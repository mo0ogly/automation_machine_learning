"""Deep RL workbench (Gymnasium + Stable-Baselines3), the realistic-scale
counterpart to the tabular GridWorld/Q-learning demo.

Trains DQN / PPO / A2C agents on continuous-state Gymnasium environments in a
background job, and exposes the algorithm/env registries + hyperparameter schema
the UI and the AI helper reason about. Heavy imports (torch) stay lazy: importing
this package only touches the registries, not stable_baselines3.
"""

from . import envs, algos, jobs, cyber_envs, presets

# Register the custom cyber-defense environments with Gymnasium at import time so
# gym.make("AlertTriage-v0") works wherever the package is loaded.
cyber_envs.register()

__all__ = ["envs", "algos", "jobs", "cyber_envs", "presets", "catalog", "deep_rl_fields"]


def catalog() -> dict:
    """Everything the UI needs to render the workbench: the environment list, the
    algorithm list (with per-algorithm hyperparameter schema + supported action
    kinds), and the ready-to-train presets ("base models")."""
    return {"envs": envs.list_envs(), "algos": algos.list_algos(),
            "presets": presets.list_presets()}


def deep_rl_fields() -> list:
    """Union of every algorithm's hyperparameter fields, de-duplicated by name.

    Used by the ``/explain`` route so the AI helper can describe any slider
    regardless of which algorithm is selected."""
    seen, out = set(), []
    for algo in algos.list_algos():
        for field in algo["fields"]:
            if field["name"] not in seen:
                seen.add(field["name"])
                out.append(field)
    return out
