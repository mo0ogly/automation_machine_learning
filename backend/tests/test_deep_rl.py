"""Tests for the Deep RL workbench (rl.deep): registries, validation, and a short
end-to-end training job. The end-to-end test uses a tiny timestep budget so it
stays fast (a few seconds on CPU)."""

import time

import pytest

from rl import deep as deep_rl
from rl.deep import algos, envs, train


def test_catalog_shape():
    cat = deep_rl.catalog()
    assert len(cat["envs"]) >= 5
    ids = {a["id"] for a in cat["algos"]}
    assert {"PPO", "DQN", "A2C"} <= ids
    for env in cat["envs"]:
        assert env["action_kind"] in (envs.DISCRETE, envs.CONTINUOUS)
        assert env["obs_dim"] >= 1
    # Presets ("base models"), cyber-defense first, all pointing at real envs/algos.
    presets = cat["presets"]
    assert len(presets) >= 2
    assert presets[0]["group"] == "cyber_defense"
    env_ids = {e["id"] for e in cat["envs"]}
    algo_ids = {a["id"] for a in cat["algos"]}
    for p in presets:
        assert p["env_id"] in env_ids
        assert p["algo"] in algo_ids


def test_cyber_env_registered_and_valid():
    """The custom AlertTriage env is registered and follows the Gymnasium API."""
    import gymnasium as gym
    from rl.deep import cyber_envs
    cyber_envs.register()
    assert "AlertTriage-v0" in gym.registry
    env = gym.make("AlertTriage-v0")
    obs, info = env.reset(seed=0)
    assert env.observation_space.contains(obs)
    total, steps, done = 0.0, 0, False
    while not done and steps < 100:
        obs, r, term, trunc, _ = env.step(env.action_space.sample())
        total += r
        steps += 1
        done = term or trunc
    assert steps == 50  # episode length
    env.close()


def test_dqn_is_discrete_only():
    assert algos.supports("DQN", envs.DISCRETE) is True
    assert algos.supports("DQN", envs.CONTINUOUS) is False
    assert algos.supports("PPO", envs.CONTINUOUS) is True
    assert algos.supports("A2C", envs.DISCRETE) is True


def test_build_kwargs_clamps_out_of_range():
    kw = algos.build_kwargs("PPO", {"total_timesteps": 10 ** 9, "learning_rate": 99,
                                    "gamma": -5, "ent_coef": 10})
    assert kw["total_timesteps"] == 200000            # capped at max
    assert kw["learning_rate"] == pytest.approx(0.01)  # capped at max
    assert kw["gamma"] == pytest.approx(0.8)           # floored at min
    assert kw["ent_coef"] == pytest.approx(0.05)       # capped at max
    assert isinstance(kw["total_timesteps"], int)


def test_build_kwargs_uses_defaults_for_missing():
    kw = algos.build_kwargs("DQN", {})
    assert kw["total_timesteps"] == 30000
    assert kw["gamma"] == pytest.approx(0.99)
    assert "exploration_fraction" in kw


def test_deep_rl_fields_deduplicated():
    names = [f["name"] for f in deep_rl.deep_rl_fields()]
    assert len(names) == len(set(names))
    assert "total_timesteps" in names and "learning_rate" in names


def test_train_unknown_env_raises():
    with pytest.raises(ValueError):
        train.train("Nope-v9", "PPO", {})


def test_train_rejects_incompatible_algo():
    with pytest.raises(ValueError):
        train.train("Pendulum-v1", "DQN", {})


def test_train_end_to_end_cartpole():
    """A tiny PPO run on CartPole finishes and produces coherent metrics."""
    result, extras = train.train("CartPole-v1", "PPO", {"total_timesteps": 2000},
                                 n_eval_episodes=5)
    m = result["metrics"]
    assert m["Algorithme"] == "PPO"
    assert m["Environnement"] == "CartPole-v1"
    assert len(extras["eval_rewards"]) == 5
    assert isinstance(result["solved"], bool)
    assert result["threshold"] == 475.0


def test_job_lifecycle():
    """start_training -> poll -> done, with plots attached to the result."""
    job_id = deep_rl.jobs.start_training("CartPole-v1", "PPO", {"total_timesteps": 2000})
    for _ in range(120):
        job = deep_rl.jobs.get_job(job_id)
        if job["status"] in ("done", "error", "cancelled"):
            break
        time.sleep(1)
    assert job["status"] == "done", job.get("error")
    assert len(job["result"]["plots"]) == 2
    assert all(set(p) >= {"img", "caption"} for p in job["result"]["plots"])
    assert "cancel" not in job and "model_path" not in job  # internals never leak
    # The trained model was saved and is downloadable.
    assert job["result"]["can_download"] is True
    path = deep_rl.jobs.model_path(job_id)
    assert path is not None and path.endswith(".zip")
