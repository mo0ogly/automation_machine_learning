"""
routes_deeprl.py — Deep RL workbench endpoints (Gymnasium + Stable-Baselines3).

A dedicated router (mounted in app.py) so the Deep RL concern is isolated and
app.py stays within the file-size budget — the same pattern as routes_monitor.
Training runs as a background job (rl.deep.jobs); this router only starts jobs,
reports their progress/result, and serves the env/algo catalogue + the per-slider
AI helper (which reuses the shared, store-resolved assist agent).
"""

import llm_agent
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline.stages.base import to_native
from rl import deep as deep_rl

router = APIRouter(prefix="/api/rl/deep", tags=["deep-rl"])


class DeepRLTrainRequest(BaseModel):
    env_id: str
    algo: str = "PPO"
    config: dict = {}


@router.get("/catalog")
def deep_catalog():
    """Environments + algorithms (with hyperparameter schema) for the UI."""
    return to_native(deep_rl.catalog())


@router.post("/train")
def deep_train(req: DeepRLTrainRequest):
    """Start a background training job; returns the job id to poll."""
    if deep_rl.envs.get_env(req.env_id) is None:
        raise HTTPException(status_code=404, detail=f"Environnement inconnu : {req.env_id}")
    if deep_rl.algos.get_algo(req.algo) is None:
        raise HTTPException(status_code=404, detail=f"Algorithme inconnu : {req.algo}")
    kind = deep_rl.envs.action_kind(req.env_id)
    if not deep_rl.algos.supports(req.algo, kind):
        raise HTTPException(
            status_code=409,
            detail=f"{req.algo} ne supporte pas un espace d'action {kind}. "
                   f"Choisissez PPO ou A2C pour cet environnement.")
    job_id = deep_rl.jobs.start_training(req.env_id, req.algo, req.config or {})
    return {"job_id": job_id, "status": "running"}


@router.get("/job/{job_id}")
def deep_job(job_id: str):
    """Poll a training job: status, progress, and result once finished."""
    job = deep_rl.jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job d'entraînement inconnu ou expiré.")
    return to_native(job)


@router.get("/job/{job_id}/download")
def deep_job_download(job_id: str):
    """Download the trained agent as a self-contained Stable-Baselines3 ``.zip``."""
    path = deep_rl.jobs.model_path(job_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Modèle introuvable (job non terminé ou expiré).")
    return FileResponse(path, media_type="application/zip",
                        filename=f"deeprl_agent_{job_id}.zip")


@router.post("/job/{job_id}/cancel")
def deep_job_cancel(job_id: str):
    """Request cancellation of a running job (stops at the next training step)."""
    ok = deep_rl.jobs.cancel_job(job_id)
    if not ok:
        raise HTTPException(status_code=409, detail="Job introuvable ou déjà terminé.")
    return {"job_id": job_id, "status": "cancelling"}


_FIELDS = deep_rl.deep_rl_fields()
_FIELDS_BY_NAME = {f["name"]: f for f in _FIELDS}


@router.post("/explain")
def deep_explain(body: dict = Body(default={})):
    """AI helper for the Deep RL view (reuses the session-free assist agent).

    Handles two kinds of request, keyed by ``param``:
      - a hyperparameter name (``learning_rate``, ``gamma``, …) -> explain the slider
        and, when relevant, suggest an applicable value;
      - anything else (e.g. ``"graphe: courbe d'apprentissage"``) -> explain a
        result graph, using the run's metrics as context.
    """
    param = str(body.get("param") or "")
    level = str(body.get("level") or "novice").lower()
    config = body.get("config") or {}
    field = _FIELDS_BY_NAME.get(param)
    if field is not None:
        topic, focus = "param:" + param, {"parametre": field}
    else:
        caption = str(body.get("caption") or param)
        topic = "graphe: " + caption
        focus = {"graphe": caption, "metriques": body.get("metrics") or {}}
    out = llm_agent.assist("Deep RL (Gymnasium + Stable-Baselines3)", "reinforcement",
                           topic, focus, "", level, _FIELDS, config)
    return to_native({**out, "param": param})
