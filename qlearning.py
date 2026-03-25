"""
qlearning.py — Algorithm 1: Q-Learning
========================================

WHAT IS Q-LEARNING?
--------------------
Q-Learning is the simplest tabular reinforcement learning algorithm.
It learns a Q-table: a lookup table that maps (state, action) pairs
to expected future rewards.

  Q(s, a) = expected total reward if we take action `a` in state `s`
             and then act optimally afterwards.

Q-VALUE UPDATE RULE (Bellman equation):
  Q(s, a) <- Q(s, a) + lr * [ r  +  gamma * max_a' Q(s', a')  -  Q(s, a) ]

Run:
  python qlearning.py

Output shown on terminal only. No browser launched.
"""

import numpy as np
import json
from env import FirewallEnv
from data_loader import X_train, y_train
import pickle

# ══════════════════════════════════════════════════════════════════════
# HYPER-PARAMETERS
# ══════════════════════════════════════════════════════════════════════
EPISODES        = 1
LEARNING_RATE   = 0.10
DISCOUNT_FACTOR = 0.90
EPSILON_START   = 1.00
EPSILON_END     = 0.05
EPSILON_DECAY   = 0.95
ROUND_DECIMALS  = 1
LOG_PATH        = "qlearning_rewards.json"

# ══════════════════════════════════════════════════════════════════════
# Q-TABLE
# ══════════════════════════════════════════════════════════════════════
q_table: dict = {}


def discretize_state(state: np.ndarray) -> tuple:
    return tuple(np.round(state, ROUND_DECIMALS).tolist())


def get_q_values(state: np.ndarray) -> np.ndarray:
    key = discretize_state(state)
    if key not in q_table:
        q_table[key] = np.zeros(3, dtype=np.float32)
    return q_table[key]


def choose_action(state: np.ndarray, epsilon: float) -> int:
    if np.random.rand() < epsilon:
        return np.random.randint(3)
    return int(np.argmax(get_q_values(state)))


def update_q_value(state, action, reward, next_state):
    current_q   = get_q_values(state)[action]
    best_next_q = np.max(get_q_values(next_state))
    td_target   = reward + DISCOUNT_FACTOR * best_next_q
    td_error    = td_target - current_q
    get_q_values(state)[action] += LEARNING_RATE * td_error


# ══════════════════════════════════════════════════════════════════════
# TRAINING LOOP
# ══════════════════════════════════════════════════════════════════════
def train():
    env     = FirewallEnv(X_train, y_train)
    epsilon = EPSILON_START
    rewards_log: list[float] = []

    print()
    print("=" * 60)
    print("  STEP 2 — Q-LEARNING TRAINING")
    print("  Algorithm: Tabular Q-Learning (educational)")
    print("=" * 60)
    print(f"  Episodes       : {EPISODES}")
    print(f"  Learning rate  : {LEARNING_RATE}")
    print(f"  Discount (γ)   : {DISCOUNT_FACTOR}")
    print(f"  Epsilon start  : {EPSILON_START}  -> end: {EPSILON_END}")
    print(f"  State bins     : 10 per feature (round to {ROUND_DECIMALS} dp)")
    print(f"  Actions        : 0=ALLOW  1=BLOCK  2=RATE-LIMIT")
    print("=" * 60)

    for episode in range(EPISODES):
        state, _ = env.reset()
        total_reward = 0.0
        correct      = 0
        steps        = 0

        while True:
            action = choose_action(state, epsilon)
            next_state, reward, done, _, _ = env.step(action)
            update_q_value(state, action, reward, next_state)
            total_reward += reward
            if reward > 0:
                correct += 1
            steps  += 1
            state   = next_state
            if done:
                break

        rewards_log.append(round(total_reward, 2))
        accuracy = correct / steps * 100 if steps else 0
        print(
            f"  Episode {episode + 1:>3}/{EPISODES}"
            f"  |  Reward: {total_reward:>10.1f}"
            f"  |  Accuracy: {accuracy:>5.1f}%"
            f"  |  ε: {epsilon:.3f}"
            f"  |  Q-table size: {len(q_table):,} states"
        )
        epsilon = max(EPSILON_END, epsilon * EPSILON_DECAY)

    with open(LOG_PATH, "w") as f:
        json.dump(rewards_log, f)

    print("=" * 60)
    print(f"  Q-Learning training complete.")
    print(f"  Final Q-table size : {len(q_table):,} unique states")
    print(f"  Best episode reward: {max(rewards_log):.1f}")
    print(f"  Reward log saved   -> {LOG_PATH}")
    print()
    print("  WHY Q-LEARNING HAS LIMITS:")
    print("  - State space (8 features x 10 bins) = 10^8 possible states.")
    print("  - Cannot generalise to unseen but similar states.")
    print("  - DQN fixes this with a neural network.")
    print("=" * 60)
    print()
    print("  NEXT STEP:")
    print("  python dqn.py    <- Step 3: Deep Q-Network (neural net RL)")
    print("=" * 60)

    with open("q_table.pkl", "wb") as f:
        pickle.dump(q_table, f)

    return rewards_log


if __name__ == "__main__":
    train()