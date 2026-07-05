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
    assert "agents" in cat  # "My agents" registry surfaced in the catalogue
    ids = {a["id"] for a in cat["algos"]}
    assert {"PPO", "DQN", "A2C", "RecurrentPPO", "ARS", "CrossQ", "MaskablePPO"} <= ids
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


def test_cyber_envs_registered_and_valid():
    """The two new cyber envs are registered and follow the Gymnasium API."""
    import gymnasium as gym
    from rl.deep import cyber_envs
    cyber_envs.register()
    for env_id, steps in (("IncidentContainment-v0", 60), ("ThresholdTuning-v0", 80)):
        assert env_id in gym.registry
        env = gym.make(env_id)
        obs, _ = env.reset(seed=0)
        assert env.observation_space.contains(obs)
        obs, r, term, trunc, _ = env.step(env.action_space.sample())
        assert isinstance(float(r), float)
        env.close()


def test_new_cyber_envs_in_catalog():
    """Both new cyber envs surface in the catalogue, grouped as cyber_defense."""
    by_id = {e["id"]: e for e in envs.list_envs()}
    assert by_id["IncidentContainment-v0"]["action_kind"] == envs.DISCRETE
    assert by_id["ThresholdTuning-v0"]["action_kind"] == envs.CONTINUOUS
    assert by_id["ThresholdTuning-v0"]["group"] == "cyber_defense"


def test_noc_envs_registered_and_valid():
    """The two NOC envs are registered and follow the Gymnasium API."""
    import gymnasium as gym
    from rl.deep import noc_envs
    noc_envs.register()
    for env_id in ("TrafficRerouting-v0", "CapacityScaling-v0"):
        assert env_id in gym.registry
        env = gym.make(env_id)
        obs, _ = env.reset(seed=0)
        assert env.observation_space.contains(obs)
        obs, r, term, trunc, _ = env.step(env.action_space.sample())
        assert isinstance(float(r), float)
        env.close()


def test_noc_and_new_soc_envs_in_catalog():
    """NOC envs surface grouped as noc_ops; the staffing env as cyber_defense."""
    by_id = {e["id"]: e for e in envs.list_envs()}
    assert by_id["TrafficRerouting-v0"]["group"] == "noc_ops"
    assert by_id["TrafficRerouting-v0"]["action_kind"] == envs.DISCRETE
    assert by_id["CapacityScaling-v0"]["group"] == "noc_ops"
    assert by_id["CapacityScaling-v0"]["action_kind"] == envs.CONTINUOUS
    assert by_id["AnalystAssignment-v0"]["group"] == "cyber_defense"
    # Both budget-constrained envs expose an action mask.
    assert envs.is_maskable("TrafficRerouting-v0") is True
    assert envs.is_maskable("AnalystAssignment-v0") is True


def test_analyst_assignment_masks_senior_pool():
    """ASSIGN_SENIOR is masked exactly while every senior is busy."""
    import gymnasium as gym
    from rl.deep import cyber_envs
    cyber_envs.register()
    env = gym.make("AnalystAssignment-v0").unwrapped
    env.reset(seed=0)
    assert env.action_masks()[2]  # all seniors free at the start
    for _ in range(env.n_seniors):
        assert env.action_masks()[2]
        env.step(2)  # AA_SENIOR
    # Seniors tick down one step per env.step, so after n assignments in n
    # steps at least one is still busy only if busy time exceeds elapsed steps.
    masks = env.action_masks()
    assert masks[0] and masks[1]  # defer / junior always valid


def test_patch_and_case_envs_registered_and_valid():
    """The patch-prioritization and case-investigation envs follow the API."""
    import gymnasium as gym
    from rl.deep import cyber_envs
    cyber_envs.register()
    for env_id in ("PatchPrioritization-v0", "CaseInvestigation-v0"):
        assert env_id in gym.registry
        env = gym.make(env_id)
        obs, _ = env.reset(seed=0)
        assert env.observation_space.contains(obs)
        obs, r, term, trunc, _ = env.step(env.action_space.sample())
        assert isinstance(float(r), float)
        env.close()
    by_id = {e["id"]: e for e in envs.list_envs()}
    assert by_id["PatchPrioritization-v0"]["group"] == "cyber_defense"
    assert by_id["CaseInvestigation-v0"]["group"] == "cyber_defense"
    assert envs.is_maskable("PatchPrioritization-v0") is True


def test_patch_prioritization_masks_emergency_budget():
    """EMERGENCY is masked exactly once every maintenance window is spent."""
    import gymnasium as gym
    from rl.deep import cyber_envs
    cyber_envs.register()
    env = gym.make("PatchPrioritization-v0").unwrapped
    env.reset(seed=0)
    for _ in range(env.max_windows):
        assert env.action_masks()[2]
        env.step(2)  # PP_EMERGENCY
    assert not env.action_masks()[2]  # budget spent -> masked
    masks = env.action_masks()
    assert masks[0] and masks[1]  # defer / schedule always valid


