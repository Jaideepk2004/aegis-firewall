"""
test.py — Model Evaluation
============================
Evaluates the trained PPO model (adaptive_firewall_ppo.zip) on the
held-out test set produced by data_loader.py.

Metrics reported
-----------------
  - Accuracy        : fraction of packets correctly classified
  - ROC-AUC         : area under the ROC curve (1.0 = perfect)
  - Confusion Matrix: TP / FP / FN / TN breakdown
  - Classification Report: precision, recall, F1 per class

Action interpretation for binary classification
-------------------------------------------------
  PPO output action 1 (BLOCK)  -> predicted label = 1 (ATTACK)
  PPO output action 0 or 2     -> predicted label = 0 (BENIGN / RATE-LIMIT)

This mapping is intentional: the firewall's primary job is to identify
and block attacks.  Rate-limiting is treated as "not blocked" for the
purposes of binary evaluation metrics.

Run:
  python test.py
"""

import numpy as np
from stable_baselines3 import PPO
from sklearn.metrics import (
    confusion_matrix,
    classification_report,
    roc_auc_score,
    accuracy_score,
)
from env import FirewallEnv
from data_loader import X_test, y_test

MODEL_PATH = "adaptive_firewall_ppo"


def evaluate():
    print("=" * 60)
    print("  PPO MODEL EVALUATION")
    print("=" * 60)

    # Load saved PPO model
    try:
        model = PPO.load(MODEL_PATH)
        print(f"  Model loaded from: {MODEL_PATH}.zip")
    except FileNotFoundError:
        print(f"  ERROR: {MODEL_PATH}.zip not found.")
        print("  Run train_ppo.py first to generate the model.")
        return

    env   = FirewallEnv(X_test, y_test)
    state, _ = env.reset()

    y_true:   list[int] = []
    y_pred:   list[int] = []
    actions_raw: list[int] = []

    print(f"  Evaluating on {len(X_test):,} test samples...")

    for i in range(len(X_test)):
        # Deterministic prediction (no random sampling)
        action, _ = model.predict(state, deterministic=True)
        action = int(action)
        actions_raw.append(action)

        # Map action to binary label for evaluation
        # BLOCK (1) = predicted attack;  ALLOW(0) or RATE-LIMIT(2) = not attack
        pred_label = 1 if action == 1 else 0

        y_pred.append(pred_label)
        y_true.append(int(y_test[i]))

        state, _, done, _, _ = env.step(action)
        if done:
            break

    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    actions_raw = np.array(actions_raw)

    # ── Metrics ───────────────────────────────────────────────────────
    accuracy = accuracy_score(y_true, y_pred)
    auc      = roc_auc_score(y_true, y_pred)
    cm       = confusion_matrix(y_true, y_pred)
    report   = classification_report(y_true, y_pred,
                                     target_names=["BENIGN", "ATTACK"])

    # Action distribution
    n_allow = int((actions_raw == 0).sum())
    n_block = int((actions_raw == 1).sum())
    n_rate  = int((actions_raw == 2).sum())
    total   = len(actions_raw)

    print()
    print(f"  Accuracy   : {accuracy:.4f}  ({accuracy*100:.2f}%)")
    print(f"  ROC-AUC    : {auc:.4f}")
    print()
    print("  Confusion Matrix:")
    print("             Pred BENIGN  Pred ATTACK")
    print(f"  True BENIGN   {cm[0][0]:>8,}      {cm[0][1]:>8,}")
    print(f"  True ATTACK   {cm[1][0]:>8,}      {cm[1][1]:>8,}")
    print()
    print(f"    TN (correct allow) : {cm[0][0]:,}")
    print(f"    FP (false block)   : {cm[0][1]:,}")
    print(f"    FN (missed attack) : {cm[1][0]:,}")
    print(f"    TP (correct block) : {cm[1][1]:,}")
    print()
    print("  Classification Report:")
    print(report)
    print()
    print("  Action Distribution (raw PPO outputs):")
    print(f"    ALLOW      (0) : {n_allow:>6,}  ({n_allow/total*100:.1f}%)")
    print(f"    BLOCK      (1) : {n_block:>6,}  ({n_block/total*100:.1f}%)")
    print(f"    RATE-LIMIT (2) : {n_rate:>6,}  ({n_rate/total*100:.1f}%)")
    print("=" * 60)


if __name__ == "__main__":
    evaluate()
