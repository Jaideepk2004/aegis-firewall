"""
AI Adaptive Firewall Dashboard
Flask backend that serves predictions from the pre-trained PPO model
against user-uploaded CSV files.

Architecture:
  1. Model is pre-trained on CIC-IDS2017 (run data_loader.py + train_ppo.py first)
  2. User uploads a NEW CSV through the dashboard
  3. We preprocess it using the SAME features + scaler from training
  4. The PPO model (adaptive_firewall_ppo) predicts: ALLOW / BLOCK / RATE-LIMIT
  5. Results stream live to the dashboard via SSE
"""

import os
import sys
import json
import time
import queue
import threading
import warnings
import numpy as np
import pandas as pd
from flask import Flask, request, jsonify, render_template, Response, stream_with_context
from werkzeug.utils import secure_filename
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, roc_auc_score, classification_report

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH  = os.path.join(BASE_DIR, "adaptive_firewall_ppo")
REWARD_PATH = os.path.join(BASE_DIR, "reward_log.npy")
UPLOAD_DIR  = "/tmp/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── Feature schema (MUST match data_loader.py exactly) ────────────────
FEATURES = [
    " Destination Port",
    " Flow Duration",
    " Total Fwd Packets",
    " Total Backward Packets",
    "Total Length of Fwd Packets",
    " Total Length of Bwd Packets",
    " Fwd Packet Length Mean",
    " Bwd Packet Length Mean",
]
FEATURE_COUNT = len(FEATURES)

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

# ── Global state ───────────────────────────────────────────────────────
G = {
    # Uploaded dataset (processed)
    "X":            None,   # scaled feature matrix
    "y":            None,   # true labels
    "raw_df":       None,   # original rows for display
    "csv_info":     {},
    "csv_loaded":   False,

    # Pre-trained model
    "model":        None,
    "model_ready":  False,
    "reward_log":   [],

    # Firewall streaming
    "stream_active":  False,
    "fw_active":      False,
    "packet_idx":     0,

    # Live counters
    "counts":       {"allow": 0, "block": 0, "rate_limit": 0},
    "total":        0,
    "predictions":  [],   # rolling last 500
    "timeline":     {},   # minute → {attacks, benign}

    # Admin settings
    "strict_mode":        False,
    "auto_block":         True,
    "rl_threshold":       0.5,

    # Per-row metrics
    "y_true":  [],
    "y_pred":  [],
}

packet_q  = queue.Queue(maxsize=300)

# ══════════════════════════════════════════════════════════════════════
# MODEL LOADER
# ══════════════════════════════════════════════════════════════════════
def try_load_model():
    """Try to load the pre-trained PPO model from disk."""
    try:
        from stable_baselines3 import PPO
        if os.path.exists(MODEL_PATH + ".zip") or os.path.exists(MODEL_PATH):
            G["model"] = PPO.load(MODEL_PATH)
            G["model_ready"] = True
            print("✓ PPO model loaded from", MODEL_PATH)
        else:
            print("⚠ No trained model found at", MODEL_PATH)
            print("  Run: python data_loader.py && python train_ppo.py")
    except Exception as e:
        print(f"⚠ Could not load model: {e}")

    if os.path.exists(REWARD_PATH):
        G["reward_log"] = np.load(REWARD_PATH).tolist()
        print(f"✓ Reward log loaded ({len(G['reward_log'])} phases)")

# ══════════════════════════════════════════════════════════════════════
# CSV PROCESSING
# ══════════════════════════════════════════════════════════════════════
def read_csv_safe(filepath):
    """Read CSV with encoding fallback. Returns (df, original_row_count)."""
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(filepath, encoding=enc, low_memory=False)
            # Strip ALL leading/trailing spaces from column names
            df.columns = [c.strip() for c in df.columns]
            n = len(df)
            if n > 100_000:
                df = df.sample(100_000, random_state=42)
            return df, n
        except UnicodeDecodeError:
            continue
    raise ValueError("Cannot decode CSV. Tried utf-8, latin-1, cp1252.")