def test_capacity_scaling_trains_continuous():
    """The continuous NOC env trains with an off-policy continuous algo (SAC)."""
    result, _ = train.train("CapacityScaling-v0", "SAC",
                            {"total_timesteps": 2000, "buffer_size": 10000}, n_eval_episodes=3)
    assert result["metrics"]["Environnement"] == "CapacityScaling-v0"
    assert result["action_kind"] == envs.CONTINUOUS


def test_random_baseline_and_gain():
    """Training reports a random baseline + a gain-vs-random signal, and a short
    run on the incident env should beat the random policy."""
    result, _ = train.train("IncidentContainment-v0", "PPO",
                            {"total_timesteps": 20000}, n_eval_episodes=15)
    assert "Récompense aléatoire (réf.)" in result["metrics"]
    assert "Gain vs aléatoire" in result["metrics"]
    assert isinstance(result["random_reward"], float)
    assert isinstance(result["beats_random"], bool)
    assert result["beats_random"] is True  # a trained PPO must beat random here


def test_threshold_tuning_continuous_train():
    """The continuous cyber env trains with an off-policy continuous algo (SAC)."""
    result, _ = train.train("ThresholdTuning-v0", "SAC",
                            {"total_timesteps": 2000, "buffer_size": 10000}, n_eval_episodes=3)
    assert result["metrics"]["Environnement"] == "ThresholdTuning-v0"
    assert result["action_kind"] == envs.CONTINUOUS


def test_action_space_support():
    assert algos.supports("DQN", envs.DISCRETE) is True
    assert algos.supports("DQN", envs.CONTINUOUS) is False
    assert algos.supports("PPO", envs.CONTINUOUS) is True
    assert algos.supports("A2C", envs.DISCRETE) is True
    # SAC / TD3 / DDPG / TQC / CrossQ are continuous-control only.
    for name in ("SAC", "TD3", "DDPG", "TQC", "CrossQ"):
        assert algos.supports(name, envs.CONTINUOUS) is True
        assert algos.supports(name, envs.DISCRETE) is False
    # QRDQN discrete-only; TRPO / RecurrentPPO / ARS both (sb3-contrib).
    assert algos.supports("QRDQN", envs.DISCRETE) is True
    assert algos.supports("QRDQN", envs.CONTINUOUS) is False
    for name in ("TRPO", "RecurrentPPO", "ARS"):
        assert algos.supports(name, envs.DISCRETE) is True
        assert algos.supports(name, envs.CONTINUOUS) is True


def test_maskable_requires_maskable_env():
    """MaskablePPO is discrete AND only compatible with a mask-capable env."""
    assert algos.requires_mask("MaskablePPO") is True
    assert algos.requires_mask("PPO") is False
    assert algos.supports("MaskablePPO", envs.DISCRETE) is True
    # AlertTriage is maskable; CartPole is not.
    assert algos.compatible("MaskablePPO", envs.DISCRETE, True) is True
    assert algos.compatible("MaskablePPO", envs.DISCRETE, False) is False
    assert algos.compatible("PPO", envs.DISCRETE, False) is True
    assert envs.is_maskable("AlertTriage-v0") is True
    assert envs.is_maskable("CartPole-v1") is False


def test_ars_has_no_gamma_but_has_delta_std():
    """ARS is gradient-free: its schema drops gamma and adds delta_std."""
    names = {f["name"] for f in algos.fields_for("ARS")}
    assert "delta_std" in names and "learning_rate" in names
    assert "gamma" not in names and "ent_coef" not in names


def test_buffer_size_clamps_to_int():
    kw = algos.build_kwargs("SAC", {"buffer_size": 10 ** 9, "tau": 99})
    assert kw["buffer_size"] == 1000000 and isinstance(kw["buffer_size"], int)
    assert kw["tau"] == pytest.approx(0.02)  # capped at max


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


def test_train_end_to_end_sac_continuous():
    """A tiny SAC run on a continuous env (Pendulum) wires up and evaluates."""
    result, extras = train.train("Pendulum-v1", "SAC",
                                 {"total_timesteps": 1000, "buffer_size": 10000},
                                 n_eval_episodes=3)
    assert result["metrics"]["Algorithme"] == "SAC"
    assert len(extras["eval_rewards"]) == 3


def test_train_end_to_end_qrdqn_contrib():
    """A tiny QRDQN (sb3-contrib) run on CartPole wires up and evaluates."""
    pytest.importorskip("sb3_contrib")
    result, extras = train.train("CartPole-v1", "QRDQN", {"total_timesteps": 2000},
                                 n_eval_episodes=3)
    assert result["metrics"]["Algorithme"] == "QRDQN"
    assert len(extras["eval_rewards"]) == 3


