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
        "obs_dim": 4, "n_actions": 3, "max_steps": 50, "maskable": True,
        "reward_threshold": 30.0, "reward_range": [-300.0, 200.0],
    },
    {
        # Spreading-incident containment: state evolves over time, no fixed
        # "solved" threshold — quality is judged against the random baseline.
        "id": "IncidentContainment-v0", "group": "cyber_defense", "action_kind": DISCRETE,
        "obs_dim": 4, "n_actions": 3, "max_steps": 60,
        "reward_threshold": None, "reward_range": [-250.0, 25.0],
    },
    {
        # Online IDS threshold tuning: a CONTINUOUS action (nudge the threshold),
        # so SAC / TD3 / DDPG / CrossQ / TQC finally apply to a cyber problem.
        "id": "ThresholdTuning-v0", "group": "cyber_defense", "action_kind": CONTINUOUS,
        "obs_dim": 4, "action_dim": 1, "max_steps": 80,
        "reward_threshold": None, "reward_range": [-6.0, 2.0],
    },
    {
        # SOC staffing: dispatch incidents to a scarce senior pool. Maskable
        # (ASSIGN_SENIOR is invalid when every senior is busy).
        "id": "AnalystAssignment-v0", "group": "cyber_defense", "action_kind": DISCRETE,
        "obs_dim": 4, "n_actions": 3, "max_steps": 50, "maskable": True,
        "reward_threshold": None, "reward_range": [-200.0, 300.0],
    },
    {
        # Vulnerability management: spend scarce emergency maintenance windows
        # on the findings most likely to be exploited (CVSS / KEV / exposure).
        # Maskable (EMERGENCY is invalid once every window is spent).
        "id": "PatchPrioritization-v0", "group": "cyber_defense", "action_kind": DISCRETE,
        "obs_dim": 4, "n_actions": 3, "max_steps": 50, "maskable": True,
        "reward_threshold": None, "reward_range": [-300.0, 250.0],
    },
    {
        # Optimal stopping: investigate a case until the evidence justifies
        # closing or escalating. Partially observable — RecurrentPPO shines.
        "id": "CaseInvestigation-v0", "group": "cyber_defense", "action_kind": DISCRETE,
        "obs_dim": 4, "n_actions": 3, "max_steps": 60,
        "reward_threshold": None, "reward_range": [-400.0, 300.0],
    },
    {
        # NOC congestion triage under a spare-path budget — the network sibling
        # of AlertTriage. Maskable (REROUTE invalid once the budget is spent).
        "id": "TrafficRerouting-v0", "group": "noc_ops", "action_kind": DISCRETE,
        "obs_dim": 4, "n_actions": 3, "max_steps": 50, "maskable": True,
        "reward_threshold": None, "reward_range": [-300.0, 200.0],
    },
    {
        # Online capacity dimensioning: a CONTINUOUS action (scale capacity),
        # so SAC / TD3 / DDPG / CrossQ / TQC apply to a network problem.
        "id": "CapacityScaling-v0", "group": "noc_ops", "action_kind": CONTINUOUS,
        "obs_dim": 4, "action_dim": 1, "max_steps": 80,
        "reward_threshold": None, "reward_range": [-6.0, 2.0],
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

# User-imported environments (e.g. a CSV-backed triage env), registered at
# runtime by :mod:`rl.deep.custom_envs`. Kept separate from the curated built-ins
# so they can be listed with a ``custom`` flag and removed independently.
_CUSTOM: list = []
_CUSTOM_BY_ID: dict = {}


def register_custom(meta: dict) -> None:
    """Add (or replace) a user-imported environment in the catalogue."""
    env_id = meta["id"]
    if env_id in _CUSTOM_BY_ID:
        _CUSTOM[:] = [e for e in _CUSTOM if e["id"] != env_id]
    _CUSTOM.append(meta)
    _CUSTOM_BY_ID[env_id] = meta


def unregister_custom(env_id: str) -> bool:
    """Remove a user-imported environment from the catalogue."""
    if env_id not in _CUSTOM_BY_ID:
        return False
    _CUSTOM[:] = [e for e in _CUSTOM if e["id"] != env_id]
    _CUSTOM_BY_ID.pop(env_id, None)
    return True


def list_envs() -> list:
    """All exposed environments, in display order — built-ins then user imports."""
    return list(_ENVS) + list(_CUSTOM)


def get_env(env_id: str):
    """Environment metadata by id, or ``None`` if it is not in the registry."""
    return _ENVS_BY_ID.get(env_id) or _CUSTOM_BY_ID.get(env_id)


def action_kind(env_id: str):
    """``'discrete'`` / ``'continuous'`` for a known env, else ``None``."""
    meta = get_env(env_id)
    return meta["action_kind"] if meta else None


def is_maskable(env_id: str) -> bool:
    """Whether the env exposes an action mask (required by MaskablePPO)."""
    meta = get_env(env_id)
    return bool(meta and meta.get("maskable"))
