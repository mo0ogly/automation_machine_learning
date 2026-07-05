"""
noc_envs.py — custom Gymnasium environments for network-operations (NOC)
reinforcement learning, the networking counterpart of the SOC envs in
:mod:`rl.deep.cyber_envs`.

Two genuine sequential decision problems a NOC faces:

  TrafficRerouting-v0 — handle a stream of link-congestion events under a
  limited spare-path budget. Each step the agent sees one event (utilization,
  latency, link criticality, remaining reroute capacity) and chooses to keep,
  throttle or reroute. Rerouting a genuinely degraded critical link pays off;
  rerouting a healthy link disrupts flows for nothing; ignoring a real
  degradation is costly; and the spare-path budget forces the agent to spend
  reroutes where they matter. The structural sibling of AlertTriage-v0, on the
  network side of the house.

  CapacityScaling-v0 — continuously adjust provisioned capacity while demand
  follows a diurnal cycle with random bursts. The ACTION is a real number
  (scale capacity up/down), so SAC / TD3 / DDPG / CrossQ / TQC apply. Reward
  pays served traffic, charges over-provisioning (cost/energy) and heavily
  charges dropped traffic (SLA breach) — the classic NOC dimensioning
  trade-off, adjusted online.

State is continuous in both; TrafficRerouting is discrete-action (DQN / PPO /
A2C / MaskablePPO), CapacityScaling is continuous-action. Envs are registered
with Gymnasium via :func:`register` (idempotent).
"""

from __future__ import annotations

import numpy as np
import gymnasium as gym
from gymnasium import spaces

# Discrete responses to a congestion event, from cheapest to most intrusive.
KEEP, THROTTLE, REROUTE = 0, 1, 2
NOC_ACTION_NAMES = ["maintenir", "limiter", "rerouter"]


