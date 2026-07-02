"""
cyber_envs.py — custom Gymnasium environments for cyber-defense reinforcement
learning, the domain the whole cockpit is oriented towards (SOC / threat intel).

Rather than dressing a generic control task in cyber vocabulary (which would be
decorative), this defines a genuine sequential decision problem a SOC faces:

  AlertTriage-v0 — triage a stream of security alerts under a limited response
  budget. Each step the agent sees one alert (threat score, asset criticality,
  source reputation, remaining budget) and chooses how hard to respond. Blocking
  a real attack on a critical asset pays off; blocking benign traffic disrupts
  the business; missing a real attack is costly; and the response budget forces
  the agent to spend its blocks where they matter. The reward encodes exactly the
  operational cost/benefit trade-off (false positives vs missed detections vs
  analyst budget) the cockpit already reasons about for supervised models.

State is continuous, actions are discrete, so DQN / PPO / A2C all apply. The env
is registered with Gymnasium on import so ``gym.make("AlertTriage-v0")`` works.
"""

from __future__ import annotations

import numpy as np
import gymnasium as gym
from gymnasium import spaces

# Discrete responses, from cheapest/least intrusive to most.
DISMISS, MONITOR, BLOCK = 0, 1, 2
ACTION_NAMES = ["ignorer", "surveiller", "bloquer"]


class AlertTriageEnv(gym.Env):
    """A SOC alert-triage MDP (see module docstring)."""

    metadata = {"render_modes": []}

    def __init__(self, episode_len: int = 50, budget: int = 15):
        super().__init__()
        self.episode_len = int(episode_len)
        self.max_budget = int(budget)
        # [threat_score, asset_criticality, source_reputation, budget_fraction]
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)
        self._step = 0
        self._budget = self.max_budget
        self._alert = None  # (threat, criticality, reputation, is_malicious)

    def _draw_alert(self):
        threat = float(self.np_random.uniform(0.0, 1.0))
        criticality = float(self.np_random.uniform(0.0, 1.0))
        reputation = float(self.np_random.uniform(0.0, 1.0))
        # Ground-truth maliciousness: driven by threat and (low) source reputation.
        p_mal = np.clip(0.7 * threat + 0.3 * (1.0 - reputation), 0.0, 1.0)
        is_malicious = bool(self.np_random.uniform() < p_mal)
        self._alert = (threat, criticality, reputation, is_malicious)

    def _obs(self):
        threat, crit, rep, _ = self._alert
        budget_frac = self._budget / max(1, self.max_budget)
        return np.array([threat, crit, rep, budget_frac], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step = 0
        self._budget = self.max_budget
        self._draw_alert()
        return self._obs(), {}

    def step(self, action):
        action = int(action)
        _, criticality, _, is_malicious = self._alert
        # Blocking needs budget; with none left it degrades to monitoring.
        effective = action
        if action == BLOCK and self._budget <= 0:
            effective = MONITOR
        if effective == BLOCK:
            self._budget -= 1

        if is_malicious:
            reward = {DISMISS: -10.0 * criticality,
                      MONITOR: 3.0 * criticality,
                      BLOCK: 10.0 * criticality}[effective]
        else:
            reward = {DISMISS: 1.0,
                      MONITOR: -1.0,
                      BLOCK: -5.0}[effective]

        self._step += 1
        terminated = False
        truncated = self._step >= self.episode_len
        if not truncated:
            self._draw_alert()
        return self._obs(), float(reward), terminated, truncated, {"blocked_out_of_budget": action == BLOCK and effective != BLOCK}


_REGISTERED = False


def register():
    """Register the cyber-defense envs with Gymnasium (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    if "AlertTriage-v0" not in gym.registry:
        gym.register(id="AlertTriage-v0",
                     entry_point="rl.deep.cyber_envs:AlertTriageEnv",
                     max_episode_steps=50)
    _REGISTERED = True
