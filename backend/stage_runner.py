"""
stage_runner.py — resilient single-stage execution orchestration.

Extracted from app.py so the pipeline's execution/error-handling concern lives in
one place (and app.py stays within the file-size budget). Runs one stage against
a session, records the result, and — crucially — converts ANY stage failure into
a clean, actionable HTTP error instead of an opaque 500 + stack trace. This is
what makes ``autorun`` resilient: it only ever has to handle ``HTTPException``.
"""

from __future__ import annotations

from fastapi import HTTPException

from pipeline import plotting
from pipeline.registry import get_stage, stage_meta, DATA_STAGE_IDS


def stage_error(stage_id, exc):
    """Map a stage exception to a clean HTTP error.

    ``ValueError`` is an expected, explained precondition (a stage validating its
    inputs) → 409. Anything else is an unexpected failure attributed to this
    stage → 422 with an analyst-facing message (no stack trace leaks out).
    """
    if isinstance(exc, HTTPException):
        return exc
    title = stage_meta(stage_id)["title"]
    if isinstance(exc, ValueError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=(
        f"L'étape « {title} » a échoué ({type(exc).__name__}). Vérifiez la configuration "
        "et la qualité du jeu de données, puis réessayez."))


def run_stage(session, stage_id, config):
    """Execute one stage, record it on the session, and return its result dict.

    Data stages consume the upstream dataframe; model/evaluate stages consume the
    session artefacts. Every path is wrapped so a failure surfaces as a clean
    409/422, never a 500.
    """
    stage = get_stage(stage_id)
    ctx = session.ctx
    if stage_id in DATA_STAGE_IDS:
        df_in, err = session.input_df_for(stage_id)
        if err:
            raise HTTPException(status_code=409, detail=err)
        try:
            with plotting.PLOT_LOCK:  # serialise pyplot (not thread-safe)
                if getattr(stage, "NEEDS_SESSION", False):  # separate: train-only preprocessor fit
                    out = stage.run(df_in, config, ctx, session=session)
                else:
                    out = stage.run(df_in, config, ctx)
        except Exception as e:  # no opaque 500 — attribute the failure to this stage
            raise stage_error(stage_id, e)
        if isinstance(out, tuple) and len(out) == 3:
            df_out, result, artifacts = out
        else:
            df_out, result = out
            artifacts = None
        session.record(stage_id, config, result, output_df=df_out, artifacts=artifacts)
        return result

    # model / evaluate operate on session artefacts
    try:
        with plotting.PLOT_LOCK:
            result, artifacts = stage.run(session, config)
    except Exception as e:
        raise stage_error(stage_id, e)
    session.record(stage_id, config, result, output_df=None, artifacts=artifacts)
    return result
