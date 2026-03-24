"""
dqn.py — Algorithm 2: Deep Q-Network (DQN)
============================================

DQN replaces the Q-table with a neural network.
  Q-table:  Q(s, a) = table_lookup(discretize(s), a)
  DQN:      Q(s, a) = neural_network(s)[a]

Key innovations: Experience Replay + Target Network.

Run:
  python dqn.py

Output shown on terminal only. No browser launched.
"""

import json
import random
from collections import deque

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from env import FirewallEnv
from data_loader import X_train, y_train


# ══════════════════════════════════════════════════════════════════════
# HYPER-PARAMETERS
# ══════════════════════════════════════════════════════════════════════
EPISODES           = 70
BATCH_SIZE         = 64
REPLAY_BUFFER      = 10_000
LEARNING_RATE      = 1e-3
DISCOUNT_FACTOR    = 0.95
EPSILON_START      = 1.0
EPSILON_END        = 0.05
EPSILON_DECAY      = 0.97
TARGET_UPDATE_FREQ = 500
N_FEATURES         = X_train.shape[1]
N_ACTIONS          = 3
LOG_PATH           = "dqn_rewards.json"


# ══════════════════════════════════════════════════════════════════════
# NEURAL NETWORK
# ══════════════════════════════════════════════════════════════════════
class QNetwork(nn.Module):
    def __init__(self, n_features: int, n_actions: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, n_actions),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# ══════════════════════════════════════════════════════════════════════
# REPLAY BUFFER
# ══════════════════════════════════════════════════════════════════════
class ReplayBuffer:
    def __init__(self, capacity: int):
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done):
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, batch_size)
        states, actions, rewards, next_states, dones = zip(*batch)
        return (
            np.array(states,      dtype=np.float32),
            np.array(actions,     dtype=np.int64),
            np.array(rewards,     dtype=np.float32),
            np.array(next_states, dtype=np.float32),
            np.array(dones,       dtype=np.float32),
        )

    def __len__(self):
        return len(self.buffer)


# ══════════════════════════════════════════════════════════════════════
# DQN AGENT
# ══════════════════════════════════════════════════════════════════════
class DQNAgent:
    def __init__(self):
        self.device     = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.online_net = QNetwork(N_FEATURES, N_ACTIONS).to(self.device)
        self.target_net = QNetwork(N_FEATURES, N_ACTIONS).to(self.device)
        self.target_net.load_state_dict(self.online_net.state_dict())
        self.target_net.eval()
        self.optimizer  = optim.Adam(self.online_net.parameters(), lr=LEARNING_RATE)
        self.loss_fn    = nn.MSELoss()
        self.memory     = ReplayBuffer(REPLAY_BUFFER)
        self.epsilon    = EPSILON_START
        self.steps      = 0

    def select_action(self, state: np.ndarray) -> int:
        if np.random.rand() < self.epsilon:
            return np.random.randint(N_ACTIONS)
        state_t = torch.tensor(state, dtype=torch.float32).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q_values = self.online_net(state_t)
        return int(q_values.argmax().item())

    def store(self, state, action, reward, next_state, done):
        self.memory.push(state, action, reward, next_state, done)

    def learn(self):
        if len(self.memory) < BATCH_SIZE:
            return

        states, actions, rewards, next_states, dones = self.memory.sample(BATCH_SIZE)

        states_t      = torch.tensor(states,      device=self.device)
        actions_t     = torch.tensor(actions,     device=self.device)
        rewards_t     = torch.tensor(rewards,     device=self.device)
        next_states_t = torch.tensor(next_states, device=self.device)
        dones_t       = torch.tensor(dones,       device=self.device)

        q_pred = self.online_net(states_t).gather(1, actions_t.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            q_next   = self.target_net(next_states_t).max(1).values
            q_target = rewards_t + DISCOUNT_FACTOR * q_next * (1 - dones_t)

        loss = self.loss_fn(q_pred, q_target)
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.online_net.parameters(), max_norm=1.0)
        self.optimizer.step()

        self.steps += 1
        if self.steps % TARGET_UPDATE_FREQ == 0:
            self.target_net.load_state_dict(self.online_net.state_dict())

    def decay_epsilon(self):
        self.epsilon = max(EPSILON_END, self.epsilon * EPSILON_DECAY)


# ══════════════════════════════════════════════════════════════════════
# TRAINING LOOP
# ══════════════════════════════════════════════════════════════════════
def train():
    if not TORCH_AVAILABLE:
        print("PyTorch not installed.  Run:  pip install torch")
        print("DQN training skipped.")
        return []

    env   = FirewallEnv(X_train, y_train)
    agent = DQNAgent()
    rewards_log: list[float] = []

    print()
    print("=" * 65)
    print("  STEP 3 — DEEP Q-NETWORK (DQN) TRAINING")
    print("  Algorithm: Neural Network Q-Learning (educational)")
    print("=" * 65)
    print(f"  Episodes          : {EPISODES}")
    print(f"  Network           : {N_FEATURES} -> 128 -> 64 -> {N_ACTIONS}")
    print(f"  Replay buffer     : {REPLAY_BUFFER:,} transitions")
    print(f"  Batch size        : {BATCH_SIZE}")
    print(f"  Learning rate     : {LEARNING_RATE}")
    print(f"  Target net update : every {TARGET_UPDATE_FREQ} steps")
    print(f"  Device            : {agent.device}")
    print("=" * 65)

    for episode in range(EPISODES):
        state, _ = env.reset()
        total_reward = 0.0
        correct      = 0
        steps        = 0

        while True:
            action = agent.select_action(state)
            next_state, reward, done, _, _ = env.step(action)
            agent.store(state, action, reward, next_state, float(done))
            agent.learn()
            total_reward += reward
            if reward > 0:
                correct += 1
            steps  += 1
            state   = next_state
            if done:
                break

        rewards_log.append(round(total_reward, 2))
        agent.decay_epsilon()
        accuracy = correct / steps * 100 if steps else 0
        print(
            f"  Episode {episode + 1:>3}/{EPISODES}"
            f"  |  Reward: {total_reward:>10.1f}"
            f"  |  Accuracy: {accuracy:>5.1f}%"
            f"  |  ε: {agent.epsilon:.3f}"
            f"  |  Memory: {len(agent.memory):,}"
        )

    with open(LOG_PATH, "w") as f:
        json.dump(rewards_log, f)

    torch.save(agent.online_net.state_dict(), "dqn_firewall.pt")

    print("=" * 65)
    print("  DQN Training complete.")
    print(f"  Best episode reward : {max(rewards_log):.1f}")
    print(f"  Model saved         -> dqn_firewall.pt")
    print(f"  Reward log saved    -> {LOG_PATH}")
    print()
    print("  DQN vs Q-LEARNING SUMMARY:")
    print("  - Q-Learning : table lookup, discretised states, no generalisation")
    print("  - DQN        : neural net, continuous states, generalises to unseen inputs")
    print("  - PPO        : directly learns action probabilities (best performance)")
    print("=" * 65)
    print()
    print("  NEXT STEP:")
    print("  python train_ppo.py    <- Step 4: PPO training (production model)")
    print("=" * 65)

    return rewards_log


if __name__ == "__main__":
    train()