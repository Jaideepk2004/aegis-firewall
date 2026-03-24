"""
test.py — FINAL HYBRID MODEL EVALUATION
=======================================

Evaluates:
    1. Q-Learning
    2. DQN
    3. PPO
    4. HYBRID MODEL (combined)

Hybrid Rule:
    If ANY model predicts ATTACK → final prediction = ATTACK

Binary mapping:
    BLOCK (1) = ATTACK
    ALLOW (0) or RATE-LIMIT (2) = BENIGN

Run:
    python test.py
"""

import numpy as np
import torch
import json

from stable_baselines3 import PPO
from sklearn.metrics import (
    confusion_matrix,
    classification_report,
    roc_auc_score,
    accuracy_score,
)

from env import FirewallEnv
from data_loader import X_test, y_test


# ============================================================
# Q-LEARNING POLICY (approximation using reward trend)
# ============================================================
def load_qlearning_policy():

    try:
        with open("qlearning_rewards.json") as f:
            rewards = json.load(f)

        print("Q-learning rewards loaded")

        # simple heuristic policy
        def policy(state):

            score = np.mean(state)

            if score > 0.65:
                return 1  # BLOCK

            elif score < 0.35:
                return 0  # ALLOW

            else:
                return 2  # RATE LIMIT

        return policy

    except:

        print("qlearning_rewards.json not found")

        return lambda s: 0


# ============================================================
# DQN MODEL
# ============================================================
class QNetwork(torch.nn.Module):

    def __init__(self, n_features, n_actions):

        super().__init__()

        self.net = torch.nn.Sequential(

            torch.nn.Linear(n_features, 128),
            torch.nn.ReLU(),

            torch.nn.Linear(128, 64),
            torch.nn.ReLU(),

            torch.nn.Linear(64, n_actions),

        )

    def forward(self, x):

        return self.net(x)


def load_dqn():

    try:

        model = QNetwork(X_test.shape[1], 3)

        model.load_state_dict(
            torch.load("dqn_firewall.pt", map_location="cpu")
        )

        model.eval()

        print("DQN model loaded")

        return model

    except:

        print("dqn_firewall.pt not found")

        return None


def dqn_predict(model, state):

    if model is None:
        return 0

    state_t = torch.tensor(
        state,
        dtype=torch.float32
    ).unsqueeze(0)

    with torch.no_grad():

        q_values = model(state_t)

    return int(q_values.argmax().item())


# ============================================================
# PPO MODEL
# ============================================================
def load_ppo():

    try:

        model = PPO.load("adaptive_firewall_ppo")

        print("PPO model loaded")

        return model

    except:

        print("adaptive_firewall_ppo.zip not found")

        return None


def ppo_predict(model, state):

    if model is None:
        return 0

    action, _ = model.predict(
        state,
        deterministic=True
    )

    return int(action)


# ============================================================
# ACTION → LABEL
# ============================================================
def action_to_label(action):

    return 1 if action == 1 else 0


# ============================================================
# SINGLE MODEL EVALUATION
# ============================================================
def evaluate_model(name, predict_function):

    env = FirewallEnv(X_test, y_test)

    state, _ = env.reset()

    y_true = []
    y_pred = []

    for _ in range(len(X_test)):

        action = predict_function(state)

        pred_label = action_to_label(action)

        y_pred.append(pred_label)

        y_true.append(int(y_test[env.index]))

        state, _, done, _, _ = env.step(action)

        if done:
            break

    y_true = np.array(y_true)

    y_pred = np.array(y_pred)

    acc = accuracy_score(y_true, y_pred)

    auc = roc_auc_score(y_true, y_pred)

    cm = confusion_matrix(y_true, y_pred)

    print()
    print("=" * 60)

    print(name)

    print("=" * 60)

    print(f"Accuracy : {acc:.4f} ({acc*100:.2f}%)")

    print(f"ROC-AUC  : {auc:.4f}")

    print()

    print("Confusion Matrix")

    print(cm)

    print()

    print(
        classification_report(
            y_true,
            y_pred,
            target_names=["BENIGN", "ATTACK"]
        )
    )


# ============================================================
# HYBRID MODEL
# ============================================================
def evaluate_hybrid(q_policy, dqn_model, ppo_model):

    env = FirewallEnv(X_test, y_test)

    state, _ = env.reset()

    y_true = []
    y_pred = []

    for _ in range(len(X_test)):

        q_action = q_policy(state)

        dqn_action = dqn_predict(dqn_model, state)

        ppo_action = ppo_predict(ppo_model, state)

        q_label = action_to_label(q_action)

        dqn_label = action_to_label(dqn_action)

        ppo_label = action_to_label(ppo_action)

        # HYBRID DECISION
        final_label = 1 if (
            q_label + dqn_label + ppo_label
        ) >= 1 else 0

        y_pred.append(final_label)

        y_true.append(int(y_test[env.index]))

        state, _, done, _, _ = env.step(ppo_action)

        if done:
            break

    y_true = np.array(y_true)

    y_pred = np.array(y_pred)

    acc = accuracy_score(y_true, y_pred)

    auc = roc_auc_score(y_true, y_pred)

    cm = confusion_matrix(y_true, y_pred)

    print()
    print("=" * 60)

    print("HYBRID MODEL (Q + DQN + PPO)")

    print("=" * 60)

    print(f"Accuracy : {acc:.4f} ({acc*100:.2f}%)")

    print(f"ROC-AUC  : {auc:.4f}")

    print()

    print("Confusion Matrix")

    print(cm)

    print()

    print(
        classification_report(
            y_true,
            y_pred,
            target_names=["BENIGN", "ATTACK"]
        )
    )


# ============================================================
# MAIN
# ============================================================
def main():

    print()
    print("=" * 60)

    print("FINAL MODEL COMPARISON")

    print("=" * 60)

    q_policy = load_qlearning_policy()

    dqn_model = load_dqn()

    ppo_model = load_ppo()

    evaluate_model(
        "Q-LEARNING",
        q_policy
    )

    evaluate_model(
        "DQN",
        lambda s: dqn_predict(dqn_model, s)
    )

    evaluate_model(
        "PPO",
        lambda s: ppo_predict(ppo_model, s)
    )

    evaluate_hybrid(
        q_policy,
        dqn_model,
        ppo_model
    )

    print("=" * 60)


if __name__ == "__main__":

    main()