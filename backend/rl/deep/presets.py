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
        # Showcases invalid-action masking: BLOCK is masked when the budget is spent.
        "id": "soc_triage_maskable", "group": "cyber_defense", "recommended": False,
        "env_id": "AlertTriage-v0", "algo": "MaskablePPO",
        "config": {"total_timesteps": 60000, "learning_rate": 0.0003,
                   "gamma": 0.99, "ent_coef": 0.01},
    },
    {
        # Temporal decision-making: contain a spreading incident before it hurts.
        "id": "incident_ppo", "group": "cyber_defense", "recommended": False,
        "env_id": "IncidentContainment-v0", "algo": "PPO",
        "config": {"total_timesteps": 80000, "learning_rate": 0.0003,
                   "gamma": 0.995, "ent_coef": 0.01},
    },
    {
        # Continuous cyber control: online IDS threshold tuning under drift (SAC).
        "id": "threshold_sac", "group": "cyber_defense", "recommended": False,
        "env_id": "ThresholdTuning-v0", "algo": "SAC",
        "config": {"total_timesteps": 40000, "learning_rate": 0.0007,
                   "gamma": 0.98, "tau": 0.01, "buffer_size": 100000},
    },
    {
        # SOC staffing under a scarce senior pool; masking makes the constraint hard.
        "id": "soc_assign_maskable", "group": "cyber_defense", "recommended": False,
        "env_id": "AnalystAssignment-v0", "algo": "MaskablePPO",
        "config": {"total_timesteps": 60000, "learning_rate": 0.0003,
                   "gamma": 0.99, "ent_coef": 0.01},
    },
    {
        # Vulnerability management under scarce emergency windows (KEV-driven).
        "id": "soc_patch_maskable", "group": "cyber_defense", "recommended": False,
        "env_id": "PatchPrioritization-v0", "algo": "MaskablePPO",
        "config": {"total_timesteps": 60000, "learning_rate": 0.0003,
                   "gamma": 0.99, "ent_coef": 0.01},
    },
    {
        # Partially observable investigation: the LSTM policy tracks evidence.
        "id": "soc_invest_recurrent", "group": "cyber_defense", "recommended": False,
        "env_id": "CaseInvestigation-v0", "algo": "RecurrentPPO",
        "config": {"total_timesteps": 80000, "learning_rate": 0.0003,
                   "gamma": 0.99},
    },
    {
        "id": "noc_reroute_dqn", "group": "noc_ops", "recommended": False,
        "env_id": "TrafficRerouting-v0", "algo": "DQN",
        "config": {"total_timesteps": 60000, "learning_rate": 0.0005,
                   "gamma": 0.99, "exploration_fraction": 0.2},
    },
    {
        # Invalid-action masking on the NOC side: REROUTE masked without spare paths.
        "id": "noc_reroute_maskable", "group": "noc_ops", "recommended": False,
        "env_id": "TrafficRerouting-v0", "algo": "MaskablePPO",
        "config": {"total_timesteps": 60000, "learning_rate": 0.0003,
                   "gamma": 0.99, "ent_coef": 0.01},
    },
    {
        # Continuous NOC control: online capacity dimensioning under bursty demand.
        "id": "noc_capacity_sac", "group": "noc_ops", "recommended": False,
        "env_id": "CapacityScaling-v0", "algo": "SAC",
        "config": {"total_timesteps": 40000, "learning_rate": 0.0007,
                   "gamma": 0.98, "tau": 0.01, "buffer_size": 100000},
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
    {
        "id": "pendulum_sac", "group": "classic_control", "recommended": False,
        "env_id": "Pendulum-v1", "algo": "SAC",
        "config": {"total_timesteps": 20000, "learning_rate": 0.001,
                   "gamma": 0.99, "tau": 0.005, "buffer_size": 100000},
    },
    {
        "id": "pendulum_crossq", "group": "classic_control", "recommended": False,
        "env_id": "Pendulum-v1", "algo": "CrossQ",
        "config": {"total_timesteps": 20000, "learning_rate": 0.001,
                   "gamma": 0.99, "buffer_size": 100000},
    },
]


def list_presets() -> list:
    """All presets, cyber-defense first (list of metadata dicts)."""
    return list(_PRESETS)