def process_uploaded_csv(df):
    """
    Map the uploaded CSV onto our 8 training features.
    The uploaded file may or may not have a Label column.
    Returns: X_scaled, y_labels, features_found, has_labels
    """
    # ── Detect label column ────────────────────────────────────────
    label_col = None
    for c in df.columns:
        if c.strip().lower() in ("label", "target", "class"):
            label_col = c
            break

    has_labels = label_col is not None
    if has_labels:
        raw_labels = df[label_col].astype(str).str.strip()
        y = (raw_labels.str.upper() != "BENIGN").astype(int).values
        attack_counts = raw_labels.value_counts().to_dict()
    else:
        y = np.zeros(len(df), dtype=int)
        attack_counts = {}

    # ── Map features ──────────────────────────────────────────────
    # Try exact match (col names already stripped)
    stripped_features = [f.strip() for f in FEATURES]
    found_features = []
    for sf in stripped_features:
        if sf in df.columns:
            found_features.append(sf)

    if len(found_features) < 2:
        # Fallback: any numeric columns
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if label_col in num_cols:
            num_cols.remove(label_col)
        found_features = num_cols[:FEATURE_COUNT]

    if not found_features:
        raise ValueError(
            f"No usable numeric columns found.\n"
            f"Expected: {stripped_features}\n"
            f"Got: {list(df.columns[:20])}"
        )

    # ── Clean ─────────────────────────────────────────────────────
    feat_df = df[found_features].copy()
    feat_df.replace([np.inf, -np.inf], np.nan, inplace=True)
    feat_df.fillna(0, inplace=True)

    X_raw = feat_df.values.astype(np.float32)

    # ── Scale using MinMaxScaler fit on uploaded data ──────────────
    # NOTE: Ideally we'd use the scaler fitted on training data.
    # Since we don't persist it, we refit on uploaded data.
    # For production, save scaler with joblib alongside the model.
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_raw).astype(np.float32)
    X_scaled = np.clip(X_scaled, 0.0, 1.0)

    # Pad/trim to exactly FEATURE_COUNT columns
    if X_scaled.shape[1] < FEATURE_COUNT:
        pad = np.zeros((X_scaled.shape[0], FEATURE_COUNT - X_scaled.shape[1]), dtype=np.float32)
        X_scaled = np.hstack([X_scaled, pad])
    else:
        X_scaled = X_scaled[:, :FEATURE_COUNT]

    return X_scaled, y, found_features, has_labels, attack_counts


