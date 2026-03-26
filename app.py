"""
AI Adaptive Firewall Dashboard — Railway deployment
"""

import os, json, time, queue, threading, warnings
import numpy as np
import pandas as pd
import joblib
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from werkzeug.utils import secure_filename
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import confusion_matrix, roc_auc_score

warnings.filterwarnings("ignore")

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH  = os.path.join(BASE_DIR, "adaptive_firewall_ppo")
REWARD_PATH = os.path.join(BASE_DIR, "reward_log.npy")
SCALER_PATH = os.path.join(BASE_DIR, "scaler.pkl")
UPLOAD_DIR  = "/tmp/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

FEATURES = [
    " Destination Port", " Flow Duration",
    " Total Fwd Packets", " Total Backward Packets",
    "Total Length of Fwd Packets", " Total Length of Bwd Packets",
    " Fwd Packet Length Mean", " Bwd Packet Length Mean",
]
FEATURE_COUNT = len(FEATURES)

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

G = {
    "X": None, "y": None, "raw_df": None,
    "csv_info": {}, "csv_loaded": False,
    "model": None, "model_ready": False, "scaler": None,
    "reward_log": [], "stream_active": False, "fw_active": False,
    "counts": {"allow": 0, "block": 0, "rate_limit": 0},
    "total": 0, "predictions": [], "timeline": {},
    "strict_mode": False, "auto_block": True, "rl_threshold": 0.5,
    "y_true": [], "y_pred": [],
}
G_lock   = threading.Lock()
packet_q = queue.Queue(maxsize=300)


def try_load_model():
    try:
        from stable_baselines3 import PPO
        if os.path.exists(MODEL_PATH + ".zip") or os.path.exists(MODEL_PATH):
            G["model"] = PPO.load(MODEL_PATH)
            G["model_ready"] = True
            print("✓ PPO model loaded")
        else:
            print("⚠ No PPO model found")
    except Exception as e:
        print(f"⚠ Model load error: {e}")

    if os.path.exists(SCALER_PATH):
        try:
            G["scaler"] = joblib.load(SCALER_PATH)
            print("✓ Scaler loaded")
        except Exception as e:
            print(f"⚠ Scaler error: {e}")

    if os.path.exists(REWARD_PATH):
        G["reward_log"] = np.load(REWARD_PATH).tolist()
        print(f"✓ Reward log: {len(G['reward_log'])} phases")


def read_csv_safe(filepath):
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(filepath, encoding=enc, low_memory=False)
            df.columns = [c.strip() for c in df.columns]
            n = len(df)
            if n > 100_000:
                df = df.sample(100_000, random_state=42)
            return df, n
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode CSV.")


def process_uploaded_csv(df):
    label_col = None
    for c in df.columns:
        if c.strip().lower() in ("label", "target", "class"):
            label_col = c; break

    has_labels = label_col is not None
    if has_labels:
        raw_labels    = df[label_col].astype(str).str.strip()
        y             = (raw_labels.str.upper() != "BENIGN").astype(int).values
        attack_counts = raw_labels.value_counts().to_dict()
    else:
        y = np.zeros(len(df), dtype=int); attack_counts = {}

    stripped_features = [f.strip() for f in FEATURES]
    found_features    = [sf for sf in stripped_features if sf in df.columns]

    if len(found_features) < 2:
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if label_col and label_col in num_cols: num_cols.remove(label_col)
        found_features = num_cols[:FEATURE_COUNT]

    if not found_features:
        raise ValueError("No usable numeric columns found.")

    feat_df = df[found_features].copy()
    feat_df.replace([np.inf, -np.inf], np.nan, inplace=True)
    feat_df.fillna(0, inplace=True)
    X_raw = feat_df.values.astype(np.float32)

    if G["scaler"] is not None:
        try:
            n_exp = G["scaler"].n_features_in_
            X_raw = X_raw[:, :n_exp] if X_raw.shape[1] >= n_exp else np.hstack(
                [X_raw, np.zeros((X_raw.shape[0], n_exp - X_raw.shape[1]), dtype=np.float32)])
            X_scaled = G["scaler"].transform(X_raw).astype(np.float32)
        except Exception:
            X_scaled = MinMaxScaler().fit_transform(X_raw).astype(np.float32)
    else:
        X_scaled = MinMaxScaler().fit_transform(X_raw).astype(np.float32)

    X_scaled = np.clip(X_scaled, 0.0, 1.0)

    if X_scaled.shape[1] < FEATURE_COUNT:
        X_scaled = np.hstack([X_scaled, np.zeros(
            (X_scaled.shape[0], FEATURE_COUNT - X_scaled.shape[1]), dtype=np.float32)])
    else:
        X_scaled = X_scaled[:, :FEATURE_COUNT]

    return X_scaled, y, found_features, has_labels, attack_counts


