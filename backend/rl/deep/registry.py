"""
registry.py — persistent "My agents" store for the Deep RL workbench.

Turns the workbench from a throwaway demo into a tool you build with: a trained
(or imported) agent can be named and saved; it then survives a backend restart
and reappears as a reusable model you can re-evaluate, continue training, export
or delete. This is the counterpart of the "base models" (presets) but for the
analyst's own agents.

Layout under ``exports/registry/``:
  - ``index.json``            — the catalogue (one entry per agent)
  - ``agent_<id>.zip``        — the self-contained Stable-Baselines3 model
An export *bundle* (``bundle_<id>.zip``) additionally packs a ``report.json``
(metrics + hyperparameters + provenance) alongside the model, so a run can be
archived or shared as a single self-describing artefact.
"""

from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

_DIR = Path(__file__).resolve().parents[2] / "exports" / "registry"
_INDEX = _DIR / "index.json"

# Fields exposed to the client (the on-disk path stays server-side).
_PUBLIC = ("id", "name", "env_id", "algo", "config", "metrics", "solved",
           "obs_dim", "action_kind", "imported", "created", "n_timesteps")


def _read() -> dict:
    if _INDEX.exists():
        try:
            return json.loads(_INDEX.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {"agents": []}
    return {"agents": []}


def _write(data: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    _INDEX.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _public(entry: dict) -> dict:
    return {k: entry.get(k) for k in _PUBLIC}


def list_agents() -> list:
    """All saved agents, newest first (public fields only)."""
    agents = _read().get("agents", [])
    return [_public(e) for e in reversed(agents)]


def _entry(agent_id: str):
    for e in _read().get("agents", []):
        if e["id"] == agent_id:
            return e
    return None


def get_agent(agent_id: str):
    """Public metadata for one agent, or ``None``."""
    e = _entry(agent_id)
    return _public(e) if e else None


def agent_path(agent_id: str):
    """Filesystem path of an agent's ``.zip``, or ``None`` if missing."""
    e = _entry(agent_id)
    if not e:
        return None
    p = Path(e["path"])
    return str(p) if p.exists() else None


def _add(name, env_id, algo, config, metrics, solved, obs_dim, action_kind,
         src_zip, imported, n_timesteps) -> dict:
    agent_id = uuid.uuid4().hex[:12]
    _DIR.mkdir(parents=True, exist_ok=True)
    dest = _DIR / f"agent_{agent_id}.zip"
    shutil.copyfile(src_zip, dest)
    entry = {"id": agent_id, "name": (name or f"agent_{agent_id}")[:80],
             "env_id": env_id, "algo": algo, "config": config or {},
             "metrics": metrics or {}, "solved": bool(solved),
             "obs_dim": obs_dim, "action_kind": action_kind,
             "imported": bool(imported), "n_timesteps": n_timesteps,
             "created": datetime.now().isoformat(timespec="seconds"),
             "path": str(dest)}
    index = _read()
    index["agents"].append(entry)
    _write(index)
    return _public(entry)


def save_from_job(name: str, job_result: dict, model_zip: str, config: dict) -> dict:
    """Persist a finished training job's agent into the registry."""
    metrics = job_result.get("metrics", {})
    return _add(name, job_result.get("env_id"), job_result.get("algo"),
                config, metrics, job_result.get("solved"),
                job_result.get("obs_dim"), job_result.get("action_kind"),
                model_zip, imported=False,
                n_timesteps=metrics.get("Pas d'entraînement"))


def import_agent(name: str, env_id: str, algo: str, obs_dim, action_kind,
                 src_zip: str) -> dict:
    """Register an externally-provided ``.zip`` as an imported agent."""
    return _add(name, env_id, algo, {}, {}, False, obs_dim, action_kind,
                src_zip, imported=True, n_timesteps=None)


def delete_agent(agent_id: str) -> bool:
    """Remove an agent (index entry + model file + any export bundle)."""
    index = _read()
    keep = [e for e in index["agents"] if e["id"] != agent_id]
    if len(keep) == len(index["agents"]):
        return False
    for e in index["agents"]:
        if e["id"] == agent_id:
            Path(e["path"]).unlink(missing_ok=True)
    (_DIR / f"bundle_{agent_id}.zip").unlink(missing_ok=True)
    index["agents"] = keep
    _write(index)
    return True


def export_bundle(agent_id: str):
    """Build a self-describing ``bundle_<id>.zip`` (model + report.json) and
    return its path, or ``None`` if the agent is unknown."""
    e = _entry(agent_id)
    if not e or not Path(e["path"]).exists():
        return None
    report = {k: e.get(k) for k in _PUBLIC}
    bundle = _DIR / f"bundle_{agent_id}.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(e["path"], arcname="model.zip")
        zf.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=2))
    return str(bundle)
