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

# Extra fields shared by the off-policy continuous-control algorithms (SAC/TD3/DDPG),
# which learn from a replay buffer with a soft target-network update.
_OFFPOLICY_CONT_FIELDS = [
    {"name": "tau", "label": "Mise à jour douce (tau)", "type": "range",
     "min": 0.001, "max": 0.02, "step": 0.001, "default": 0.005,
     "help": "Vitesse de rapprochement du réseau cible vers le réseau courant. "
             "Petit = cible stable mais lente ; grand = plus réactif mais instable."},
    {"name": "buffer_size", "label": "Taille du tampon de rejeu", "type": "range",
     "min": 10000, "max": 1000000, "step": 10000, "default": 100000,
     "help": "Nombre de transitions passées gardées en mémoire pour ré-apprentissage "
             "(replay buffer). Plus grand = plus de recul mais plus de mémoire."},
]

# On-policy exploration knob (PPO / A2C / RecurrentPPO / MaskablePPO).
_ENT_COEF_FIELD = {
    "name": "ent_coef", "label": "Coefficient d'entropie", "type": "range",
    "min": 0.0, "max": 0.05, "step": 0.005, "default": 0.0,
    "help": "Encourage l'exploration en pénalisant les politiques trop sûres "
            "d'elles. 0 = aucune incitation ; augmenter si l'agent converge trop "
            "vite vers une mauvaise stratégie."}

# ARS is gradient-free (random search): it has neither gamma nor entropy, but a
# perturbation scale (delta_std) and a larger learning rate than the SGD algos.
_ARS_FIELDS = [
    {"name": "total_timesteps", "label": "Pas d'entraînement", "type": "range",
     "min": 2000, "max": 200000, "step": 1000, "default": 40000,
     "help": "Nombre total d'interactions agent-environnement. Plus = meilleure "
             "politique mais entraînement plus long."},
    {"name": "learning_rate", "label": "Taux d'apprentissage", "type": "range",
     "min": 0.005, "max": 0.05, "step": 0.005, "default": 0.02,
     "help": "Pas de mise à jour de la politique le long des perturbations. ARS "
             "tolère un taux bien plus grand que les méthodes à gradient."},
    {"name": "delta_std", "label": "Amplitude des perturbations (delta)", "type": "range",
     "min": 0.01, "max": 0.1, "step": 0.01, "default": 0.05,
     "help": "Écart-type du bruit ajouté aux poids pour explorer. Grand = "
             "exploration large mais bruitée ; petit = fin mais lent."},
]

# Field names carrying an integer count (rounded when clamped).
_INT_FIELDS = {"total_timesteps", "buffer_size"}

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
    "SAC": {
        "id": "SAC", "family": "off-policy (acteur-critique, entropie maximale)",
        "action_kinds": [CONTINUOUS],
        "fields": _COMMON_FIELDS + _OFFPOLICY_CONT_FIELDS,
    },
    "TD3": {
        "id": "TD3", "family": "off-policy (acteur-critique, double critique)",
        "action_kinds": [CONTINUOUS],
        "fields": _COMMON_FIELDS + _OFFPOLICY_CONT_FIELDS,
    },
    "DDPG": {
        "id": "DDPG", "family": "off-policy (acteur-critique déterministe)",
        "action_kinds": [CONTINUOUS],
        "fields": _COMMON_FIELDS + _OFFPOLICY_CONT_FIELDS,
    },
    # --- sb3-contrib (separate package) ---
    "QRDQN": {
        "id": "QRDQN", "family": "off-policy (valeur, distributionnel)", "contrib": True,
        "action_kinds": [DISCRETE],
        "fields": _COMMON_FIELDS + [
            {"name": "exploration_fraction", "label": "Fraction d'exploration", "type": "range",
             "min": 0.05, "max": 0.5, "step": 0.05, "default": 0.1,
             "help": "Part de l'entraînement où epsilon décroît (exploration vs "
                     "exploitation). QRDQN étend DQN en apprenant la distribution des "
                     "retours plutôt que leur seule moyenne."},
        ],
    },
    "TRPO": {
        "id": "TRPO", "family": "on-policy (région de confiance)", "contrib": True,
        "action_kinds": [DISCRETE, CONTINUOUS],
        "fields": _COMMON_FIELDS,
    },
    "TQC": {
        "id": "TQC", "family": "off-policy (critiques quantiles tronqués)", "contrib": True,
        "action_kinds": [CONTINUOUS],
        "fields": _COMMON_FIELDS + _OFFPOLICY_CONT_FIELDS,
    },
    "RecurrentPPO": {
        "id": "RecurrentPPO", "family": "on-policy récurrent (LSTM)", "contrib": True,
        "action_kinds": [DISCRETE, CONTINUOUS],
        "fields": _COMMON_FIELDS + [_ENT_COEF_FIELD],
    },
    "ARS": {
        "id": "ARS", "family": "sans gradient (recherche aléatoire)", "contrib": True,
        "action_kinds": [DISCRETE, CONTINUOUS],
        "fields": _ARS_FIELDS,
    },
    "CrossQ": {
        # Off-policy continuous control; drops target networks (no tau), keeps a
        # replay buffer — often more sample-efficient than SAC.
        "id": "CrossQ", "family": "off-policy (sans réseau cible, BatchNorm)", "contrib": True,
        "action_kinds": [CONTINUOUS],
        "fields": _COMMON_FIELDS + [
            {"name": "buffer_size", "label": "Taille du tampon de rejeu", "type": "range",
             "min": 10000, "max": 1000000, "step": 10000, "default": 100000,
             "help": "Nombre de transitions passées gardées en mémoire pour "
                     "ré-apprentissage. Plus grand = plus de recul mais plus de mémoire."},
        ],
    },
    "MaskablePPO": {
        # PPO with invalid-action masking; only meaningful on envs that expose an
        # action mask (``requires_mask``), e.g. the SOC triage envs.
        "id": "MaskablePPO", "family": "on-policy (PPO avec masquage d'actions)",
        "contrib": True, "requires_mask": True,
        "action_kinds": [DISCRETE],
        "fields": _COMMON_FIELDS + [_ENT_COEF_FIELD],
    },
}

_ORDER = ["PPO", "DQN", "A2C", "SAC", "TD3", "DDPG",
          "QRDQN", "TRPO", "TQC", "RecurrentPPO", "ARS", "CrossQ", "MaskablePPO"]


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


def requires_mask(name: str) -> bool:
    """Whether the algorithm needs an action-mask-capable env (MaskablePPO)."""
    algo = _ALGOS.get(name)
    return bool(algo and algo.get("requires_mask"))


def compatible(name: str, kind: str, maskable: bool = False) -> bool:
    """Full compatibility check: action space AND (for MaskablePPO) that the env
    exposes an action mask."""
    if not supports(name, kind):
        return False
    return bool(maskable) if requires_mask(name) else True


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
    # integer counts (steps, buffer size) are rounded; everything else stays float.
    return int(round(v)) if field["name"] in _INT_FIELDS else v


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
