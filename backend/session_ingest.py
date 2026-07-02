"""
session_ingest.py — dataset ingestion helpers (upload guard, parsing, validation).

Extracted from app.py to keep it within the file-size budget and to group the
ingestion concern (size cap → CSV parse → degeneracy validation → session
creation) in one place. The route handlers in app.py stay thin: they call
``validated_session`` / ``session_payload`` and return the result.
"""

from __future__ import annotations

import io

import pandas as pd
from fastapi import HTTPException

import llm_agent
from pipeline import SESSIONS
from pipeline import diagnostics as dg
from pipeline import validation
from pipeline.context import detect_target_and_type
from pipeline.registry import all_stage_meta
from pipeline.stages.base import to_native

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 Mo — rejeté AVANT parsing (garde DoS mémoire)


async def read_capped(file) -> bytes:
    """Read an upload but reject oversized bodies before pandas parses them."""
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 25 Mo).")
    return raw


def read_csv(file_bytes: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV illisible : {e}")


def session_payload(session) -> dict:
    ctx = session.ctx
    return to_native({
        "session_id": session.id,
        "filename": session.filename,
        "context": ctx.to_dict(),
        "overview": dg.overview(session.raw_df, ctx.target_col),
        "data_quality": session.data_quality or [],
        "stages": all_stage_meta(),
        "status": session.stage_status(),
        "agent": llm_agent.agent_status(),
    })


def validated_session(filename: str, df: pd.DataFrame):
    """Create a session after ingestion validation: reject fatally-degenerate
    datasets with a clear 400, and attach non-fatal quality warnings to the
    session so the analyst sees them (with an AI helper) instead of hitting an
    opaque crash deep in a stage."""
    target, _ptype = detect_target_and_type(df)
    fatal, warnings = validation.validate_dataset(df, target)
    if fatal:
        raise HTTPException(status_code=400, detail=fatal)
    session = SESSIONS.create(filename, df)
    session.data_quality = warnings
    SESSIONS.save(session)
    return session
