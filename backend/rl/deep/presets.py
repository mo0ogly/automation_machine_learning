"""
presets.py — ready-to-train Deep RL "base models", the counterpart of the demo
datasets offered for the supervised/unsupervised pipeline.

Each preset pins an environment + algorithm + hyperparameters so an analyst can
train (and then download) a sensible agent in one click, without tuning first.
Cyber-defense presets come first (the cockpit's domain); the classic-control
ones are kept as gentle, fast-to-solve learning references.

User-facing labels/descriptions are NOT here — they live in the frontend i18n
``reinforcement`` namespace, keyed by preset id, so the UI stays translatable.
"""

from __future__ import annotations

_PRESETS = [
    {
        "id": "soc_triage_dqn", "group": "cyber_defense", "recommended": True,
        "env_id": "AlertTriage-v0", "algo": "DQN",
        "config": {"total_timesteps": 60000, "learning_rate": 0.0005,
                   "gamma": 0.99, "exploration_fraction": 0.2},
    },
    {
        "id": "soc_triage_ppo", "group": "cyber_defense", "recommended": False,
        "env_id": "AlertTriage-v0", "algo": "PPO",
        "config": {"total_timesteps": 60000, "learning_rate": 0.0003,
                   "gamma": 0.99, "ent_coef": 0.01},
    },
    {
        "id": "cartpole_ppo", "group": "classic_control", "recommended": False,
        "env_id": "CartPole-v1", "algo": "PPO",
        "config": {"total_timesteps": 40000, "learning_rate": 0.0003, "gamma": 0.99},
    },
    {
        "id": "pendulum_ppo", "group": "classic_control", "recommended": False,
        "env_id": "Pendulum-v1", "algo": "PPO",
        "config": {"total_timesteps": 60000, "learning_rate": 0.0003, "gamma": 0.99},
    },
]


def list_presets() -> list:
    """All presets, cyber-defense first (list of metadata dicts)."""
    return list(_PRESETS)
