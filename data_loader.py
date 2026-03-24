"""
data_loader.py — Dataset Pipeline
===================================
Loads the CIC-IDS2017 network intrusion dataset from Hugging Face
(c01dsnap/CIC-IDS2017) and prepares train / test splits used by
all three RL training scripts.

Pipeline
--------
1. Download dataset via Hugging Face `datasets` library.
2. Sample 50,000 rows (manageable for RL training loops).
3. Binarise the Label column: BENIGN -> 0, everything else -> 1.
4. Select 8 handcrafted network-flow features.
5. Clean infinite values and NaNs.
6. Split 70 % train / 30 % test  (stratified, no leakage).
7. MinMax-scale train set; apply same scaler to test set.
8. Persist the fitted scaler to disk (scaler.pkl) so the Flask
   dashboard can scale uploaded CSVs consistently.

Exported symbols
----------------
  X_train, X_test   : np.ndarray  (float32, scaled to [0, 1])
  y_train, y_test   : np.ndarray  (int,   0 = benign / 1 = attack)
  scaler            : MinMaxScaler (fitted on X_train only)
  features          : list[str]   (8 feature column names)

Run order:
  python data_loader.py    <- step 1: download data, save scaler.pkl
  python qlearning.py      <- step 2: tabular RL (educational)
  python dqn.py            <- step 3: neural net RL (educational)
  python train_ppo.py      <- step 4: PPO training (production model)
  python app.py            <- step 5: launch Flask dashboard
"""

import os
import sys
import warnings
import joblib

warnings.filterwarnings("ignore")

# ── Hugging Face cache config (must happen before `datasets` import) ──
_hf_cache = os.path.join(os.getcwd(), ".cache", "huggingface")
os.makedirs(_hf_cache, exist_ok=True)
os.environ["HF_HOME"]            = _hf_cache
os.environ["HF_DATASETS_CACHE"]  = os.path.join(_hf_cache, "datasets")
os.environ["HF_METRICS_CACHE"]   = os.path.join(_hf_cache, "metrics")
os.environ["TRANSFORMERS_CACHE"] = os.path.join(_hf_cache, "transformers")
os.environ["TMP"]  = _hf_cache
os.environ["TEMP"] = _hf_cache

from datasets import load_dataset
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split


# ── Feature schema ────────────────────────────────────────────────────
features = [
    " Destination Port",
    " Flow Duration",
    " Total Fwd Packets",
    " Total Backward Packets",
    "Total Length of Fwd Packets",
    " Total Length of Bwd Packets",
    " Fwd Packet Length Mean",
    " Bwd Packet Length Mean",
]

N_SAMPLES   = 50_000
TEST_SIZE   = 0.30
RANDOM_SEED = 42
SCALER_PATH = "scaler.pkl"


# ── Data loading ──────────────────────────────────────────────────────
def load_data() -> pd.DataFrame:
    """
    Download CIC-IDS2017 from Hugging Face.
    Falls back to synthetic data if download fails.
    """
    try:
        print("Loading CIC-IDS2017 from Hugging Face...")
        dataset = load_dataset("c01dsnap/CIC-IDS2017", split="train")
        df = dataset.to_pandas().sample(N_SAMPLES, random_state=RANDOM_SEED)

        label_col = " Label"
        df["Target"] = df[label_col].apply(
            lambda x: 0 if str(x).strip().upper() == "BENIGN" else 1
        )
        df = df[features + ["Target"]]
        print(f"Dataset loaded: {len(df):,} rows | "
              f"attack ratio: {df['Target'].mean():.2%}")
        return df

    except Exception as exc:
        print(f"Warning: Could not load from Hugging Face — {exc}")
        print("Falling back to synthetic dataset for demonstration.")
        rng    = np.random.default_rng(RANDOM_SEED)
        X_syn  = rng.random((N_SAMPLES, len(features))).astype(np.float32)
        y_syn  = (rng.random(N_SAMPLES) > 0.70).astype(int)
        df     = pd.DataFrame(X_syn, columns=features)
        df["Target"] = y_syn
        print(f"Synthetic dataset ready: {len(df):,} rows | "
              f"attack ratio: {df['Target'].mean():.2%}")
        return df


