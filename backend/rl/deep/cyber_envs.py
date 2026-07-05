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

    def action_masks(self):
        """Valid-action mask for MaskablePPO: BLOCK is masked out when the
        response budget is exhausted (a real operational constraint — you cannot
        block more alerts than your budget allows)."""
        can_block = self._budget > 0
        return np.array([True, True, can_block], dtype=bool)

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


# Incident-containment actions, from cheapest to most disruptive.
IC_MONITOR, IC_ISOLATE, IC_ERADICATE = 0, 1, 2


class IncidentContainmentEnv(gym.Env):
    """Contain a spreading incident (e.g. worm / ransomware lateral movement).

    Unlike AlertTriage (i.i.d. alerts), the state here EVOLVES: the infected
    fraction grows every step until contained, so the agent faces a genuine
    temporal trade-off — investigate to raise confidence (cheap, but the
    infection spreads meanwhile), isolate segments (slows the spread, business
    cost grows with the infected share), or eradicate (expensive, and only
    effective once confidence is high enough — acting blind fails and wastes
    the response). Reward each step is the negated business damage minus the
    action cost, plus a terminal bonus when eradication succeeds.
    """

    metadata = {"render_modes": []}

    def __init__(self, episode_len: int = 60):
        super().__init__()
        self.episode_len = int(episode_len)
        # [infected_fraction, detection_confidence, asset_criticality, isolation_level]
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)
        self._step_n = 0
        self._infected = 0.0
        self._confidence = 0.0
        self._criticality = 0.5
        self._isolation = 0.0
        self._spread_rate = 0.08

    def _obs(self):
        return np.array([self._infected, self._confidence,
                         self._criticality, self._isolation], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step_n = 0
        self._infected = float(self.np_random.uniform(0.02, 0.10))
        self._confidence = float(self.np_random.uniform(0.05, 0.25))
        self._criticality = float(self.np_random.uniform(0.3, 1.0))
        self._isolation = 0.0
        self._spread_rate = float(self.np_random.uniform(0.05, 0.14))
        return self._obs(), {}

    def step(self, action):
        action = int(action)
        reward = 0.0
        terminated = False

        if action == IC_MONITOR:
            # Investigation raises confidence; small analyst cost.
            self._confidence = min(1.0, self._confidence
                                   + float(self.np_random.uniform(0.10, 0.20)))
            reward -= 0.2
        elif action == IC_ISOLATE:
            # Isolation slows the spread; business cost scales with what is cut off.
            self._isolation = min(1.0, self._isolation + 0.34)
            reward -= 1.0 * self._isolation
        else:  # IC_ERADICATE — only works with enough confidence in the diagnosis
            reward -= 2.0
            if self._confidence >= 0.6:
                bonus = 20.0 * self._criticality * (1.0 - self._infected)
                reward += bonus
                terminated = True
            else:
                reward -= 3.0  # blind eradication fails and wastes the response

        if not terminated:
            # Uncontained infection keeps spreading (isolation dampens it).
            growth = self._spread_rate * (1.0 - self._isolation)
            self._infected = min(1.0, self._infected * (1.0 + growth) + 0.002)
            # Ongoing business damage from the infected share.
            reward -= 4.0 * self._infected * self._criticality

        self._step_n += 1
        truncated = (not terminated) and self._step_n >= self.episode_len
        return self._obs(), float(reward), terminated, truncated, {}


class ThresholdTuningEnv(gym.Env):
    """Continuously tune an IDS detection threshold under attack-rate drift.

    The cyber counterpart of the continuous-control benchmarks: the ACTION is a
    real number (nudge the detection threshold up/down), so SAC / TD3 / DDPG /
    CrossQ / TQC apply to a security problem instead of a pendulum. Each step a
    batch of events arrives; attack prevalence drifts over the episode (a
    campaign ramps up and down), attack scores are drawn high, benign scores
    low. The reward pays true positives, charges false positives (analyst
    fatigue) and heavily charges missed attacks — exactly the trade-off the
    cockpit's supervised threshold panel reasons about, but adjusted online.
    """

    metadata = {"render_modes": []}

    _BATCH = 24          # events observed per step
    _MAX_DELTA = 0.08    # max threshold nudge per step

    def __init__(self, episode_len: int = 80):
        super().__init__()
        self.episode_len = int(episode_len)
        # [threshold, observed_attack_fraction, fp_fraction, tp_fraction]
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)
        self._step_n = 0
        self._threshold = 0.5
        self._phase = 0.0
        self._last = (0.0, 0.0, 0.0)  # attack_frac, fp_frac, tp_frac

    def _obs(self):
        attack_frac, fp_frac, tp_frac = self._last
        return np.array([self._threshold, attack_frac, fp_frac, tp_frac], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step_n = 0
        self._threshold = float(self.np_random.uniform(0.3, 0.7))
        self._phase = float(self.np_random.uniform(0.0, 2.0 * np.pi))
        self._last = (0.0, 0.0, 0.0)
        return self._obs(), {}

    def step(self, action):
        delta = float(np.clip(np.asarray(action, dtype=np.float32).reshape(-1)[0], -1.0, 1.0))
        self._threshold = float(np.clip(self._threshold + delta * self._MAX_DELTA, 0.05, 0.95))

        # Attack prevalence drifts over the episode (a campaign ramps up, then down).
        t = self._step_n / max(1, self.episode_len)
        campaign = 0.5 + 0.5 * float(np.sin(self._phase + 2.0 * np.pi * t))
        attack_rate = float(np.clip(0.08 + 0.42 * campaign, 0.0, 0.6))

        # One batch of events: attack scores are high, benign scores low. An event
        # is flagged when its score clears the current threshold.
        n = self._BATCH
        n_attack = int(self.np_random.binomial(n, attack_rate))
        n_benign = n - n_attack
        atk_scores = self.np_random.uniform(0.45, 1.0, size=n_attack)
        ben_scores = self.np_random.uniform(0.0, 0.6, size=n_benign)
        thr = self._threshold
        tp = int(np.sum(atk_scores >= thr))
        fp = int(np.sum(ben_scores >= thr))
        fn = n_attack - tp

        # Reward: pay caught attacks, charge analyst fatigue (FP), heavily charge
        # missed attacks (FN) — the operational cost of a breach. Per-event scale.
        reward = (2.0 * tp - 1.0 * fp - 6.0 * fn) / n
        self._last = (n_attack / n, fp / max(1, n_benign), tp / max(1, n_attack))

        self._step_n += 1
        truncated = self._step_n >= self.episode_len
        return self._obs(), float(reward), False, truncated, {
            "attack_rate": attack_rate, "tp": tp, "fp": fp, "fn": fn}


# Analyst-assignment actions, from cheapest to the scarcest resource.
AA_DEFER, AA_JUNIOR, AA_SENIOR = 0, 1, 2


class AnalystAssignmentEnv(gym.Env):
    """Dispatch a queue of SOC incidents to a limited analyst team.

    A staffing MDP the SOC shift lead faces all day: each step one incident
    comes up (severity, time already waited, current queue pressure, senior
    availability) and must be deferred, assigned to a junior, or assigned to
    one of the few senior analysts. Seniors always resolve but are scarce (a
    senior stays busy for several steps); juniors are plentiful but fail on
    hard incidents (rework cost); deferring is free staff-wise but severe
    incidents age badly and inflate the queue. The reward encodes exactly that
    resource-allocation trade-off — spend seniors where severity warrants it.

    The env exposes an action mask (ASSIGN_SENIOR is invalid when every senior
    is busy), so MaskablePPO applies alongside DQN / PPO / A2C.
    """

    metadata = {"render_modes": []}

    _SENIOR_BUSY_STEPS = 3

    def __init__(self, episode_len: int = 50, n_seniors: int = 3):
        super().__init__()
        self.episode_len = int(episode_len)
        self.n_seniors = int(n_seniors)
        # [severity, age_fraction, queue_load, senior_available_fraction]
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)
        self._step_n = 0
        self._queue_load = 0.3
        self._busy = None      # remaining busy steps per senior
        self._incident = None  # (severity, age_fraction)

    def _seniors_free(self) -> int:
        return int(np.sum(self._busy <= 0))

    def _draw_incident(self):
        severity = float(self.np_random.uniform(0.0, 1.0))
        # Deferred work resurfaces older when the queue is loaded.
        age = float(np.clip(self.np_random.uniform(0.0, 0.5) + 0.5 * self._queue_load, 0.0, 1.0))
        self._incident = (severity, age)

    def _obs(self):
        severity, age = self._incident
        senior_frac = self._seniors_free() / max(1, self.n_seniors)
        return np.array([severity, age, self._queue_load, senior_frac], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step_n = 0
        self._queue_load = float(self.np_random.uniform(0.2, 0.5))
        self._busy = np.zeros(self.n_seniors, dtype=np.int64)
        self._draw_incident()
        return self._obs(), {}

    def action_masks(self):
        """Valid-action mask for MaskablePPO: ASSIGN_SENIOR is masked out when
        every senior analyst is busy (you cannot assign staff you do not have)."""
        return np.array([True, True, self._seniors_free() > 0], dtype=bool)

    def step(self, action):
        action = int(action)
        severity, age = self._incident
        # Assigning a senior needs one free; with none it degrades to a junior.
        effective = action
        if action == AA_SENIOR and self._seniors_free() == 0:
            effective = AA_JUNIOR

        if effective == AA_DEFER:
            # Severe incidents age badly; the queue inflates.
            reward = -2.0 * severity * (0.5 + age)
            self._queue_load = min(1.0, self._queue_load + 0.05)
        elif effective == AA_JUNIOR:
            # Juniors fail on hard incidents: rework plus the time already lost.
            success = bool(self.np_random.uniform() < 1.0 - 0.7 * severity)
            reward = 6.0 * severity + 1.0 if success else -4.0 * severity - 1.0
            self._queue_load = max(0.0, self._queue_load - 0.03)
        else:  # AA_SENIOR — always resolves, but the resource is scarce
            idx = int(np.argmax(self._busy <= 0))
            self._busy[idx] = self._SENIOR_BUSY_STEPS
            # Spending a senior on a trivial incident wastes the scarce slot.
            reward = 9.0 * severity - 1.5
            self._queue_load = max(0.0, self._queue_load - 0.05)

        # Seniors finish their current incidents; ambient arrivals load the queue.
        self._busy = np.maximum(self._busy - 1, 0)
        self._queue_load = float(np.clip(
            self._queue_load + float(self.np_random.uniform(0.0, 0.03)), 0.0, 1.0))

        self._step_n += 1
        terminated = False
        truncated = self._step_n >= self.episode_len
        if not truncated:
            self._draw_incident()
        return self._obs(), float(reward), terminated, truncated, {
            "senior_out_of_staff": action == AA_SENIOR and effective != AA_SENIOR}


# Patch-prioritization actions, from cheapest to most disruptive.
PP_DEFER, PP_SCHEDULE, PP_EMERGENCY = 0, 1, 2


class PatchPrioritizationEnv(gym.Env):
    """Prioritize a queue of vulnerabilities under a maintenance-window budget.

    The vulnerability-management MDP: each step one finding comes up (CVSS
    score, actively-exploited flag — think KEV catalogue —, internet exposure,
    remaining emergency windows) and must be deferred, scheduled for the next
    regular cycle, or patched immediately in an emergency window. Emergency
    patching a vulnerability that was about to be exploited pays off; burning
    an emergency window (production disruption) on a low-risk finding is
    wasteful; deferring a finding that then gets exploited is very costly.
    The scarce emergency windows force the agent to spend them on the
    KEV-listed, exposed, high-CVSS findings.

    Exposes an action mask (EMERGENCY is invalid once every window is spent),
    so MaskablePPO applies alongside DQN / PPO / A2C.
    """

    metadata = {"render_modes": []}

    def __init__(self, episode_len: int = 50, windows: int = 10):
        super().__init__()
        self.episode_len = int(episode_len)
        self.max_windows = int(windows)
        # [cvss, actively_exploited, exposure, window_budget_fraction]
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)
        self._step_n = 0
        self._windows = self.max_windows
        self._vuln = None  # (cvss, kev, exposure, will_be_exploited)

    def _draw_vuln(self):
        cvss = float(self.np_random.uniform(0.0, 1.0))
        kev = float(self.np_random.uniform() < 0.25)  # a minority is actively exploited
        exposure = float(self.np_random.uniform(0.0, 1.0))
        # Ground truth: exploitation is driven by active exploitation in the
        # wild and by exposed high-severity findings.
        p_exp = np.clip(0.10 + 0.55 * kev + 0.30 * exposure * cvss, 0.0, 1.0)
        will_be_exploited = bool(self.np_random.uniform() < p_exp)
        self._vuln = (cvss, kev, exposure, will_be_exploited)

    def _obs(self):
        cvss, kev, exposure, _ = self._vuln
        window_frac = self._windows / max(1, self.max_windows)
        return np.array([cvss, kev, exposure, window_frac], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step_n = 0
        self._windows = self.max_windows
        self._draw_vuln()
        return self._obs(), {}

    def action_masks(self):
        """Valid-action mask for MaskablePPO: EMERGENCY is masked out once
        every emergency maintenance window has been spent."""
        return np.array([True, True, self._windows > 0], dtype=bool)

    def step(self, action):
        action = int(action)
        cvss, _, _, will_be_exploited = self._vuln
        # Emergency patching needs a window; with none left it degrades to the
        # regular cycle.
        effective = action
        if action == PP_EMERGENCY and self._windows <= 0:
            effective = PP_SCHEDULE
        if effective == PP_EMERGENCY:
            self._windows -= 1

        if will_be_exploited:
            # Scheduling still patches, but late — partial protection only.
            reward = {PP_DEFER: -10.0 * cvss,
                      PP_SCHEDULE: 3.0 * cvss,
                      PP_EMERGENCY: 10.0 * cvss}[effective]
        else:
            # Low-risk finding: deferring saves effort; the regular cycle has a
            # small routine cost; an emergency window disrupts production.
            reward = {PP_DEFER: 1.0,
                      PP_SCHEDULE: -0.5,
                      PP_EMERGENCY: -4.0}[effective]

        self._step_n += 1
        terminated = False
        truncated = self._step_n >= self.episode_len
        if not truncated:
            self._draw_vuln()
        return self._obs(), float(reward), terminated, truncated, {
            "emergency_out_of_windows": action == PP_EMERGENCY and effective != PP_EMERGENCY}


# Case-investigation actions.
CI_INVESTIGATE, CI_CLOSE, CI_ESCALATE = 0, 1, 2


class CaseInvestigationEnv(gym.Env):
    """Decide when to stop investigating a suspicious case — an optimal-stopping MDP.

    One case is open at a time, with a hidden ground truth (real incident or
    benign). The agent only sees a noisy suspicion estimate; INVESTIGATE
    gathers more evidence (analyst cost, and the backlog grows meanwhile) and
    pulls the estimate toward the truth. CLOSE pays off on benign cases but is
    very costly on a real incident (missed detection); ESCALATE pays off on
    real incidents but wastes incident-response time on benign ones. The core
    skill to learn is WHEN enough evidence is enough — the sequential-testing
    trade-off of a SOC investigation, and a partially observable problem where
    a recurrent policy (RecurrentPPO) has a genuine edge.
    """

    metadata = {"render_modes": []}

    _MAX_EVIDENCE = 6  # evidence_fraction saturates after this many looks

    def __init__(self, episode_len: int = 60):
        super().__init__()
        self.episode_len = int(episode_len)
        # [suspicion_estimate, evidence_fraction, severity, backlog_pressure]
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)
        self._step_n = 0
        self._backlog = 0.3
        self._case = None  # dict: truth, suspicion, severity, evidence

    def _draw_case(self):
        severity = float(self.np_random.uniform(0.2, 1.0))
        is_incident = bool(self.np_random.uniform() < 0.35)
        truth = 1.0 if is_incident else 0.0
        # Initial suspicion: weakly informative and noisy.
        suspicion = float(np.clip(
            0.5 + (truth - 0.5) * self.np_random.uniform(0.1, 0.4)
            + self.np_random.uniform(-0.15, 0.15), 0.0, 1.0))
        self._case = {"truth": truth, "suspicion": suspicion,
                      "severity": severity, "evidence": 0}

    def _obs(self):
        c = self._case
        evidence_frac = min(1.0, c["evidence"] / self._MAX_EVIDENCE)
        return np.array([c["suspicion"], evidence_frac,
                         c["severity"], self._backlog], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step_n = 0
        self._backlog = float(self.np_random.uniform(0.2, 0.5))
        self._draw_case()
        return self._obs(), {}

    def step(self, action):
        action = int(action)
        c = self._case
        truth, severity = c["truth"], c["severity"]
        case_done = False

        if action == CI_INVESTIGATE:
            # Evidence pulls the estimate toward the truth; the backlog grows.
            pull = float(self.np_random.uniform(0.25, 0.50))
            noise = float(self.np_random.uniform(-0.05, 0.05))
            c["suspicion"] = float(np.clip(
                c["suspicion"] + (truth - c["suspicion"]) * pull + noise, 0.0, 1.0))
            c["evidence"] += 1
            reward = -0.3 - 0.5 * self._backlog  # analyst time, worse under pressure
            self._backlog = min(1.0, self._backlog + 0.04)
        elif action == CI_CLOSE:
            reward = 2.0 if truth < 0.5 else -10.0 * severity  # missed incident
            case_done = True
        else:  # CI_ESCALATE
            reward = 8.0 * severity if truth > 0.5 else -4.0  # IR time wasted
            case_done = True

        if case_done:
            self._backlog = max(0.0, self._backlog - 0.06)
            self._draw_case()

        self._step_n += 1
        truncated = self._step_n >= self.episode_len
        return self._obs(), float(reward), False, truncated, {}


_REGISTERED = False


def register():
    """Register the cyber-defense envs with Gymnasium (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    specs = [
        ("AlertTriage-v0", "rl.deep.cyber_envs:AlertTriageEnv", 50),
        ("IncidentContainment-v0", "rl.deep.cyber_envs:IncidentContainmentEnv", 60),
        ("ThresholdTuning-v0", "rl.deep.cyber_envs:ThresholdTuningEnv", 80),
        ("AnalystAssignment-v0", "rl.deep.cyber_envs:AnalystAssignmentEnv", 50),
        ("PatchPrioritization-v0", "rl.deep.cyber_envs:PatchPrioritizationEnv", 50),
        ("CaseInvestigation-v0", "rl.deep.cyber_envs:CaseInvestigationEnv", 60),
    ]
    for env_id, entry, max_steps in specs:
        if env_id not in gym.registry:
            gym.register(id=env_id, entry_point=entry, max_episode_steps=max_steps)
    _REGISTERED = True