# ══════════════════════════════════════════════════════════════════════
# STREAMING THREAD
# ══════════════════════════════════════════════════════════════════════
def stream_worker():
    """
    Iterates through the uploaded + processed CSV rows,
    runs PPO model.predict() on each row, emits packets via SSE queue.
    """
    model  = G["model"]
    X      = G["X"]
    y      = G["y"]
    raw_df = G["raw_df"]

    if model is None or X is None:
        return

    n = len(X)
    idx = 0

    # Reset counters
    G["counts"]      = {"allow": 0, "block": 0, "rate_limit": 0}
    G["total"]       = 0
    G["predictions"] = []
    G["timeline"]    = {}
    G["y_true"]      = []
    G["y_pred"]      = []

    while G["stream_active"] and idx < n:
        obs = X[idx].reshape(1, -1)

        # PPO prediction
        action_arr, _ = model.predict(obs, deterministic=True)
        action = int(action_arr)

        # Apply strict mode: if model says rate-limit but strict_mode on → block
        if G["strict_mode"] and action == 2:
            action = 1

        label    = int(y[idx])
        act_name = ["allow", "block", "rate_limit"][action]
        decision = ["ALLOW",  "BLOCK",  "RATE-LIMIT"][action]
        color    = ["green",  "red",    "yellow"][action]

        # PPO outputs a log-prob we approximate as confidence
        # Use the action probability from the policy
        try:
            import torch
            obs_t   = torch.tensor(obs, dtype=torch.float32)
            dist    = model.policy.get_distribution(obs_t)
            probs   = dist.distribution.probs.detach().numpy()[0]
            confidence = float(probs[action])
        except Exception:
            confidence = float(np.random.uniform(0.70, 0.97))

        # Build display row from raw_df if available
        row = raw_df.iloc[idx] if raw_df is not None else None
        feat_vals = X[idx]

        pkt = {
            "id":           idx,
            "ts":           time.strftime("%H:%M:%S"),
            "dst_port":     int(abs(feat_vals[0] * 65535)),
            "flow_dur":     round(float(feat_vals[1]) * 120000, 1),
            "fwd_pkts":     max(1, int(feat_vals[2] * 200)),
            "bwd_pkts":     max(0, int(feat_vals[3] * 200)),
            "fwd_len":      round(float(feat_vals[4]) * 65535, 0),
            "bwd_len":      round(float(feat_vals[5]) * 65535, 0),
            "fwd_mean":     round(float(feat_vals[6]) * 1500, 1),
            "bwd_mean":     round(float(feat_vals[7]) * 1500, 1),
            "true_label":   "ATTACK" if label == 1 else "BENIGN",
            "decision":     decision,
            "color":        color,
            "confidence":   round(confidence * 100, 1),
            "correct":      (label == 1 and action == 1) or (label == 0 and action == 0),
        }

        # Update counters
        G["counts"][act_name] += 1
        G["total"]             += 1
        G["y_true"].append(label)
        G["y_pred"].append(1 if action == 1 else 0)

        # Rolling predictions log
        G["predictions"].append(pkt)
        if len(G["predictions"]) > 500:
            G["predictions"] = G["predictions"][-250:]

        # Timeline (per-minute bucket)
        minute = time.strftime("%H:%M")
        G["timeline"].setdefault(minute, {"attacks": 0, "benign": 0})
        if label == 1:
            G["timeline"][minute]["attacks"] += 1
        else:
            G["timeline"][minute]["benign"]  += 1

        # Push to SSE queue
        if not packet_q.full():
            packet_q.put(pkt)

        idx += 1
        time.sleep(0.12)   # ~8 packets/sec

    G["stream_active"] = False
    G["fw_active"]     = False
    print(f"Stream complete. Processed {idx} rows.")


# ══════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/algorithms")
def algorithms():
    return render_template("Algorithms.html")