# ── Pipeline function ─────────────────────────────────────────────────
def run_pipeline():
    """
    Full data pipeline: load → clean → split → scale → save scaler.
    Called only when this file is run directly (python data_loader.py).
    """
    global X_train, X_test, y_train, y_test, scaler

    print("=" * 60)
    print("  DATA LOADER — AI Adaptive Firewall")
    print("=" * 60)

    df = load_data()

    # Clean
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.fillna(0, inplace=True)

    # Build arrays
    X = df[features].values.astype(np.float32)
    y = df["Target"].values.astype(np.int32)

    # Train / test split (stratified 70/30)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=TEST_SIZE,
        stratify=y,
        random_state=RANDOM_SEED,
    )

    # Scale (fit ONLY on train — no data leakage)
    scaler = MinMaxScaler()
    X_train = scaler.fit_transform(X_train).astype(np.float32)
    X_test  = scaler.transform(X_test).astype(np.float32)

    # Save scaler for app.py to use on uploaded CSVs
    joblib.dump(scaler, SCALER_PATH)

    print(f"Train : {X_train.shape}  |  attack ratio : {y_train.mean():.2%}")
    print(f"Test  : {X_test.shape}   |  attack ratio : {y_test.mean():.2%}")
    print(f"Scaler saved -> {SCALER_PATH}")
    print("=" * 60)
    print()
    print("  DATA LOADING COMPLETE.")
    print()
    print("  NEXT STEPS (run in order):")
    print("  python qlearning.py    <- Step 2: Q-Learning (educational)")
    print("  python dqn.py          <- Step 3: DQN        (educational)")
    print("  python train_ppo.py    <- Step 4: PPO        (production model)")
    print("  python app.py          <- Step 5: Flask dashboard")
    print("=" * 60)


# ── Lazy-load for imports (used by qlearning.py, dqn.py, train_ppo.py) ──
# When other scripts do `from data_loader import X_train, y_train`,
# this block runs silently (no terminal output) so training scripts
# get the data without re-printing the pipeline banner.
def _silent_load():
    """Load data silently when imported by other training scripts."""
    global X_train, X_test, y_train, y_test, scaler

    df = load_data.__wrapped__() if hasattr(load_data, '__wrapped__') else _load_data_silent()

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.fillna(0, inplace=True)

    X = df[features].values.astype(np.float32)
    y = df["Target"].values.astype(np.int32)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=TEST_SIZE,
        stratify=y,
        random_state=RANDOM_SEED,
    )

    scaler = MinMaxScaler()
    X_train = scaler.fit_transform(X_train).astype(np.float32)
    X_test  = scaler.transform(X_test).astype(np.float32)

    if os.path.exists(SCALER_PATH):
        scaler = joblib.load(SCALER_PATH)
    else:
        joblib.dump(scaler, SCALER_PATH)


def _load_data_silent() -> pd.DataFrame:
    """Silent version of load_data() — no print output."""
    import warnings
    warnings.filterwarnings("ignore")
    try:
        dataset = load_dataset("c01dsnap/CIC-IDS2017", split="train")
        df = dataset.to_pandas().sample(N_SAMPLES, random_state=RANDOM_SEED)
        label_col = " Label"
        df["Target"] = df[label_col].apply(
            lambda x: 0 if str(x).strip().upper() == "BENIGN" else 1
        )
        return df[features + ["Target"]]
    except Exception:
        rng   = np.random.default_rng(RANDOM_SEED)
        X_syn = rng.random((N_SAMPLES, len(features))).astype(np.float32)
        y_syn = (rng.random(N_SAMPLES) > 0.70).astype(int)
        df    = pd.DataFrame(X_syn, columns=features)
        df["Target"] = y_syn
        return df


# ── Module-level variables (populated on import OR on direct run) ─────
X_train = X_test = y_train = y_test = scaler = None

if __name__ == "__main__":
    # Direct run: full pipeline with terminal output
    run_pipeline()
else:
    # Imported by another script: load silently, no banner printed
    _silent_load()