"""
env.py — FirewallEnv
=====================
Custom Gymnasium environment shared by ALL three RL algorithms:
  • Q-Learning   (qlearning.py)
  • DQN          (dqn.py)
  • PPO          (train_ppo.py)

Observation space : 8 continuous features in [0, 1]
Action space      : Discrete(3)
                      0 → ALLOW
                      1 → BLOCK
                      2 → RATE-LIMIT

Reward structure (UPDATED for higher accuracy):
  +3  correct block   (attack detected, action = BLOCK)      ← was +2
  +2  correct allow   (benign traffic, action = ALLOW)
  -5  missed attack   (attack traffic allowed through)        ← was -3
  -2  false positive  (benign traffic blocked)                ← was -3
  -2  rate-limited    (any traffic; suboptimal fallback)      ← was -1

WHY ASYMMETRIC REWARDS?
  Missed attacks (-5) carry the heaviest penalty because allowing a real
  attack through is the worst firewall failure. Correct blocks (+3) get
  a bigger reward to reinforce attack detection. False positives (-2) are
  penalised less than missed attacks — blocking benign traffic is bad,
  but less dangerous than missing an attack. Rate-limiting (-2) is penalised
  more than before to push the model toward decisive ALLOW/BLOCK decisions.
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np


class FirewallEnv(gym.Env):
    """
    Stateful sequential environment: each step() presents one packet
    (feature row) and expects an action. Walks through the dataset once
    per episode.
    """

    metadata = {"render_modes": []}

    def __init__(self, X: np.ndarray, y: np.ndarray):
        """
        Parameters
        ----------
        X : np.ndarray, shape (n_samples, n_features)
            MinMax-scaled feature matrix from data_loader.py.
        y : np.ndarray, shape (n_samples,)
            Binary labels — 0 = BENIGN, 1 = ATTACK.
        """
        super().__init__()

        self.X     = X.astype(np.float32)
        self.y     = y
        self.index = 0

        self.observation_space = spaces.Box(
            low=0.0, high=1.0,
            shape=(X.shape[1],),
            dtype=np.float32,
        )

        self.action_space = spaces.Discrete(3)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.index = 0
        return self.X[self.index], {}

    def step(self, action: int):
        label = int(self.y[self.index])

        # Updated reward structure (asymmetric for higher accuracy)
        if label == 1 and action == 1:
            reward = +3   # Attack correctly blocked     ← was +2
        elif label == 0 and action == 0:
            reward = +2   # Benign correctly allowed
        elif label == 1 and action == 0:
            reward = -5   # Missed attack (worst error)  ← was -3
        elif label == 0 and action == 1:
            reward = -2   # False positive               ← was -3
        else:
            reward = -2   # Rate-limited (lazy fallback) ← was -1

        self.index += 1
        terminated = self.index >= len(self.X) - 1
        next_obs   = self.X[self.index] if not terminated else self.X[0]

        return next_obs, reward, terminated, False, {}