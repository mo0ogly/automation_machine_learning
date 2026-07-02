"""
algos.py — registry of Deep RL algorithms (Stable-Baselines3) and their tunable
hyperparameters for the Deep RL workbench.

Three algorithms, chosen to contrast the two families an analyst should know:

  - PPO  (on-policy, actor-critic)  — robust default, discrete AND continuous.
  - A2C  (on-policy, actor-critic)  — simpler/faster cousin of PPO, both kinds.
  - DQN  (off-policy, value-based)  — the deep counterpart of tabular Q-learning;
                                       DISCRETE action spaces only.

Each algorithm declares which action kinds it supports (so the UI can grey out
DQN on a continuous env) and a hyperparameter *schema* — the same ``{name, label,
type, min, max, step, default, help}`` shape the pipeline stages use, so the
existing per-field AI helper and slider widgets work unchanged.

``build_kwargs`` maps a validated config to the SB3 constructor keyword args,
clamping every value to its schema bounds so a hand-crafted request can never
pass out-of-range hyperparameters to the trainer.
"""

from __future__ import annotations

from .envs import DISCRETE, CONTINUOUS

# Shared hyperparameters, present for every algorithm.
_COMMON_FIELDS = [
    {"name": "total_timesteps", "label": "Pas d'entraînement", "type": "range",
     "min": 2000, "max": 200000, "step": 1000, "default": 30000,
     "help": "Nombre total d'interactions agent-environnement. Plus = meilleure "
             "politique mais entraînement plus long (quelques secondes à quelques minutes)."},
    {"name": "learning_rate", "label": "Taux d'apprentissage", "type": "range",
     "min": 0.0001, "max": 0.01, "step": 0.0001, "default": 0.0003,
     "help": "Pas de descente de gradient du réseau. Haut = apprend vite mais "
             "instable ; bas = lent mais stable."},
    {"name": "gamma", "label": "Facteur d'actualisation (gamma)", "type": "range",
     "min": 0.8, "max": 0.999, "step": 0.001, "default": 0.99,
     "help": "Poids des récompenses futures : proche de 1 = vision long terme ; "
             "plus bas = privilégie le gain immédiat."},
]

# Per-algorithm extra field + which action kinds the algorithm accepts.
_ALGOS = {
    "PPO": {
        "id": "PPO", "family": "on-policy (acteur-critique)",
        "action_kinds": [DISCRETE, CONTINUOUS],
        "fields": _COMMON_FIELDS + [
            {"name": "ent_coef", "label": "Coefficient d'entropie", "type": "range",
             "min": 0.0, "max": 0.05, "step": 0.005, "default": 0.0,
             "help": "Encourage l'exploration en pénalisant les politiques trop "
                     "sûres d'elles. 0 = aucune incitation ; augmenter si l'agent "
                     "converge trop vite vers une mauvaise stratégie."},
        ],
    },
    "A2C": {
        "id": "A2C", "family": "on-policy (acteur-critique)",
        "action_kinds": [DISCRETE, CONTINUOUS],
        "fields": _COMMON_FIELDS + [
            {"name": "ent_coef", "label": "Coefficient d'entropie", "type": "range",
             "min": 0.0, "max": 0.05, "step": 0.005, "default": 0.0,
             "help": "Encourage l'exploration en pénalisant les politiques trop "
                     "sûres d'elles. 0 = aucune incitation."},
        ],
    },
    "DQN": {
        "id": "DQN", "family": "off-policy (basé sur la valeur)",
        "action_kinds": [DISCRETE],
        "fields": _COMMON_FIELDS + [
            {"name": "exploration_fraction", "label": "Fraction d'exploration", "type": "range",
             "min": 0.05, "max": 0.5, "step": 0.05, "default": 0.1,
             "help": "Part de l'entraînement où epsilon décroît de 1 vers sa valeur "
                     "finale (exploration vs exploitation). L'équivalent Deep du "
                     "epsilon-greedy du Q-learning tabulaire."},
        ],
    },
}

_ORDER = ["PPO", "DQN", "A2C"]


def list_algos() -> list:
    """All algorithms, in display order (metadata + hyperparameter schema)."""
    return [_ALGOS[name] for name in _ORDER]


def get_algo(name: str):
    """Algorithm metadata by name, or ``None`` if unknown."""
    return _ALGOS.get(name)


def fields_for(name: str) -> list:
    """The hyperparameter schema of one algorithm (empty list if unknown)."""
    algo = _ALGOS.get(name)
    return list(algo["fields"]) if algo else []


def supports(name: str, kind: str) -> bool:
    """Whether algorithm ``name`` accepts an action space of ``kind``."""
    algo = _ALGOS.get(name)
    return bool(algo and kind in algo["action_kinds"])


def _clamp_to_field(field: dict, value):
    lo, hi = field.get("min"), field.get("max")
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = float(field.get("default", 0.0))
    if lo is not None:
        v = max(v, float(lo))
    if hi is not None:
        v = min(v, float(hi))
    # total_timesteps is an integer count; everything else stays float.
    return int(round(v)) if field["name"] == "total_timesteps" else v


def build_kwargs(name: str, config: dict) -> dict:
    """Validated, clamped ``{field: value}`` for every field of the algorithm.

    Unknown fields in ``config`` are ignored; missing ones fall back to the
    schema default. ``total_timesteps`` is returned alongside the constructor
    kwargs — the caller pops it before instantiating the model.
    """
    cfg = config or {}
    out = {}
    for field in fields_for(name):
        out[field["name"]] = _clamp_to_field(field, cfg.get(field["name"], field.get("default")))
    return out
