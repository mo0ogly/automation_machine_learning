"""
jobs.py — in-memory training-job registry for the Deep RL workbench.

A Deep RL run can take from a few seconds to a few minutes, which is too long
for a blocking HTTP request. Training therefore runs in a background thread; the
route returns a ``job_id`` immediately and the UI polls the job for progress and,
once finished, for the metrics + plots.

Single-process, single-user assumption (an interactive cockpit): jobs live in a
module-level dict guarded by a lock. Finished jobs are kept so the UI can fetch
the result after completion; the newest ``_MAX_KEPT`` are retained.

Matplotlib is not thread-safe, so figures are rendered under the pipeline's
shared ``PLOT_LOCK`` — the same lock the 8-stage pipeline and the tabular RL
route use.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

from pipeline import plotting
from . import train as trainer
from . import evaluate as evaluator
from . import plots as deep_plots

_MAX_KEPT = 12
_JOBS: "OrderedDict[str, dict]" = OrderedDict()
_LOCK = threading.Lock()

# Trained models are saved here for download; created lazily on first job.
_EXPORT_DIR = Path(__file__).resolve().parents[2] / "exports"


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _set(job_id: str, **fields):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            job.update(fields)


def _evict_old():
    while len(_JOBS) > _MAX_KEPT:
        _JOBS.popitem(last=False)


def _run(job_id: str, env_id: str, algo: str, config: dict, kind: str,
         load_from, model_zip):
    def on_progress(frac):
        _set(job_id, progress=round(float(frac), 3))

    def should_cancel():
        job = _JOBS.get(job_id)
        return bool(job and job.get("cancel"))

    try:
        _EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        if kind == "eval":
            result, extras = evaluator.evaluate(env_id, algo, model_zip)
            save_path = None
        else:  # "train" (fresh) or warm-start via load_from
            save_path = str(_EXPORT_DIR / f"deeprl_{job_id}.zip")
            result, extras = trainer.train(env_id, algo, config, on_progress=on_progress,
                                           should_cancel=should_cancel,
                                           save_path=save_path, load_from=load_from)
        with plotting.PLOT_LOCK:  # matplotlib is not thread-safe
            figs = deep_plots.all_plots(result, extras)
        status = "cancelled" if result.get("cancelled") else "done"
        model_path = result.get("model_path")
        _set(job_id, status=status, progress=1.0, model_path=model_path,
             result={"metrics": result["metrics"], "plots": figs,
                     "solved": result["solved"], "cancelled": result["cancelled"],
                     "env_id": env_id, "algo": algo, "kind": kind,
                     "obs_dim": result.get("obs_dim"), "action_kind": result.get("action_kind"),
                     "group": result.get("group"), "threshold": result.get("threshold"),
                     "random_reward": result.get("random_reward"),
                     "beats_random": result.get("beats_random"),
                     "can_download": bool(model_path and os.path.exists(model_path))})
    except Exception as exc:  # surfaced to the UI as a failed job, never crashes the server
        _set(job_id, status="error", error=f"{type(exc).__name__}: {exc}")


def _start(env_id, algo, config, kind, load_from=None, model_zip=None) -> str:
    job_id = _new_id()
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "status": "running", "progress": 0.0,
                         "cancel": False, "result": None, "error": None,
                         "env_id": env_id, "algo": algo, "kind": kind,
                         "config": dict(config or {})}
        _evict_old()
    thread = threading.Thread(target=_run,
                              args=(job_id, env_id, algo, config, kind, load_from, model_zip),
                              name=f"deeprl-{job_id}", daemon=True)
    thread.start()
    return job_id


def start_training(env_id: str, algo: str, config: dict, load_from=None) -> str:
    """Spawn a background training job (optionally warm-started from ``load_from``)."""
    return _start(env_id, algo, config, "train", load_from=load_from)


def start_evaluation(env_id: str, algo: str, model_zip: str) -> str:
    """Spawn a background evaluation job for a saved/imported agent."""
    return _start(env_id, algo, {}, "eval", model_zip=model_zip)


_INTERNAL = {"cancel", "model_path"}  # never leaked to the client


def get_job(job_id: str):
    """Snapshot of a job (without internal fields), or ``None``."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        return {k: v for k, v in job.items() if k not in _INTERNAL}


def model_path(job_id: str):
    """Filesystem path of a finished job's saved model, or ``None``."""
    with _LOCK:
        job = _JOBS.get(job_id)
        path = job.get("model_path") if job else None
        return path if path and os.path.exists(path) else None


def cancel_job(job_id: str) -> bool:
    """Request cancellation; the callback stops training at the next step."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job["status"] != "running":
            return False
        job["cancel"] = True
        return True
