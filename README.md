---
title: Ai Adaptive Firewall
emoji: 🛡️
colorFrom: green
colorTo: black
sdk: docker
pinned: false
license: mit
short_description: AI-powered network intrusion detection with Q-Learning, DQN and PPO
---

# AI Adaptive Firewall Dashboard

A real-time network intrusion detection system powered by three
reinforcement learning algorithms, served via a Flask dashboard.

## Three RL Algorithms Compared

| Algorithm | File | How it works |
|---|---|---|
| Q-Learning | qlearning.py | Lookup TABLE of Q(state, action) values |
| DQN | dqn.py | Neural network approximates Q(s,a) |
| PPO (deployed) | train_ppo.py | Directly learns policy π(action\|state) |

## Dashboard Pages

| Page | What it shows |
|---|---|
| Dashboard | Upload CSV → Start → live packet stream |
| Analytics | Benign vs attack split, top attack types |
| Protection | CPU/memory/latency comparison |
| Intelligence | PPO reward trend, confusion matrix, AUC |
| Admin | Strict mode, auto-block, rate-limit threshold |

## Run locally

```bash
pip install -r requirements.txt
python data_loader.py
python train_ppo.py
python app.py
```