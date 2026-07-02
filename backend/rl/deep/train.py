"""
train.py — train a Deep RL agent (Stable-Baselines3) on a Gymnasium environment.

Deliberately CPU-only and single-process: this is an interactive teaching/analysis
workbench, not a training cluster. A progress callback lets the surrounding job
(:mod:`rl.deep.jobs`) report advancement and lets the caller cancel a run, and a
lightweight learning-curve recorder samples the mean episode reward across
training so the UI can show whether the agent is actually improving.

Heavy imports (torch via stable_baselines3) are done lazily inside :func:`train`
so importing this module — e.g. to read the algo/env registries — stays cheap.
"""

from __future__ import annotations

import time

from . import algos as algo_registry
from . import envs as env_registry
from . import cyber_envs


def _make_callback(total_timesteps, on_progress, should_cancel):
    """Build the SB3 training callback: reports progress, samples the learning
    curve (mean episode reward), and stops early when ``should_cancel`` is set.

    Defined as a factory so importing this module does not pull in
    stable_baselines3 (and torch) at module load — the registries stay cheap.
    """
    from stable_baselines3.common.callbacks import BaseCallback

    class _CB(BaseCallback):
        def __init__(self):
            super().__init__()
            self.curve = []            # [(timesteps, mean_reward)]
            self._sample_every = max(1, total_timesteps // 100)
            self._next_sample = self._sample_every

        def _record(self):
            buf = self.model.ep_info_buffer
            if buf:
                mean_r = sum(ep["r"] for ep in buf) / len(buf)
                self.curve.append((int(self.num_timesteps), float(mean_r)))

        def _on_step(self) -> bool:
            if should_cancel and should_cancel():
                return False  # SB3 stops training gracefully
            if self.num_timesteps >= self._next_sample:
                self._record()
                self._next_sample += self._sample_every
                if on_progress:
                    on_progress(min(1.0, self.num_timesteps / max(1, total_timesteps)))
            return True

        def _on_training_end(self):
            self._record()

    return _CB()


def _build_model(algo_name, env, kwargs):
    """Instantiate the SB3 model. ``kwargs`` are already validated/clamped."""
    from stable_baselines3 import PPO, A2C, DQN
    classes = {"PPO": PPO, "A2C": A2C, "DQN": DQN}
    cls = classes[algo_name]
    common = dict(policy="MlpPolicy", env=env, verbose=0, device="cpu", seed=0,
                  learning_rate=kwargs["learning_rate"], gamma=kwargs["gamma"])
    if algo_name in ("PPO", "A2C"):
        common["ent_coef"] = kwargs.get("ent_coef", 0.0)
    elif algo_name == "DQN":
        common["exploration_fraction"] = kwargs.get("exploration_fraction", 0.1)
    return cls(**common)


def train(env_id, algo_name, config, on_progress=None, should_cancel=None,
          n_eval_episodes=20, save_path=None):
    """Train ``algo_name`` on ``env_id`` and evaluate the learned policy.

    Returns ``(result, extras)`` where ``result`` holds analyst-facing metrics +
    the learning curve, and ``extras`` holds raw arrays the plot layer needs.
    When ``save_path`` is given, the trained Stable-Baselines3 model is saved
    there (a ``.zip``) so it can be downloaded afterwards.
    Raises ``ValueError`` on an unknown env / algo / incompatible action space.
    """
    cyber_envs.register()  # idempotent; ensures custom envs are known to gym.make
    meta = env_registry.get_env(env_id)
    if meta is None:
        raise ValueError(f"Environnement inconnu : {env_id}")
    if not algo_registry.supports(algo_name, meta["action_kind"]):
        raise ValueError(
            f"{algo_name} ne supporte pas un espace d'action {meta['action_kind']} "
            f"({env_id}). Choisissez PPO ou A2C.")

    from stable_baselines3.common.env_util import make_vec_env
    from stable_baselines3.common.evaluation import evaluate_policy

    kwargs = algo_registry.build_kwargs(algo_name, config)
    total_timesteps = kwargs.pop("total_timesteps")

    env = make_vec_env(env_id, n_envs=1, seed=0)
    started = time.time()
    try:
        model = _build_model(algo_name, env, kwargs)
        cb = _make_callback(total_timesteps, on_progress, should_cancel)
        model.learn(total_timesteps=total_timesteps, callback=cb, progress_bar=False)
        cancelled = bool(should_cancel and should_cancel())

        eval_env = make_vec_env(env_id, n_envs=1, seed=123)
        try:
            ep_rewards, ep_lengths = evaluate_policy(
                model, eval_env, n_eval_episodes=n_eval_episodes,
                deterministic=True, return_episode_rewards=True)
        finally:
            eval_env.close()
        saved_path = None
        if save_path:
            model.save(save_path)  # SB3 writes a self-contained .zip
            saved_path = save_path if str(save_path).endswith(".zip") else str(save_path) + ".zip"
    finally:
        env.close()

    wall = time.time() - started
    mean_r = sum(ep_rewards) / len(ep_rewards)
    std_r = (sum((r - mean_r) ** 2 for r in ep_rewards) / len(ep_rewards)) ** 0.5
    threshold = meta.get("reward_threshold")
    solved = threshold is not None and mean_r >= threshold

    metrics = {
        "Algorithme": algo_name,
        "Environnement": env_id,
        "Pas d'entraînement": int(total_timesteps),
        "Récompense d'évaluation (moy.)": round(mean_r, 1),
        "Écart-type": round(std_r, 1),
        "Épisodes d'évaluation": int(n_eval_episodes),
        "Seuil de réussite": ("—" if threshold is None else round(float(threshold), 1)),
        "Résolu": ("—" if threshold is None else ("oui" if solved else "non")),
        "Durée (s)": round(wall, 1),
    }
    result = {
        "metrics": metrics,
        "curve": cb.curve,
        "cancelled": cancelled,
        "solved": bool(solved),
        "threshold": (None if threshold is None else float(threshold)),
        "env_id": env_id, "algo": algo_name,
        "model_path": saved_path,
    }
    extras = {"eval_rewards": [float(r) for r in ep_rewards],
              "eval_lengths": [int(x) for x in ep_lengths]}
    return result, extras
