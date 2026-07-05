"""
evaluate.py — evaluate a saved Deep RL agent on an environment, without training.

Powers two workbench actions on a stored/imported model:
  - "evaluate" — run the greedy policy for N episodes and report the same metrics
    + reward distribution as a fresh training run (minus the learning curve);
  - the compatibility guard used before "continue training".

Loading a Stable-Baselines3 ``.zip`` needs the concrete algorithm class, so the
caller passes the algorithm name (known from the registry / import form). The
observation space of the saved policy is checked against the target env so a
mismatched model fails with a clear message instead of a deep SB3 traceback.
"""

from __future__ import annotations

import time

from . import algos as algo_registry
from . import envs as env_registry
from . import cyber_envs
from . import noc_envs
from . import train as trainer


def _obs_dim(space):
    shape = getattr(space, "shape", None)
    return int(shape[0]) if shape else None


def check_compatible(env_id, algo_name, model_zip):
    """Validate that ``model_zip`` (an ``algo_name`` agent) can run on ``env_id``.

    Returns the env metadata on success; raises ``ValueError`` otherwise. Used by
    both evaluate and continue-training so the mismatch is caught up front.
    """
    cyber_envs.register()
    noc_envs.register()
    meta = env_registry.get_env(env_id)
    if meta is None:
        raise ValueError(f"Environnement inconnu : {env_id}")
    if not algo_registry.compatible(algo_name, meta["action_kind"], meta.get("maskable")):
        raise ValueError(
            f"{algo_name} n'est pas compatible avec l'environnement {env_id} "
            f"(action {meta['action_kind']}, masquable={bool(meta.get('maskable'))}).")
    model = trainer.algo_class(algo_name).load(model_zip, device="cpu")
    got = _obs_dim(model.observation_space)
    want = meta.get("obs_dim")
    if got is not None and want is not None and got != want:
        raise ValueError(
            f"Modèle incompatible : il attend une observation de dimension {got}, "
            f"mais {env_id} en fournit {want}. Choisissez un environnement de même dimension.")
    return meta, model


def evaluate(env_id, algo_name, model_zip, n_eval_episodes=20):
    """Evaluate a saved agent on ``env_id``; returns ``(result, extras)`` in the
    same shape as :func:`rl.deep.train.train` (with an empty learning curve)."""
    meta, model = check_compatible(env_id, algo_name, model_zip)

    from stable_baselines3.common.env_util import make_vec_env
    evaluate_policy = trainer._evaluate_policy_fn(algo_name)

    started = time.time()
    eval_env = make_vec_env(env_id, n_envs=1, seed=123)
    try:
        model.set_env(eval_env)
        ep_rewards, ep_lengths = evaluate_policy(
            model, eval_env, n_eval_episodes=n_eval_episodes,
            deterministic=True, return_episode_rewards=True)
    finally:
        eval_env.close()

    wall = time.time() - started
    mean_r = sum(ep_rewards) / len(ep_rewards)
    std_r = (sum((r - mean_r) ** 2 for r in ep_rewards) / len(ep_rewards)) ** 0.5
    threshold = meta.get("reward_threshold")
    solved = threshold is not None and mean_r >= threshold
    random_ref = trainer.random_baseline(env_id, n_eval_episodes)
    beats_random = trainer._quality(mean_r, random_ref)

    metrics = {
        "Mode": "Évaluation (sans entraînement)",
        "Algorithme": algo_name,
        "Environnement": env_id,
        "Récompense d'évaluation (moy.)": round(mean_r, 1),
        "Écart-type": round(std_r, 1),
        "Récompense aléatoire (réf.)": round(random_ref, 1),
        "Gain vs aléatoire": round(mean_r - random_ref, 1),
        "Épisodes d'évaluation": int(n_eval_episodes),
        "Seuil de réussite": ("—" if threshold is None else round(float(threshold), 1)),
        "Résolu": ("—" if threshold is None else ("oui" if solved else "non")),
        "Durée (s)": round(wall, 1),
    }
    result = {
        "metrics": metrics, "curve": [], "cancelled": False, "solved": bool(solved),
        "threshold": (None if threshold is None else float(threshold)),
        "random_reward": round(random_ref, 2), "beats_random": bool(beats_random),
        "env_id": env_id, "algo": algo_name, "group": meta.get("group"),
        "obs_dim": meta.get("obs_dim"), "action_kind": meta.get("action_kind"),
        "model_path": None,
    }
    extras = {"eval_rewards": [float(r) for r in ep_rewards],
              "eval_lengths": [int(x) for x in ep_lengths]}
    return result, extras
