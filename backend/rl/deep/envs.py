"""
envs.py — curated registry of Gymnasium environments for the Deep RL workbench.

Only "classic control" environments are exposed: they ship with Gymnasium, need
no native compilation (no Box2D/MuJoCo), train in seconds-to-minutes on CPU, and
together cover both action-space kinds an analyst needs to see:

  - DISCRETE action spaces  (CartPole, MountainCar, Acrobot)  -> DQN / PPO / A2C
  - CONTINUOUS action spaces (Pendulum, MountainCarContinuous) -> PPO / A2C

Each entry carries the facts the UI and the AI helper reason about — observation
dimensionality, action kind, the reward threshold that counts as "solved", and a
one-line goal — WITHOUT any user-facing prose (labels/descriptions live in the
frontend i18n ``reinforcement`` namespace, keyed by the env id).
"""

from __future__ import annotations

DISCRETE = "discrete"
CONTINUOUS = "continuous"

# Ordered so the cockpit's own domain (cyber defense) comes first, then the
# standard control benchmarks from gentlest to hardest.
_ENVS = [
    {
        # Threshold calibrated empirically: a random policy scores ~ -29, a
        # well-trained agent ~ +40, so +30 marks a genuinely mastered policy.
        "id": "AlertTriage-v0", "group": "cyber_defense", "action_kind": DISCRETE,
        "obs_dim": 4, "n_actions": 3, "max_steps": 50,
        "reward_threshold": 30.0, "reward_range": [-300.0, 200.0],
    },
    {
        "id": "CartPole-v1", "group": "classic_control", "action_kind": DISCRETE,
        "obs_dim": 4, "n_actions": 2, "max_steps": 500,
        "reward_threshold": 475.0, "reward_range": [0.0, 500.0],
    },
    {
        "id": "Acrobot-v1", "group": "classic_control", "action_kind": DISCRETE,
        "obs_dim": 6, "n_actions": 3, "max_steps": 500,
        "reward_threshold": -100.0, "reward_range": [-500.0, 0.0],
    },
    {
        "id": "MountainCar-v0", "group": "classic_control", "action_kind": DISCRETE,
        "obs_dim": 2, "n_actions": 3, "max_steps": 200,
        "reward_threshold": -110.0, "reward_range": [-200.0, 0.0],
    },
    {
        "id": "Pendulum-v1", "group": "classic_control", "action_kind": CONTINUOUS,
        "obs_dim": 3, "action_dim": 1, "max_steps": 200,
        "reward_threshold": None, "reward_range": [-1600.0, 0.0],
    },
    {
        "id": "MountainCarContinuous-v0", "group": "classic_control", "action_kind": CONTINUOUS,
        "obs_dim": 2, "action_dim": 1, "max_steps": 999,
        "reward_threshold": 90.0, "reward_range": [-100.0, 100.0],
    },
]

_ENVS_BY_ID = {e["id"]: e for e in _ENVS}


def list_envs() -> list:
    """All exposed environments, in display order (list of metadata dicts)."""
    return list(_ENVS)


def get_env(env_id: str):
    """Environment metadata by id, or ``None`` if it is not in the registry."""
    return _ENVS_BY_ID.get(env_id)


def action_kind(env_id: str):
    """``'discrete'`` / ``'continuous'`` for a known env, else ``None``."""
    meta = _ENVS_BY_ID.get(env_id)
    return meta["action_kind"] if meta else None
