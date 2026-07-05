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
from . import noc_envs


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


# Non-default SB3 policy aliases (everything else uses "MlpPolicy").
_POLICY = {"RecurrentPPO": "MlpLstmPolicy"}


def algo_class(algo_name):
    """Return the SB3 / sb3-contrib algorithm class for ``algo_name`` (lazy import)."""
    from stable_baselines3 import PPO, A2C, DQN, SAC, TD3, DDPG
    classes = {"PPO": PPO, "A2C": A2C, "DQN": DQN, "SAC": SAC, "TD3": TD3, "DDPG": DDPG}
    if algo_name in ("QRDQN", "TRPO", "TQC", "RecurrentPPO", "ARS", "CrossQ", "MaskablePPO"):
        from sb3_contrib import QRDQN, TRPO, TQC, RecurrentPPO, ARS, CrossQ, MaskablePPO
        classes.update({"QRDQN": QRDQN, "TRPO": TRPO, "TQC": TQC,
                        "RecurrentPPO": RecurrentPPO, "ARS": ARS,
                        "CrossQ": CrossQ, "MaskablePPO": MaskablePPO})
    cls = classes.get(algo_name)
    if cls is None:
        raise ValueError(f"Algorithme inconnu : {algo_name}")
    return cls


def _build_model(algo_name, env, kwargs):
    """Instantiate the SB3 (or sb3-contrib) model.

    Rather than hand-maintaining which constructor accepts which keyword (they
    differ: ARS has no ``gamma``, CrossQ has no ``tau``, …), we assemble the
    superset of hyperparameters we might pass and filter it to the arguments the
    class actually declares — robust across algorithms and SB3 versions.
    """
    import inspect
    cls = algo_class(algo_name)
    desired = {"policy": _POLICY.get(algo_name, "MlpPolicy"), "env": env,
               "verbose": 0, "device": "cpu", "seed": 0}
    for key in ("learning_rate", "gamma", "ent_coef", "exploration_fraction",
                "tau", "buffer_size", "delta_std"):
        if kwargs.get(key) is not None:
            desired[key] = kwargs[key]
    accepted = set(inspect.signature(cls.__init__).parameters)
    return cls(**{k: v for k, v in desired.items() if k in accepted})


def _evaluate_policy_fn(algo_name):
    """The right ``evaluate_policy`` for the algorithm (maskable variant for
    MaskablePPO so masks are honoured at evaluation time)."""
    if algo_name == "MaskablePPO":
        from sb3_contrib.common.maskable.evaluation import evaluate_policy
    else:
        from stable_baselines3.common.evaluation import evaluate_policy
    return evaluate_policy


def random_baseline(env_id, n_episodes=20):
    """Mean episode reward of a uniformly random policy on ``env_id``.

    The honest reference every trained agent is compared against: "does the
    learned policy actually beat acting at random?" — far more meaningful for a
    bespoke cyber env than an arbitrary fixed threshold. Deterministic (fixed
    seeds), so the same env always yields the same baseline.
    """
    import gymnasium as gym
    cyber_envs.register()
    noc_envs.register()
    env = gym.make(env_id)
    try:
        rewards = []
        for i in range(n_episodes):
            env.reset(seed=1000 + i)
            done, total = False, 0.0
            while not done:
                _, r, term, trunc, _ = env.step(env.action_space.sample())
                total += float(r)
                done = term or trunc
            rewards.append(total)
    finally:
        env.close()
    return sum(rewards) / len(rewards)


def _quality(mean_r, random_ref):
    """Whether ``mean_r`` clearly beats the random baseline (margin scaled to the
    baseline's magnitude, so it is robust to very different reward scales)."""
    margin = 0.1 * abs(random_ref) + 0.01
    return mean_r >= random_ref + margin


def train(env_id, algo_name, config, on_progress=None, should_cancel=None,
          n_eval_episodes=20, save_path=None, load_from=None):
    """Train ``algo_name`` on ``env_id`` and evaluate the learned policy.

    Returns ``(result, extras)`` where ``result`` holds analyst-facing metrics +
    the learning curve, and ``extras`` holds raw arrays the plot layer needs.
    When ``save_path`` is given, the trained Stable-Baselines3 model is saved
    there (a ``.zip``) so it can be downloaded afterwards. When ``load_from`` is
    given, training resumes from that saved model (warm-start) instead of a fresh
    network — the workbench's "continue training" path.
    Raises ``ValueError`` on an unknown env / algo / incompatible action space.
    """
    cyber_envs.register()  # idempotent; ensures custom envs are known to gym.make
    noc_envs.register()
    meta = env_registry.get_env(env_id)
    if meta is None:
        raise ValueError(f"Environnement inconnu : {env_id}")
    if not algo_registry.compatible(algo_name, meta["action_kind"], meta.get("maskable")):
        raise ValueError(
            f"{algo_name} n'est pas compatible avec l'environnement {env_id} "
            f"(action {meta['action_kind']}, masquable={bool(meta.get('maskable'))}).")

    from stable_baselines3.common.env_util import make_vec_env
    evaluate_policy = _evaluate_policy_fn(algo_name)

    kwargs = algo_registry.build_kwargs(algo_name, config)
    total_timesteps = kwargs.pop("total_timesteps")

    env = make_vec_env(env_id, n_envs=1, seed=0)
    started = time.time()
    try:
        if load_from:
            model = algo_class(algo_name).load(load_from, env=env, device="cpu")
        else:
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
    random_ref = random_baseline(env_id, n_eval_episodes)
    beats_random = _quality(mean_r, random_ref)

    metrics = {
        "Algorithme": algo_name,
        "Environnement": env_id,
        "Pas d'entraînement": int(total_timesteps),
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
        "metrics": metrics,
        "curve": cb.curve,
        "cancelled": cancelled,
        "solved": bool(solved),
        "threshold": (None if threshold is None else float(threshold)),
        "random_reward": round(random_ref, 2), "beats_random": bool(beats_random),
        "env_id": env_id, "algo": algo_name, "group": meta.get("group"),
        "obs_dim": meta.get("obs_dim"), "action_kind": meta.get("action_kind"),
        "model_path": saved_path,
    }
    extras = {"eval_rewards": [float(r) for r in ep_rewards],
              "eval_lengths": [int(x) for x in ep_lengths]}
    return result, extras
