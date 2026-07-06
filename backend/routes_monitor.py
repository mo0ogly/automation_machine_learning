"""
routes_monitor.py — post-deployment drift & stability monitoring endpoint.

A dedicated router (mounted in app.py) so the monitoring concern is isolated and
app.py stays within the file-size budget. The analyst uploads a NEW batch of raw
rows; the server compares it to the training reference (data drift), the
prediction distribution (concept drift), checks reproducibility, and — when the
batch is labelled — re-calibrates the operating point. No model re-fit.
"""

import io
import json

import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from pipeline import SESSIONS
from pipeline import monitoring
from pipeline import monitoring_plots
from pipeline import plotting
from pipeline import scoring
from pipeline import stability
from pipeline import stability_plots
from pipeline.stages.base import to_native
from session_ingest import read_capped

router = APIRouter(prefix="/api/session", tags=["monitoring"])


def _require_trained(session_id: str):
    session = SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session inconnue.")
    if session.get_run("separate") is None or session.get_run("model") is None:
        raise HTTPException(status_code=409, detail="Entraînez et évaluez le modèle d'abord.")
    return session


@router.post("/{session_id}/monitor")
async def monitor(session_id: str, file: UploadFile = File(...),
                  cost_fn: float = Form(None), cost_fp: float = Form(None),
                  metadata: str = Form(None)):
    """Drift & stability report for an uploaded batch of new raw rows.

    Returns the full report (data drift, prediction/concept drift, reproducibility,
    execution-environment comparison, re-calibrated operating point) plus figures.
    ``metadata`` is an optional JSON object of operational context for the batch
    (e.g. ``{"node": "gpu-03", "throttling": true, "temp_c": 82}``); malformed
    JSON is ignored rather than failing the request.
    """
    session = _require_trained(session_id)
    try:
        df = pd.read_csv(io.BytesIO(await read_capped(file)))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV illisible : {e}")
    if df.empty:
        raise HTTPException(status_code=400, detail="Le lot est vide.")

    exec_meta = None
    if metadata:
        try:
            parsed = json.loads(metadata)
            exec_meta = parsed if isinstance(parsed, dict) else None
        except Exception:
            exec_meta = None  # best-effort hint; never fail the report on bad JSON

    try:
        with plotting.PLOT_LOCK:  # serialise pyplot (not thread-safe)
            report = monitoring.drift_report(session, df, cost_fn=cost_fn, cost_fp=cost_fp,
                                             exec_meta=exec_meta)
            plots = monitoring_plots.monitoring_plots(report) if report.get("available") else []
    except Exception as e:
        raise HTTPException(status_code=422, detail=(
            f"Surveillance impossible ({type(e).__name__}). Vérifiez que le lot a les mêmes "
            "colonnes que le jeu d'entraînement."))
    return to_native({**report, "plots": plots})


@router.post("/{session_id}/jitter")
async def jitter(session_id: str):
    """Prediction-stability ("jitter") protocol on the reference set.

    No upload needed: the server perturbs the held-out reference with Gaussian
    noise at increasing amplitudes (fractions of each feature's std), re-scores,
    and reports the flip-rate curve with a verdict. Deterministic (fixed seed).
    """
    session = _require_trained(session_id)
    try:
        with plotting.PLOT_LOCK:
            report = monitoring.jitter_protocol(session)
            plots = [monitoring_plots.jitter_plot(report)] if report.get("available") else []
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Protocole jitter impossible ({type(e).__name__}).")
    return to_native({**report, "plots": plots})


@router.post("/{session_id}/stability/{analysis}")
async def stability_analysis(session_id: str, analysis: str):
    """One advanced stability analysis on the reference set (no upload).

    ``analysis`` in {numerical, margin, churn, conformal, smoothing} — see
    pipeline/stability.py. Uniform display contract: verdict + summary rows +
    notes + one figure. Deterministic (fixed seed).
    """
    fn = stability.ANALYSES.get(analysis)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"Analyse inconnue : {analysis}.")
    session = _require_trained(session_id)
    try:
        report = fn(session)                       # compute outside the plot lock
        plots = []
        if report.get("available"):
            with plotting.PLOT_LOCK:               # pyplot only under the lock
                plots = [stability_plots.PLOTS[analysis](report)]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Analyse impossible ({type(e).__name__}).")
    # Trim the raw distributions (only needed to draw the figure server-side).
    for k in ("score_deltas", "margins", "p_values", "residuals", "set_sizes", "radii"):
        report.pop(k, None)
    return to_native({**report, "analysis": analysis, "plots": plots})


@router.post("/{session_id}/batch-monitor")
async def batch_monitor(session_id: str, file: UploadFile = File(...),
                        cost_fn: float = Form(None), cost_fp: float = Form(None)):
    """Scheduled-batch operations endpoint: score a new batch AND assess drift in
    ONE call, with an actionable verdict. Designed to be hit periodically by an
    external scheduler (cron / CI) — 'scheduled batch scoring' without an in-process
    scheduler dependency. Returns the scored rows (CSV + summary) plus a compact
    drift verdict, so an ops pipeline can route alerts and flag re-training.
    """
    session = _require_trained(session_id)
    try:
        df = pd.read_csv(io.BytesIO(await read_capped(file)))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV illisible : {e}")
    if df.empty:
        raise HTTPException(status_code=400, detail="Le lot est vide.")

    try:
        with plotting.PLOT_LOCK:
            enriched, summary = scoring.score_dataframe(session, df)
            drift = monitoring.drift_report(session, df, cost_fn=cost_fn, cost_fp=cost_fp)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=(
            f"Batch-monitor impossible ({type(e).__name__}). Vérifiez que le lot a les mêmes "
            "colonnes que le jeu d'entraînement."))

    # Actionable verdict for an automation pipeline.
    overall = drift.get("overall") if drift.get("available") else None
    repro = (drift.get("reproducibility") or {}).get("deterministic", True)
    if overall == "major" or repro is False:
        action = "action_required"
    elif overall == "moderate":
        action = "review"
    else:
        action = "ok"

    return to_native({
        "n_scored": int(len(enriched)),
        "scoring_summary": summary,
        "action": action,
        "drift": {
            "available": drift.get("available", False),
            "overall": overall,
            "data_drift": (drift.get("data_drift") or {}).get("verdict"),
            "prediction_drift": (drift.get("prediction_drift") or {}).get("level"),
            "reproducibility": (drift.get("reproducibility") or {}).get("verdict"),
            "recalibration": drift.get("recalibration"),
        },
        "csv": enriched.to_csv(index=False),
    })