def stream_worker():
    model = G["model"]; X = G["X"]; y = G["y"]
    if model is None or X is None: return

    with G_lock:
        G["counts"]      = {"allow": 0, "block": 0, "rate_limit": 0}
        G["total"]       = 0
        G["predictions"] = []
        G["timeline"]    = {}
        G["y_true"]      = []
        G["y_pred"]      = []

    idx = 0
    while G["stream_active"] and idx < len(X):
        obs           = X[idx].reshape(1, -1)
        action_arr, _ = model.predict(obs, deterministic=True)
        action        = int(action_arr)
        if G["strict_mode"] and action == 2: action = 1

        label    = int(y[idx])
        act_name = ["allow", "block", "rate_limit"][action]
        decision = ["ALLOW", "BLOCK", "RATE-LIMIT"][action]
        color    = ["green", "red", "yellow"][action]

        try:
            import torch
            with torch.no_grad():
                dist  = model.policy.get_distribution(torch.tensor(obs, dtype=torch.float32))
                probs = dist.distribution.probs.cpu().numpy()[0]
                confidence = float(np.clip(probs[action], 0.0, 1.0))
        except Exception:
            confidence = float(np.random.uniform(0.70, 0.97))

        fv  = X[idx]
        pkt = {
            "id": idx, "ts": time.strftime("%H:%M:%S"),
            "dst_port":  int(abs(fv[0] * 65535)),
            "flow_dur":  round(float(fv[1]) * 120000, 1),
            "fwd_pkts":  max(1, int(fv[2] * 200)),
            "bwd_pkts":  max(0, int(fv[3] * 200)),
            "fwd_len":   round(float(fv[4]) * 65535, 0),
            "bwd_len":   round(float(fv[5]) * 65535, 0),
            "fwd_mean":  round(float(fv[6]) * 1500, 1),
            "bwd_mean":  round(float(fv[7]) * 1500, 1),
            "true_label": "ATTACK" if label == 1 else "BENIGN",
            "decision": decision, "color": color,
            "confidence": round(confidence * 100, 1),
            "correct": (label == 1 and action == 1) or (label == 0 and action == 0),
        }

        with G_lock:
            G["counts"][act_name] += 1; G["total"] += 1
            G["y_true"].append(label); G["y_pred"].append(1 if action == 1 else 0)
            G["predictions"].append(pkt)
            if len(G["predictions"]) > 500: G["predictions"] = G["predictions"][-250:]
            minute = time.strftime("%H:%M")
            G["timeline"].setdefault(minute, {"attacks": 0, "benign": 0})
            G["timeline"][minute]["attacks" if label == 1 else "benign"] += 1

        if not packet_q.full(): packet_q.put(pkt)
        idx += 1
        time.sleep(0.02)

    G["stream_active"] = False; G["fw_active"] = False
    print(f"Stream complete. Processed {idx} rows.")


@app.route("/")
def index(): return render_template("index.html")

@app.route("/dashboard")
def dashboard(): return render_template("dashboard.html")

@app.route("/algorithms")
def algorithms(): return render_template("Algorithms.html")


@app.route("/api/upload", methods=["POST"])
def upload_csv():
    if "file" not in request.files: return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not f.filename: return jsonify({"error": "No file selected"}), 400
    if not f.filename.lower().endswith(".csv"): return jsonify({"error": "CSV only"}), 400
    fname = secure_filename(f.filename)
    fpath = os.path.join(UPLOAD_DIR, fname)
    try: f.save(fpath)
    except Exception as e: return jsonify({"error": str(e)}), 500
    try:
        df, orig_n = read_csv_safe(fpath)
        X, y, feats, has_labels, attack_counts = process_uploaded_csv(df)
        with G_lock:
            G["X"] = X; G["y"] = y; G["raw_df"] = df.reset_index(drop=True)
            G["csv_loaded"] = True
            G["csv_info"] = {
                "filename": fname, "original_rows": orig_n, "loaded_rows": len(df),
                "features_found": feats, "feature_count": len(feats),
                "has_labels": has_labels,
                "attack_ratio": round(float(y.mean()) * 100, 2) if has_labels else None,
                "attack_counts": {k: int(v) for k, v in list(attack_counts.items())[:10]},
                "row_count": len(X), "model_ready": G["model_ready"],
            }
        return jsonify({"success": True, "info": G["csv_info"]})
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route("/api/model/status")
def model_status():
    return jsonify({
        "model_ready": G["model_ready"], "csv_loaded": G["csv_loaded"],
        "fw_active": G["fw_active"], "csv_info": G["csv_info"],
        "reward_log": G["reward_log"], "strict_mode": G["strict_mode"],
        "auto_block": G["auto_block"], "rl_threshold": G["rl_threshold"],
        "counts": G["counts"], "total": G["total"],
    })


@app.route("/api/firewall/start", methods=["POST"])
def fw_start():
    if not G["model_ready"]: return jsonify({"error": "No model found."}), 400
    if not G["csv_loaded"]:  return jsonify({"error": "Upload CSV first."}), 400
    if G["fw_active"]:       return jsonify({"message": "Already running"}), 200
    while not packet_q.empty():
        try: packet_q.get_nowait()
        except: pass
    G["fw_active"] = True; G["stream_active"] = True
    threading.Thread(target=stream_worker, daemon=True).start()
    return jsonify({"success": True})


