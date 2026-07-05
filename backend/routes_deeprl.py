"""
routes_deeprl.py — Deep RL workbench endpoints (Gymnasium + Stable-Baselines3).

A dedicated router (mounted in app.py) so the Deep RL concern is isolated and
app.py stays within the file-size budget — the same pattern as routes_monitor.
Training runs as a background job (rl.deep.jobs); this router only starts jobs,
reports their progress/result, and serves the env/algo catalogue + the per-slider
AI helper (which reuses the shared, store-resolved assist agent).
"""

import shutil
import tempfile

import llm_agent
from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from pipeline.stages.base import to_native
from rl import deep as deep_rl

router = APIRouter(prefix="/api/rl/deep", tags=["deep-rl"])


class DeepRLTrainRequest(BaseModel):
    env_id: str
    algo: str = "PPO"
    config: dict = {}


class SaveAgentRequest(BaseModel):
    job_id: str
    name: str = ""


class EvaluateRequest(BaseModel):
    agent_id: str
    env_id: str = ""


class ContinueRequest(BaseModel):
    agent_id: str
    env_id: str = ""
    config: dict = {}


def _validate_train(env_id: str, algo: str):
    """Shared guard: known env + algo, and compatible action space / masking."""
    meta = deep_rl.envs.get_env(env_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Environnement inconnu : {env_id}")
    if deep_rl.algos.get_algo(algo) is None:
        raise HTTPException(status_code=404, detail=f"Algorithme inconnu : {algo}")
    if not deep_rl.algos.compatible(algo, meta["action_kind"], meta.get("maskable")):
        raise HTTPException(
            status_code=409,
            detail=f"{algo} n'est pas compatible avec {env_id} "
                   f"(action {meta['action_kind']}, masquable={bool(meta.get('maskable'))}).")
    return meta


@router.get("/catalog")
def deep_catalog():
    """Environments + algorithms (with hyperparameter schema) for the UI."""
    return to_native(deep_rl.catalog())


@router.post("/train")
def deep_train(req: DeepRLTrainRequest):
    """Start a background training job; returns the job id to poll."""
    _validate_train(req.env_id, req.algo)
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
    elif param in ("resultats", "diagnostic"):
        # Operational diagnosis: is this agent good, and what to do with it? The
        # store-resolved assist prompt does the reasoning; the focus supplies the
        # decision signals (gain vs random baseline, threshold, cyber domain).
        topic = "diagnostic opérationnel"
        focus = {
            "question": "Ce modèle est-il bon pour un usage opérationnel, et que "
                        "faire du résultat côté SOC ?",
            "domaine": body.get("group") or "apprentissage par renforcement",
            "metriques": body.get("metrics") or {},
            "recompense_aleatoire_reference": body.get("random_reward"),
            "seuil_de_reussite": body.get("threshold"),
            "bat_la_politique_aleatoire": body.get("beats_random"),
            "consigne": "Donne d'abord un verdict clair (bon / moyen / insuffisant) "
                        "justifié par le gain vs politique aléatoire et le seuil, puis "
                        "2 à 3 actions concrètes : déploiement en observation (shadow), "
                        "réglage du budget/seuil, poursuite de l'entraînement, ou "
                        "collecte de données supplémentaires.",
        }
    else:
        caption = str(body.get("caption") or param)
        topic = "graphe: " + caption
        focus = {"graphe": caption, "metriques": body.get("metrics") or {}}
    out = llm_agent.assist("Deep RL (Gymnasium + Stable-Baselines3)", "reinforcement",
                           topic, focus, "", level, _FIELDS, config)
    return to_native({**out, "param": param})


# --- "My agents": persist / import / evaluate / continue / export -------------

def _save_upload(file: UploadFile, suffix: str) -> str:
    """Stream an uploaded file to a temp path and return it."""
    fd = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(file.file, fd)
    finally:
        fd.close()
    return fd.name


def _cleanup(path: str) -> None:
    try:
        import os
        os.unlink(path)
    except OSError:
        pass


@router.get("/registry")
def deep_registry():
    """List the analyst's saved agents ("My agents")."""
    return to_native({"agents": deep_rl.registry.list_agents()})


@router.post("/save")
def deep_save(req: SaveAgentRequest):
    """Persist a finished training job's agent into the registry under a name."""
    path = deep_rl.jobs.model_path(req.job_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Modèle introuvable (job non terminé ou expiré).")
    job = deep_rl.jobs.get_job(req.job_id) or {}
    entry = deep_rl.registry.save_from_job(req.name, job.get("result") or {}, path,
                                           job.get("config") or {})
    return to_native(entry)


@router.get("/registry/{agent_id}/download")
def deep_registry_download(agent_id: str):
    """Download a saved agent's Stable-Baselines3 ``.zip``."""
    path = deep_rl.registry.agent_path(agent_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Agent introuvable.")
    return FileResponse(path, media_type="application/zip", filename=f"agent_{agent_id}.zip")


@router.get("/registry/{agent_id}/export")
def deep_registry_export(agent_id: str):
    """Export a self-describing bundle (model + report.json) for a saved agent."""
    bundle = deep_rl.registry.export_bundle(agent_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Agent introuvable.")
    return FileResponse(bundle, media_type="application/zip",
                        filename=f"agent_{agent_id}_bundle.zip")


@router.delete("/registry/{agent_id}")
def deep_registry_delete(agent_id: str):
    """Delete a saved agent (model file + index entry)."""
    if not deep_rl.registry.delete_agent(agent_id):
        raise HTTPException(status_code=404, detail="Agent introuvable.")
    return {"deleted": agent_id}


@router.post("/evaluate")
def deep_evaluate(req: EvaluateRequest):
    """Evaluate a saved agent on an environment (no training); returns a job id."""
    agent = deep_rl.registry.get_agent(req.agent_id)
    path = deep_rl.registry.agent_path(req.agent_id)
    if agent is None or path is None:
        raise HTTPException(status_code=404, detail="Agent introuvable.")
    env_id = req.env_id or agent["env_id"]
    _validate_train(env_id, agent["algo"])
    job_id = deep_rl.jobs.start_evaluation(env_id, agent["algo"], path)
    return {"job_id": job_id, "status": "running"}


@router.post("/continue")
def deep_continue(req: ContinueRequest):
    """Resume training from a saved agent (warm-start); returns a job id."""
    agent = deep_rl.registry.get_agent(req.agent_id)
    path = deep_rl.registry.agent_path(req.agent_id)
    if agent is None or path is None:
        raise HTTPException(status_code=404, detail="Agent introuvable.")
    env_id = req.env_id or agent["env_id"]
    _validate_train(env_id, agent["algo"])
    job_id = deep_rl.jobs.start_training(env_id, agent["algo"], req.config or {}, load_from=path)
    return {"job_id": job_id, "status": "running"}


@router.post("/import")
def deep_import(file: UploadFile = File(...), name: str = Form(""),
                env_id: str = Form(...), algo: str = Form(...)):
    """Import an externally-trained SB3 ``.zip`` into the registry.

    The model is validated (loadable + observation space matches the target env)
    before it is registered, so a mismatched upload fails with a clear message.
    """
    meta = _validate_train(env_id, algo)
    tmp = _save_upload(file, ".zip")
    try:
        deep_rl.evaluate.check_compatible(env_id, algo, tmp)
        entry = deep_rl.registry.import_agent(name, env_id, algo, meta.get("obs_dim"),
                                              meta.get("action_kind"), tmp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        _cleanup(tmp)
    return to_native(entry)


@router.post("/import-env")
def deep_import_env(file: UploadFile = File(...), name: str = Form("")):
    """Import a CSV alert dataset as a custom SOC-triage environment."""
    tmp = _save_upload(file, ".csv")
    try:
        meta = deep_rl.custom_envs.import_dataset(name, tmp)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        _cleanup(tmp)
    return to_native(meta)


@router.delete("/env/{env_id}")
def deep_delete_env(env_id: str):
    """Delete a user-imported CSV environment."""
    if not deep_rl.custom_envs.delete_dataset(env_id):
        raise HTTPException(status_code=404, detail="Environnement importé introuvable.")
    return {"deleted": env_id}
