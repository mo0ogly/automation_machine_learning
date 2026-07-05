"""
custom_envs.py — user-imported Gymnasium environments built from a CSV dataset.

The safe way to let an analyst "bring their own environment": rather than
executing uploaded Python (arbitrary code execution + content-filter risk), we
build a *data-driven* SOC triage environment from an uploaded CSV of real alerts.
The MDP is identical to :class:`AlertTriageEnv` (same actions, budget and
cost/benefit reward), but instead of sampling synthetic alerts it replays the
rows of the analyst's own dataset — so the learned policy reflects their traffic.

Expected CSV columns (case-insensitive, order-independent):
  threat_score, asset_criticality, source_reputation, label
where the first three are in [0, 1] (clipped) and ``label`` is 1 for a real
attack, 0 for benign.

Imported datasets are persisted under ``exports/custom_envs/`` (the CSV + a JSON
index) and re-registered at import time, so they survive a backend restart.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from . import envs as env_registry
from .cyber_envs import DISMISS, MONITOR, BLOCK

_DIR = Path(__file__).resolve().parents[2] / "exports" / "custom_envs"
_INDEX = _DIR / "index.json"
_COLUMNS = ["threat_score", "asset_criticality", "source_reputation", "label"]


class CsvTriageEnv(gym.Env):
    """SOC alert-triage MDP replaying rows of a user-imported CSV dataset."""

    metadata = {"render_modes": []}

    def __init__(self, path: str, episode_len: int = 50, budget: int = 15):
        super().__init__()
        self._data = _load_matrix(path)  # (N, 4) float32
        self.episode_len = int(episode_len)
        self.max_budget = int(budget)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(4,), dtype=np.float32)
        self.action_space = spaces.Discrete(3)
        self._step = 0
        self._budget = self.max_budget
        self._row = None

    def _draw(self):
        idx = int(self.np_random.integers(0, len(self._data)))
        self._row = self._data[idx]

    def _obs(self):
        threat, crit, rep, _ = self._row
        budget_frac = self._budget / max(1, self.max_budget)
        return np.array([threat, crit, rep, budget_frac], dtype=np.float32)

    def action_masks(self):
        return np.array([True, True, self._budget > 0], dtype=bool)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._step = 0
        self._budget = self.max_budget
        self._draw()
        return self._obs(), {}

    def step(self, action):
        action = int(action)
        _, criticality, _, label = self._row
        is_malicious = label >= 0.5
        effective = action
        if action == BLOCK and self._budget <= 0:
            effective = MONITOR
        if effective == BLOCK:
            self._budget -= 1
        if is_malicious:
            reward = {DISMISS: -10.0 * criticality, MONITOR: 3.0 * criticality,
                      BLOCK: 10.0 * criticality}[effective]
        else:
            reward = {DISMISS: 1.0, MONITOR: -1.0, BLOCK: -5.0}[effective]
        self._step += 1
        truncated = self._step >= self.episode_len
        if not truncated:
            self._draw()
        return self._obs(), float(reward), False, truncated, {}


def make_csv_env(path: str, episode_len: int = 50, budget: int = 15):
    """Gymnasium entry point (registered per imported dataset)."""
    return CsvTriageEnv(path, episode_len=episode_len, budget=budget)


def _load_matrix(path: str) -> np.ndarray:
    """Parse the CSV into an (N, 4) float matrix [threat, crit, rep, label]."""
    import pandas as pd
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in _COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("Colonnes manquantes dans le CSV : " + ", ".join(missing)
                         + f". Attendu : {', '.join(_COLUMNS)}.")
    mat = df[_COLUMNS].to_numpy(dtype="float32")
    if mat.shape[0] < 10:
        raise ValueError("Le CSV doit contenir au moins 10 lignes d'alertes.")
    mat[:, :3] = np.clip(mat[:, :3], 0.0, 1.0)         # features in [0, 1]
    mat[:, 3] = (mat[:, 3] >= 0.5).astype("float32")   # label -> {0, 1}
    return mat


def _slug(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "dataset")).strip("-").lower()
    return (s or "dataset")[:24]


def _read_index() -> dict:
    if _INDEX.exists():
        try:
            return json.loads(_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {"envs": []}
    return {"envs": []}


def _write_index(data: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _register_gym(env_id: str, path: str) -> None:
    if env_id not in gym.registry:
        gym.register(id=env_id, entry_point="rl.deep.custom_envs:make_csv_env",
                     max_episode_steps=50, kwargs={"path": path})


def _meta(entry: dict) -> dict:
    return {"id": entry["id"], "group": "cyber_defense", "action_kind": env_registry.DISCRETE,
            "obs_dim": 4, "n_actions": 3, "max_steps": 50, "maskable": True,
            "reward_threshold": None, "reward_range": [-300.0, 200.0],
            "custom": True, "label": entry.get("name") or entry["id"],
            "n_rows": entry.get("n_rows", 0)}


def import_dataset(name: str, csv_path: str) -> dict:
    """Validate + persist a CSV dataset and register it as a Gymnasium env.

    Returns the catalogue metadata for the new environment. Raises ``ValueError``
    if the CSV is malformed.
    """
    mat = _load_matrix(csv_path)  # validates; raises on bad columns/size
    env_id = f"CustomTriage-{_slug(name)}-{uuid.uuid4().hex[:6]}-v0"
    _DIR.mkdir(parents=True, exist_ok=True)
    stored = _DIR / f"{env_id}.csv"
    import pandas as pd
    pd.DataFrame(mat, columns=_COLUMNS).to_csv(stored, index=False)
    entry = {"id": env_id, "name": name or env_id, "path": str(stored),
             "n_rows": int(mat.shape[0])}
    index = _read_index()
    index["envs"].append(entry)
    _write_index(index)
    _register_gym(env_id, str(stored))
    meta = _meta(entry)
    env_registry.register_custom(meta)
    return meta


def delete_dataset(env_id: str) -> bool:
    """Remove an imported dataset (index entry, CSV file, catalogue entry)."""
    index = _read_index()
    keep = [e for e in index["envs"] if e["id"] != env_id]
    if len(keep) == len(index["envs"]):
        return False
    for e in index["envs"]:
        if e["id"] == env_id:
            try:
                Path(e["path"]).unlink(missing_ok=True)
            except OSError:
                pass
    index["envs"] = keep
    _write_index(index)
    env_registry.unregister_custom(env_id)
    return True


def load_persisted() -> None:
    """Re-register every persisted dataset (called at package import)."""
    for entry in _read_index().get("envs", []):
        if Path(entry.get("path", "")).exists():
            _register_gym(entry["id"], entry["path"])
            env_registry.register_custom(_meta(entry))