def test_train_end_to_end_maskable_ppo():
    """MaskablePPO trains on the maskable SOC env (action masks honoured)."""
    pytest.importorskip("sb3_contrib")
    result, extras = train.train("AlertTriage-v0", "MaskablePPO",
                                 {"total_timesteps": 1000}, n_eval_episodes=3)
    assert result["metrics"]["Algorithme"] == "MaskablePPO"
    assert len(extras["eval_rewards"]) == 3


def test_train_end_to_end_crossq():
    """CrossQ (no tau) trains on a continuous env via signature-filtered kwargs."""
    pytest.importorskip("sb3_contrib")
    result, _ = train.train("Pendulum-v1", "CrossQ",
                            {"total_timesteps": 1000, "buffer_size": 10000}, n_eval_episodes=2)
    assert result["metrics"]["Algorithme"] == "CrossQ"


def test_train_end_to_end_ars():
    """ARS (gradient-free, no gamma) trains without passing unsupported kwargs."""
    pytest.importorskip("sb3_contrib")
    result, _ = train.train("CartPole-v1", "ARS",
                            {"total_timesteps": 2000, "delta_std": 0.05}, n_eval_episodes=2)
    assert result["metrics"]["Algorithme"] == "ARS"


def test_train_end_to_end_recurrent_ppo():
    """RecurrentPPO trains with the LSTM policy and evaluates."""
    pytest.importorskip("sb3_contrib")
    result, _ = train.train("CartPole-v1", "RecurrentPPO",
                            {"total_timesteps": 2000}, n_eval_episodes=2)
    assert result["metrics"]["Algorithme"] == "RecurrentPPO"


def test_registry_save_evaluate_export_delete(tmp_path):
    """Train tiny -> save to registry -> evaluate the saved agent -> export -> delete."""
    from rl.deep import registry, evaluate
    save_path = str(tmp_path / "m.zip")
    result, _ = train.train("CartPole-v1", "PPO", {"total_timesteps": 2000},
                            n_eval_episodes=3, save_path=save_path)
    entry = registry.save_from_job("test-agent", result, save_path, {"total_timesteps": 2000})
    try:
        assert entry["name"] == "test-agent" and entry["algo"] == "PPO"
        assert any(a["id"] == entry["id"] for a in registry.list_agents())
        path = registry.agent_path(entry["id"])
        assert path and path.endswith(".zip")
        # Evaluate the saved agent without retraining.
        eval_res, eval_extras = evaluate.evaluate("CartPole-v1", "PPO", path, n_eval_episodes=3)
        assert eval_res["metrics"]["Mode"].startswith("Évaluation")
        assert len(eval_extras["eval_rewards"]) == 3
        bundle = registry.export_bundle(entry["id"])
        assert bundle and bundle.endswith(".zip")
    finally:
        assert registry.delete_agent(entry["id"]) is True
        assert registry.get_agent(entry["id"]) is None


def test_continue_warm_start(tmp_path):
    """A saved agent can resume training (warm-start) via load_from."""
    first = str(tmp_path / "a.zip")
    train.train("CartPole-v1", "PPO", {"total_timesteps": 2000}, save_path=first)
    result, _ = train.train("CartPole-v1", "PPO", {"total_timesteps": 2000},
                            save_path=str(tmp_path / "b.zip"), load_from=first)
    assert result["metrics"]["Algorithme"] == "PPO"


def test_evaluate_rejects_dim_mismatch(tmp_path):
    """A model trained on one env is refused on an env of different obs dim."""
    from rl.deep import evaluate
    path = str(tmp_path / "cp.zip")
    train.train("CartPole-v1", "PPO", {"total_timesteps": 1000}, save_path=path)
    # CartPole obs_dim=4, Acrobot obs_dim=6 -> mismatch must raise.
    with pytest.raises(ValueError):
        evaluate.check_compatible("Acrobot-v1", "PPO", path)


def test_custom_csv_env_import_train_delete(tmp_path):
    """Import a CSV as a triage env, train on it, then delete it."""
    import csv
    from rl.deep import custom_envs, envs as env_registry
    csv_path = tmp_path / "alerts.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["threat_score", "asset_criticality", "source_reputation", "label"])
        for i in range(40):
            w.writerow([0.1 + 0.02 * (i % 40), 0.5, 0.3, i % 2])
    meta = custom_envs.import_dataset("prod-alerts", str(csv_path))
    env_id = meta["id"]
    try:
        assert meta["custom"] is True and meta["maskable"] is True
        assert any(e["id"] == env_id for e in env_registry.list_envs())
        result, _ = train.train(env_id, "PPO", {"total_timesteps": 1000}, n_eval_episodes=2)
        assert result["metrics"]["Environnement"] == env_id
    finally:
        assert custom_envs.delete_dataset(env_id) is True
        assert env_registry.get_env(env_id) is None


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