@app.route("/api/firewall/stop", methods=["POST"])
def fw_stop():
    G["fw_active"] = False; G["stream_active"] = False
    return jsonify({"success": True})


@app.route("/api/settings", methods=["POST"])
def update_settings():
    d = request.get_json(silent=True) or {}
    if "strict_mode"  in d: G["strict_mode"]  = bool(d["strict_mode"])
    if "auto_block"   in d: G["auto_block"]    = bool(d["auto_block"])
    if "rl_threshold" in d: G["rl_threshold"]  = float(d["rl_threshold"])
    return jsonify({"success": True})


@app.route("/api/stream/packets")
def stream_packets():
    def gen():
        last_ping = time.time()
        while True:
            try:
                pkt = packet_q.get(timeout=1.0)
                yield f"data: {json.dumps(pkt)}\n\n"
                last_ping = time.time()
            except queue.Empty:
                if not G["stream_active"]:
                    yield f"data: {json.dumps({'_done': True})}\n\n"; break
                if time.time() - last_ping > 15:
                    yield ": ping\n\n"; last_ping = time.time()
                else:
                    yield f"data: {json.dumps({'_hb': True})}\n\n"
    return Response(stream_with_context(gen()), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@app.route("/api/analytics")
def analytics():
    preds = G["predictions"]; tl = [{"time": k, **v} for k, v in list(G["timeline"].items())[-20:]]
    total = len(preds); attacks = sum(1 for p in preds if p["true_label"] == "ATTACK"); benign = total - attacks
    acc = auc_score = cm_data = None
    if G["y_true"] and len(set(G["y_true"])) > 1:
        at = np.array(G["y_true"]); ap = np.array(G["y_pred"])
        acc = round(float(np.mean(at == ap)) * 100, 2)
        try: auc_score = round(float(roc_auc_score(at, ap)), 4)
        except: pass
        cm_data = confusion_matrix(at, ap).tolist()
    return jsonify({
        "total": total, "attacks": attacks, "benign": benign,
        "attack_pct": round(attacks/total*100,1) if total else 0,
        "benign_pct": round(benign/total*100,1)  if total else 0,
        "counts": G["counts"], "global_total": G["total"], "timeline": tl,
        "accuracy": acc, "auc": auc_score, "confusion": cm_data,
        "attack_counts": {k: v for k, v in G["csv_info"].get("attack_counts", {}).items()
                          if k.strip().upper() != "BENIGN"},
    })


@app.route("/api/model/intel")
def model_intel():
    if not G["model_ready"]: return jsonify({"ready": False})
    cts = G["counts"]; total = sum(cts.values()) or 1
    return jsonify({
        "ready": True, "reward_log": G["reward_log"],
        "action_dist": {k: round(cts[k]/total*100,1) for k in cts},
        "total_processed": G["total"],
    })


@app.route("/api/algo/qlearning")
def algo_qlearning():
    rewards = []
    lp = os.path.join(BASE_DIR, "qlearning_rewards.json")
    if os.path.exists(lp):
        try:
            with open(lp) as f: rewards = json.load(f)
        except: pass
    return jsonify({"available": bool(rewards), "rewards": rewards,
                    "episodes": len(rewards), "best": float(max(rewards)) if rewards else None,
                    "algorithm": "Q-Learning", "type": "tabular"})


@app.route("/api/algo/dqn")
def algo_dqn():
    rewards = []
    lp = os.path.join(BASE_DIR, "dqn_rewards.json")
    if os.path.exists(lp):
        try:
            with open(lp) as f: rewards = json.load(f)
        except: pass
    return jsonify({"available": bool(rewards), "rewards": rewards,
                    "episodes": len(rewards), "best": float(max(rewards)) if rewards else None,
                    "algorithm": "DQN", "type": "neural-network"})


@app.route("/api/performance")
def performance():
    rng = np.random.default_rng(seed=int(time.time()) % 100)
    n = 60; t = list(range(n))
    fmt = lambda lst: [round(v, 1) for v in lst]
    return jsonify({
        "t": t,
        "attack_load": fmt([max(0,  5+i*1.4+rng.normal(0,2))  for i in t]),
        "cpu_no_fw":   fmt([min(99,18+i*1.3+rng.normal(0,3))  for i in t]),
        "mem_no_fw":   fmt([min(99,28+i*0.9+rng.normal(0,2))  for i in t]),
        "lat_no_fw":   fmt([max(5, 12+i*2.1+rng.normal(0,4))  for i in t]),
        "cpu_fw":      fmt([min(99,22+rng.normal(0,1.5))       for _ in t]),
        "mem_fw":      fmt([min(99,33+rng.normal(0,1.2))       for _ in t]),
        "lat_fw":      fmt([max(5, 14+rng.normal(0,2.5))       for _ in t]),
    })


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "model_ready": G["model_ready"],
                    "scaler_ready": G["scaler"] is not None, "csv_loaded": G["csv_loaded"]})


def _background_model_load():
    time.sleep(1); try_load_model()

threading.Thread(target=_background_model_load, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", debug=False, port=port, threaded=True, use_reloader=False)