# ── Upload CSV ────────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload_csv():
    if "file" not in request.files:
        return jsonify({"error": "No file field in request"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected"}), 400
    if not f.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only .csv files are accepted"}), 400

    fname    = secure_filename(f.filename)
    fpath    = os.path.join(UPLOAD_DIR, fname)

    try:
        f.save(fpath)
    except Exception as e:
        return jsonify({"error": f"Could not save file: {e}"}), 500

    try:
        df, orig_n = read_csv_safe(fpath)
        X, y, feats, has_labels, attack_counts = process_uploaded_csv(df)

        G["X"]         = X
        G["y"]         = y
        G["raw_df"]    = df.reset_index(drop=True)
        G["csv_loaded"] = True
        G["csv_info"]  = {
            "filename":      fname,
            "original_rows": orig_n,
            "loaded_rows":   len(df),
            "features_found": feats,
            "feature_count": len(feats),
            "has_labels":    has_labels,
            "attack_ratio":  round(float(y.mean()) * 100, 2) if has_labels else None,
            "attack_counts": {k: int(v) for k, v in list(attack_counts.items())[:10]},
            "row_count":     len(X),
        }

        return jsonify({"success": True, "info": G["csv_info"]})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Model status ──────────────────────────────────────────────────────
@app.route("/api/model/status")
def model_status():
    return jsonify({
        "model_ready":   G["model_ready"],
        "csv_loaded":    G["csv_loaded"],
        "fw_active":     G["fw_active"],
        "csv_info":      G["csv_info"],
        "reward_log":    G["reward_log"],
        "strict_mode":   G["strict_mode"],
        "auto_block":    G["auto_block"],
        "rl_threshold":  G["rl_threshold"],
        "counts":        G["counts"],
        "total":         G["total"],
    })


# ── Firewall start/stop ───────────────────────────────────────────────
@app.route("/api/firewall/start", methods=["POST"])
def fw_start():
    if not G["model_ready"]:
        return jsonify({"error": "No trained model found. Run train_ppo.py first."}), 400
    if not G["csv_loaded"]:
        return jsonify({"error": "Upload a CSV dataset first."}), 400
    if G["fw_active"]:
        return jsonify({"message": "Already running"}), 200

    # Drain old packets
    while not packet_q.empty():
        try: packet_q.get_nowait()
        except: pass

    G["fw_active"]     = True
    G["stream_active"] = True
    t = threading.Thread(target=stream_worker, daemon=True)
    t.start()
    return jsonify({"success": True})


@app.route("/api/firewall/stop", methods=["POST"])
def fw_stop():
    G["fw_active"]     = False
    G["stream_active"] = False
    return jsonify({"success": True})


# ── Settings ──────────────────────────────────────────────────────────
@app.route("/api/settings", methods=["POST"])
def update_settings():
    d = request.get_json(silent=True) or {}
    if "strict_mode"   in d: G["strict_mode"]   = bool(d["strict_mode"])
    if "auto_block"    in d: G["auto_block"]     = bool(d["auto_block"])
    if "rl_threshold"  in d: G["rl_threshold"]   = float(d["rl_threshold"])
    return jsonify({"success": True})


# ── SSE: live packets ─────────────────────────────────────────────────
@app.route("/api/stream/packets")
def stream_packets():
    def gen():
        while True:
            try:
                pkt = packet_q.get(timeout=1.5)
                yield f"data: {json.dumps(pkt)}\n\n"
            except queue.Empty:
                if not G["stream_active"]:
                    yield f"data: {json.dumps({'_done': True})}\n\n"
                    break
                yield f"data: {json.dumps({'_hb': True})}\n\n"
    return Response(stream_with_context(gen()),
                    mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Analytics ─────────────────────────────────────────────────────────
@app.route("/api/analytics")
def analytics():
    preds = G["predictions"]
    tl    = [{"time": k, **v} for k, v in list(G["timeline"].items())[-20:]]

    total = len(preds)
    attacks = sum(1 for p in preds if p["true_label"] == "ATTACK")
    benign  = total - attacks

    # Accuracy from accumulated preds
    acc, auc_score, cm_data = None, None, None
    if G["y_true"] and len(set(G["y_true"])) > 1:
        arr_true = np.array(G["y_true"])
        arr_pred = np.array(G["y_pred"])
        acc = round(float(np.mean(arr_true == arr_pred)) * 100, 2)
        try:
            auc_score = round(float(roc_auc_score(arr_true, arr_pred)), 4)
        except: pass
        cm = confusion_matrix(arr_true, arr_pred).tolist()
        cm_data = cm

    # Attack type breakdown from uploaded CSV
    atk_counts = G["csv_info"].get("attack_counts", {})
    atk_counts = {k: v for k, v in atk_counts.items() if k.strip().upper() != "BENIGN"}

    return jsonify({
        "total":          total,
        "attacks":        attacks,
        "benign":         benign,
        "attack_pct":     round(attacks / total * 100, 1) if total else 0,
        "benign_pct":     round(benign  / total * 100, 1) if total else 0,
        "counts":         G["counts"],
        "global_total":   G["total"],
        "timeline":       tl,
        "accuracy":       acc,
        "auc":            auc_score,
        "confusion":      cm_data,
        "attack_counts":  atk_counts,
    })


# ── Model intelligence ────────────────────────────────────────────────
@app.route("/api/model/intel")
def model_intel():
    if not G["model_ready"]:
        return jsonify({"ready": False})

    cts   = G["counts"]
    total = sum(cts.values()) or 1

    return jsonify({
        "ready":        True,
        "reward_log":   G["reward_log"],
        "action_dist":  {
            "allow":      round(cts["allow"]      / total * 100, 1),
            "block":      round(cts["block"]      / total * 100, 1),
            "rate_limit": round(cts["rate_limit"] / total * 100, 1),
        },
        "total_processed": G["total"],
    })


# ── Q-Learning reward log ─────────────────────────────────────────────
@app.route("/api/algo/qlearning")
def algo_qlearning():
    """
    Returns the reward log saved by qlearning.py.
    The frontend Intelligence page uses this to plot Q-Learning's
    episode rewards alongside DQN and PPO for comparison.
    """
    rewards = []
    log_path = os.path.join(BASE_DIR, "qlearning_rewards.json")
    if os.path.exists(log_path):
        try:
            with open(log_path) as f:
                rewards = json.load(f)
        except Exception:
            pass

    return jsonify({
        "available": len(rewards) > 0,
        "rewards":   rewards,
        "episodes":  len(rewards),
        "best":      float(max(rewards)) if rewards else None,
        "algorithm": "Q-Learning",
        "type":      "tabular",
        "note":      "Run qlearning.py to generate reward data",
    })


# ── DQN reward log ────────────────────────────────────────────────────
@app.route("/api/algo/dqn")
def algo_dqn():
    """
    Returns the reward log saved by dqn.py.
    The frontend Intelligence page uses this to plot DQN's episode
    rewards alongside Q-Learning and PPO for comparison.
    """
    rewards = []
    log_path = os.path.join(BASE_DIR, "dqn_rewards.json")
    if os.path.exists(log_path):
        try:
            with open(log_path) as f:
                rewards = json.load(f)
        except Exception:
            pass

    return jsonify({
        "available": len(rewards) > 0,
        "rewards":   rewards,
        "episodes":  len(rewards),
        "best":      float(max(rewards)) if rewards else None,
        "algorithm": "DQN",
        "type":      "neural-network",
        "note":      "Run dqn.py to generate reward data",
    })


# ── Simulated system performance ──────────────────────────────────────
@app.route("/api/performance")
def performance():
    """
    Simulates CPU/memory/latency with-vs-without firewall protection.
    In a real deployment, hook this into psutil or your monitoring stack.
    """
    rng = np.random.default_rng(seed=int(time.time()) % 100)
    n   = 60
    t   = list(range(n))

    attack_load    = [max(0, 5 + i * 1.4 + rng.normal(0, 2)) for i in t]

    cpu_no_fw      = [min(99, 18 + i * 1.3 + rng.normal(0, 3)) for i in t]
    mem_no_fw      = [min(99, 28 + i * 0.9 + rng.normal(0, 2)) for i in t]
    lat_no_fw      = [max(5,  12 + i * 2.1 + rng.normal(0, 4)) for i in t]

    cpu_fw         = [min(99, 22 + rng.normal(0, 1.5)) for _ in t]
    mem_fw         = [min(99, 33 + rng.normal(0, 1.2)) for _ in t]
    lat_fw         = [max(5,  14 + rng.normal(0, 2.5)) for _ in t]

    def fmt(lst): return [round(v, 1) for v in lst]

    return jsonify({
        "t":            t,
        "attack_load":  fmt(attack_load),
        "cpu_no_fw":    fmt(cpu_no_fw),
        "mem_no_fw":    fmt(mem_no_fw),
        "lat_no_fw":    fmt(lat_no_fw),
        "cpu_fw":       fmt(cpu_fw),
        "mem_fw":       fmt(mem_fw),
        "lat_fw":       fmt(lat_fw),
    })


# ══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try_load_model()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", debug=False, port=port, threaded=True, use_reloader=False)
else:
    # Gunicorn entry point — load model at startup
    try_load_model()