"""
env.py — FirewallEnv (IMPROVED FOR BETTER Q-LEARNING PERFORMANCE)
================================================================

Observation space : 8 continuous features in [0, 1]
Action space      : Discrete(3)
                      0 → ALLOW
                      1 → BLOCK
                      2 → RATE-LIMIT

Improved reward logic:

ATTACK traffic:
    +6  correct BLOCK
    +1  RATE-LIMIT (partial defense)
    -8  ALLOW (worst mistake)

BENIGN traffic:
    +4  correct ALLOW
    -3  BLOCK (false alarm)
    -1  RATE-LIMIT (unnecessary)

Why this works better:
    Q-learning needs stronger reward signals to learn patterns.
    Detecting attacks must give clearly higher benefit than always allowing traffic.
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np


class FirewallEnv(gym.Env):

    metadata = {"render_modes": []}

    def __init__(self, X: np.ndarray, y: np.ndarray):

        super().__init__()

        self.X = X.astype(np.float32)
        self.y = y

        self.index = 0

        self.observation_space = spaces.Box(

            low=0.0,
            high=1.0,
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

        # ===============================
        # IMPROVED REWARD FUNCTION
        # ===============================

        if label == 1:  # ATTACK traffic

            if action == 1:
                reward = +6      # correct block (strong reward)

            elif action == 2:
                reward = +1      # partial defense

            else:
                reward = -8      # allowed attack (worst)

        else:  # BENIGN traffic

            if action == 0:
                reward = +4      # correct allow

            elif action == 1:
                reward = -3      # false positive

            else:
                reward = -1      # unnecessary rate limit


        # move to next packet
        self.index += 1

        terminated = self.index >= len(self.X) - 1

        next_obs = self.X[self.index] if not terminated else self.X[0]

        return next_obs, reward, terminated, False, {}