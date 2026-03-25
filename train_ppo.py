"""
train_ppo.py — Algorithm 3: PPO (Proximal Policy Optimization)
===============================================================

PPO directly learns a policy π(a|s) — probability of each action.
Uses clipped updates for stable training.

CHANGES vs original (for higher accuracy):
  - PHASES: 10 → 30  (more training = better convergence)
  - learning_rate: 3e-4 → 1e-4  (slower = more precise)
  - n_steps: 2048 → 4096  (larger rollouts = better gradients)
  - clip_range: 0.20 → 0.15  (tighter = more stable)
  - ent_coef: 0.005 added  (prevents premature convergence)
  - net_arch: [256, 256, 128]  (deeper network = more capacity)

Run:
  python train_ppo.py

Output shown on terminal only. No browser launched.
Produces:
  adaptive_firewall_ppo.zip   (loaded by app.py at startup)
  reward_log.npy              (displayed in dashboard Intelligence tab)
"""

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from env import FirewallEnv
from data_loader import X_train, y_train

# ══════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════
PHASES              = 10      # was 10 → more phases = better convergence
TIMESTEPS_PER_PHASE = 20_000      # steps per phase  (600K total)
EVAL_STEPS          = 5_000       # evaluation steps per phase

PPO_CONFIG = dict(
    policy        = "MlpPolicy",
    learning_rate = 1e-4,         # was 3e-4 → slower, more precise
    batch_size    = 256,
    n_steps       = 4096,         # was 2048 → bigger rollouts
    gamma         = 0.99,
    clip_range    = 0.15,         # was 0.20 → tighter clipping
    ent_coef      = 0.005,        # NEW: entropy bonus
    verbose       = 1,
    policy_kwargs = dict(
        net_arch  = [256, 256, 128]   # NEW: deeper network
    ),
)

MODEL_PATH  = "adaptive_firewall_ppo"
REWARD_PATH = "reward_log.npy"


# ══════════════════════════════════════════════════════════════════════
# TRAINING
# ══════════════════════════════════════════════════════════════════════
def train():
    env   = FirewallEnv(X_train, y_train)
    model = PPO(env=env, **PPO_CONFIG)

    rewards_log: list[float] = []

    print()
    print("=" * 65)
    print("  STEP 4 — PPO TRAINING  (PRODUCTION MODEL)")
    print("  Algorithm: Proximal Policy Optimization")
    print("=" * 65)
    print(f"  Phases            : {PHASES} x {TIMESTEPS_PER_PHASE:,} steps")
    print(f"  Total timesteps   : {PHASES * TIMESTEPS_PER_PHASE:,}")
    print(f"  Learning rate     : {PPO_CONFIG['learning_rate']}  (reduced for precision)")
    print(f"  Batch size        : {PPO_CONFIG['batch_size']}")
    print(f"  n_steps           : {PPO_CONFIG['n_steps']}  (larger rollouts)")
    print(f"  PPO clip range    : {PPO_CONFIG['clip_range']}  (tighter for stability)")
    print(f"  Entropy coeff     : {PPO_CONFIG['ent_coef']}  (prevents early convergence)")
    print(f"  Network arch      : {PPO_CONFIG['policy_kwargs']['net_arch']}")
    print(f"  Actions           : 0=ALLOW  1=BLOCK  2=RATE-LIMIT")
    print("=" * 65)
    print()
    print("  HOW PPO DIFFERS FROM Q-LEARNING AND DQN:")
    print()
    print("  Q-Learning  stores a TABLE of Q(state, action) values.")
    print("              Needs discrete states. Cannot generalise.")
    print()
    print("  DQN         uses a NEURAL NETWORK to approximate Q(s,a).")
    print("              Handles continuous states. Uses replay buffer.")
    print()
    print("  PPO         directly learns the POLICY π(action|state).")
    print("              Outputs action probabilities, not Q-values.")
    print("              Uses clipped updates for stable training.")
    print("              Best generalisation — this is what we deploy.")
    print()
    print("=" * 65)

    for phase in range(PHASES):
        model.learn(
            total_timesteps=TIMESTEPS_PER_PHASE,
            reset_num_timesteps=(phase == 0),
        )

        # Evaluate phase
        eval_state, _ = env.reset()
        total_reward  = 0.0
        correct       = 0

        for step in range(EVAL_STEPS):
            action, _ = model.predict(eval_state, deterministic=True)
            eval_state, reward, done, _, _ = env.step(int(action))
            total_reward += reward
            if reward > 0:
                correct += 1
            if done:
                break

        accuracy = correct / EVAL_STEPS * 100
        rewards_log.append(float(total_reward))

        print(
            f"  Phase {phase + 1:>2}/{PHASES}"
            f"  |  Eval reward: {total_reward:>10.1f}"
            f"  |  Accuracy: {accuracy:>5.1f}%"
            f"  |  Timesteps: {(phase+1)*TIMESTEPS_PER_PHASE:,}"
        )

    # Save
    model.save(MODEL_PATH)
    np.save(REWARD_PATH, np.array(rewards_log))

    print("=" * 65)
    print(f"  PPO Training complete.")
    print(f"  Best phase reward  : {max(rewards_log):.1f}")
    print(f"  Final phase reward : {rewards_log[-1]:.1f}")
    print(f"  Model saved        -> {MODEL_PATH}.zip")
    print(f"  Reward log saved   -> {REWARD_PATH}")
    print()
    print("  NEXT STEP:")
    print("  python app.py    <- Step 5: Launch Flask dashboard")
    print("                      Open http://localhost:5000")
    print("=" * 65)

    return rewards_log


if __name__ == "__main__":
    train()