class TrafficReroutingEnv(gym.Env):
    """A NOC congestion-triage MDP (see module docstring)."""

    metadata = {"render_modes": []}

    def __init__(self, episode_len: int = 50, budget: int = 12):
        super().__init__()
        self.episode_len = int(episode_len)
        self.max_budget = int(budget)
        # [utilization, latency, link_criticality, reroute_budget_fraction]
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)
        self._step = 0
        self._budget = self.max_budget
        self._event = None  # (utilization, latency, criticality, is_degraded)

    def _draw_event(self):
        utilization = float(self.np_random.uniform(0.0, 1.0))
        # Latency correlates with utilization (queueing), plus measurement noise.
        latency = float(np.clip(0.6 * utilization + 0.4 * self.np_random.uniform(0.0, 1.0), 0.0, 1.0))
        criticality = float(self.np_random.uniform(0.0, 1.0))
        # Ground-truth degradation: driven by sustained utilization and latency.
        p_deg = np.clip(0.55 * utilization + 0.45 * latency, 0.0, 1.0)
        is_degraded = bool(self.np_random.uniform() < p_deg)
        self._event = (utilization, latency, criticality, is_degraded)

    def _obs(self):
        utilization, latency, criticality, _ = self._event
        budget_frac = self._budget / max(1, self.max_budget)
        return np.array([utilization, latency, criticality, budget_frac], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step = 0
        self._budget = self.max_budget
        self._draw_event()
        return self._obs(), {}

    def action_masks(self):
        """Valid-action mask for MaskablePPO: REROUTE is masked out when no
        spare path remains (a real operational constraint — you cannot reroute
        onto capacity you do not have)."""
        can_reroute = self._budget > 0
        return np.array([True, True, can_reroute], dtype=bool)

    def step(self, action):
        action = int(action)
        _, _, criticality, is_degraded = self._event
        # Rerouting needs a spare path; with none left it degrades to throttling.
        effective = action
        if action == REROUTE and self._budget <= 0:
            effective = THROTTLE
        if effective == REROUTE:
            self._budget -= 1

        if is_degraded:
            reward = {KEEP: -10.0 * criticality,
                      THROTTLE: 3.0 * criticality,
                      REROUTE: 10.0 * criticality}[effective]
        else:
            # Healthy link: leaving it alone is right; throttling hurts users a
            # little; rerouting churns flows (jitter, reordering) for nothing.
            reward = {KEEP: 1.0,
                      THROTTLE: -1.0,
                      REROUTE: -5.0}[effective]

        self._step += 1
        terminated = False
        truncated = self._step >= self.episode_len
        if not truncated:
            self._draw_event()
        return self._obs(), float(reward), terminated, truncated, {
            "reroute_out_of_budget": action == REROUTE and effective != REROUTE}


class CapacityScalingEnv(gym.Env):
    """Continuously scale provisioned capacity under diurnal + bursty demand.

    The NOC counterpart of the continuous-control benchmarks: the ACTION is a
    real number (nudge the provisioned capacity), so off-policy continuous
    algorithms apply to a network dimensioning problem instead of a pendulum.
    Each step a traffic load arrives (diurnal sinusoid + occasional bursts);
    whatever exceeds capacity is dropped. The reward pays served traffic,
    charges the standing cost of provisioned capacity, and heavily charges
    drops (SLA breach) — over-provision and the bill hurts, under-provision
    and the users hurt.
    """

    metadata = {"render_modes": []}

    _MAX_DELTA = 0.08     # max capacity nudge per step
    _BURST_PROB = 0.12    # chance of a traffic burst on any step

    def __init__(self, episode_len: int = 80):
        super().__init__()
        self.episode_len = int(episode_len)
        # [capacity, load, drop_fraction, utilization]
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)
        self._step_n = 0
        self._capacity = 0.5
        self._phase = 0.0
        self._last = (0.0, 0.0, 0.0)  # load, drop_frac, utilization

    def _obs(self):
        load, drop_frac, utilization = self._last
        return np.array([self._capacity, load, drop_frac, utilization], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step_n = 0
        self._capacity = float(self.np_random.uniform(0.3, 0.7))
        self._phase = float(self.np_random.uniform(0.0, 2.0 * np.pi))
        self._last = (0.0, 0.0, 0.0)
        return self._obs(), {}

    def step(self, action):
        delta = float(np.clip(np.asarray(action, dtype=np.float32).reshape(-1)[0], -1.0, 1.0))
        self._capacity = float(np.clip(self._capacity + delta * self._MAX_DELTA, 0.05, 1.0))

        # Demand: diurnal sinusoid over the episode, plus occasional bursts.
        t = self._step_n / max(1, self.episode_len)
        diurnal = 0.5 + 0.5 * float(np.sin(self._phase + 2.0 * np.pi * t))
        load = 0.15 + 0.55 * diurnal + float(self.np_random.uniform(-0.05, 0.05))
        if self.np_random.uniform() < self._BURST_PROB:
            load += float(self.np_random.uniform(0.10, 0.30))
        load = float(np.clip(load, 0.0, 1.0))

        served = min(self._capacity, load)
        dropped = load - served
        # Pay served traffic, charge standing capacity cost, heavily charge drops.
        reward = 2.0 * served - 0.5 * self._capacity - 6.0 * dropped
        self._last = (load, dropped / max(load, 1e-6), served / max(self._capacity, 1e-6))

        self._step_n += 1
        truncated = self._step_n >= self.episode_len
        return self._obs(), float(reward), False, truncated, {
            "load": load, "served": served, "dropped": dropped}


_REGISTERED = False


def register():
    """Register the NOC envs with Gymnasium (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    specs = [
        ("TrafficRerouting-v0", "rl.deep.noc_envs:TrafficReroutingEnv", 50),
        ("CapacityScaling-v0", "rl.deep.noc_envs:CapacityScalingEnv", 80),
    ]
    for env_id, entry, max_steps in specs:
        if env_id not in gym.registry:
            gym.register(id=env_id, entry_point=entry, max_episode_steps=max_steps)
    _REGISTERED = True
