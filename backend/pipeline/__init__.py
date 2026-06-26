"""
pipeline — Staged, replayable ML construction for the ML Automator.

The ML construction is decomposed into explicit, inspectable, replayable stages:

    Nettoyage  -> Transformation -> Integration -> Separation -> Model -> Evaluation
    (clean)       (transform)        (integrate)    (separate)    (model)  (evaluate)

Each stage is a small module under ``pipeline.stages`` exposing a uniform contract
(``default_config``, ``config_schema``, ``diagnose``, ``run``) so an expert can,
inside an agentic loop, inspect each stage's diagnostics, read the LLM agent's
refinement recommendation, adjust the config, and re-run that single stage.
"""

from .context import PipelineContext, detect_target_and_type
from .session import Session, SessionStore, SESSIONS
from .persistence import SessionPersistence
from .registry import STAGES, STAGE_IDS, get_stage, stage_meta

__all__ = [
    "PipelineContext",
    "detect_target_and_type",
    "Session",
    "SessionStore",
    "SessionPersistence",
    "SESSIONS",
    "STAGES",
    "STAGE_IDS",
    "get_stage",
    "stage_meta",
]
