"""
session.py — Replayable per-session pipeline state.

This is what turns a one-shot script into an *expert-in-the-loop* tool. Every
data stage caches the dataframe it consumed and the dataframe it produced. The
expert can therefore re-run a single stage with a refined config; downstream
stages are automatically invalidated (marked ``stale``) so the UI knows they
must be replayed on the new upstream output.

State is in-memory (single-process, local app). It is intentionally simple — no
DB — but structured so that swapping in a persistent store later is mechanical.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from .context import PipelineContext

# Stages that transform the dataframe, in canonical order.
DATA_STAGES = ["clean", "transform", "integrate", "separate"]
# Stages that consume artefacts produced by `separate` (in canonical order):
# model trains a baseline, tune refines it (GridSearch), evaluate scores the
# current model, explain interprets it (SHAP).
MODEL_STAGES = ["model", "tune", "evaluate", "explain"]


@dataclass
class StageRun:
    stage_id: str
    config: dict
    result: dict
    output_df: Optional[pd.DataFrame] = None
    artifacts: dict = field(default_factory=dict)
    stale: bool = False
    ran_at: str = ""


class Session:
    """Holds the raw dataframe, the context, and every recorded stage run."""

    def __init__(self, filename: str, raw_df: pd.DataFrame):
        self.id = uuid.uuid4().hex[:12]
        self.filename = filename
        self.raw_df = raw_df
        self.ctx = PipelineContext.from_df(raw_df)
        self.runs: dict[str, StageRun] = {}
        self.created_at = datetime.now(timezone.utc).isoformat()
        # Assisted-mode memory: every AI interaction (sub-step explanation,
        # refinement proposal, interpretation) is journalled so later prompts
        # can be conditioned on it. `level` tunes explanation verbosity.
        self.insights: list[dict] = []
        self._insight_seq = 0
        self.level = "novice"  # "novice" | "expert"
        # Multi-turn chat thread with the AI cockpit copilot. Distinct from
        # `insights` (which journals one-shot helpers): this is a real ordered
        # conversation of {role, content} turns replayed to the LLM each turn.
        self.chat: list[dict] = []
        self._chat_seq = 0
        # Data-quality warnings from ingestion validation (validation.py). Non-fatal
        # issues (constant columns, heavy missing, degenerate target…) surfaced to
        # the analyst. Set by the ingestion route; None until then.
        self.data_quality: Optional[list] = None

    # ── assisted-mode memory ────────────────────────────────────────────
    def add_insight(self, stage: str, topic: str, label: str, text,
                    source: str = "llm", model: Optional[str] = None) -> dict:
        self._insight_seq += 1
        entry = {
            "id": self._insight_seq, "stage": stage, "topic": topic, "label": label,
            "text": text, "source": source, "model": model,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.insights.append(entry)
        return entry

    def journal_summary(self, limit: int = 10, maxlen: int = 240) -> str:
        """Compact, prompt-ready recap of recent AI exchanges (the memory)."""
        if not self.insights:
            return ""
        lines = []
        for e in self.insights[-limit:]:
            txt = e["text"]
            if isinstance(txt, (list, tuple)):
                txt = " ".join(str(x) for x in txt)
            txt = str(txt).strip().replace("\n", " ")
            if len(txt) > maxlen:
                txt = txt[:maxlen] + "…"
            lines.append(f"- [{e['stage']}/{e['topic']}] {txt}")
        return "JOURNAL D'ANALYSE (mémoire des échanges précédents) :\n" + "\n".join(lines)

    # ── conversational memory (AI cockpit chat) ─────────────────────────
    def _ensure_chat(self):
        """Lazily initialise the chat fields — a Session rehydrated from a blob
        written before the cockpit existed has neither attribute."""
        if not hasattr(self, "chat") or self.chat is None:
            self.chat = []
        if not hasattr(self, "_chat_seq"):
            self._chat_seq = len(self.chat)

    def add_chat_message(self, role: str, content, source: str = "llm",
                         model: Optional[str] = None) -> dict:
        """Append one turn (role = 'user' | 'assistant') to the conversation."""
        self._ensure_chat()
        self._chat_seq += 1
        entry = {
            "id": self._chat_seq, "role": role, "content": content,
            "source": source, "model": model,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.chat.append(entry)
        return entry

    def chat_history(self, limit: int = 20) -> list:
        """The last ``limit`` turns as ``[{role, content}]`` for the LLM (oldest
        first). Kept bounded so the prompt stays within the context window.
        Static failure replies (no backend / error) are skipped so they are not
        replayed as real assistant turns once a backend is configured."""
        self._ensure_chat()
        usable = [e for e in self.chat
                  if not (e["role"] == "assistant" and e.get("source") in ("none", "error"))]
        return [{"role": e["role"], "content": e["content"]} for e in usable[-limit:]]

    def chat_thread(self) -> list:
        """Full conversation with metadata, for the UI."""
        self._ensure_chat()
        return list(self.chat)

    def clear_chat(self):
        self.chat = []
        self._chat_seq = 0

    # ── input resolution ────────────────────────────────────────────────
    def _prev_data_stage(self, stage_id: str) -> Optional[str]:
        if stage_id not in DATA_STAGES:
            return None
        idx = DATA_STAGES.index(stage_id)
        return DATA_STAGES[idx - 1] if idx > 0 else None

    def input_df_for(self, stage_id: str):
        """
        Resolve the dataframe a data stage should consume.

        Returns ``(df, error)``. ``error`` is a human string when an upstream
        stage still needs to (re-)run first; in that case ``df`` is ``None``.
        """
        prev = self._prev_data_stage(stage_id)
        if prev is None:
            return self.raw_df, None
        run = self.runs.get(prev)
        if run is None:
            return None, f"L'étape « {prev} » doit être exécutée avant « {stage_id} »."
        if run.stale:
            return None, f"L'étape « {prev} » est obsolète — relancez-la avant « {stage_id} »."
        return run.output_df, None

    def latest_df(self) -> pd.DataFrame:
        """Output of the furthest non-stale data stage, else the raw frame."""
        df = self.raw_df
        for sid in DATA_STAGES:
            run = self.runs.get(sid)
            if run is None or run.stale or run.output_df is None:
                break
            df = run.output_df
        return df

    # ── recording + invalidation ────────────────────────────────────────
    def record(self, stage_id: str, config: dict, result: dict,
               output_df: Optional[pd.DataFrame] = None, artifacts: Optional[dict] = None):
        run = StageRun(
            stage_id=stage_id,
            config=config,
            result=result,
            output_df=output_df,
            artifacts=artifacts or {},
            stale=False,
            ran_at=datetime.now(timezone.utc).isoformat(),
        )
        self.runs[stage_id] = run
        self._invalidate_downstream(stage_id)
        return run

    def _invalidate_downstream(self, stage_id: str):
        """Mark every stage that depends on `stage_id`'s output as stale."""
        if stage_id in DATA_STAGES:
            idx = DATA_STAGES.index(stage_id)
            downstream = DATA_STAGES[idx + 1:] + MODEL_STAGES
        elif stage_id == "model":
            downstream = ["tune", "evaluate", "explain"]
        elif stage_id == "tune":
            downstream = ["evaluate", "explain"]
        else:
            downstream = []
        for sid in downstream:
            if sid in self.runs:
                self.runs[sid].stale = True

    def current_model(self):
        """The model to evaluate / explain: the tuned one if fresh, else the baseline.

        Returns ``(model, origin)`` where origin is 'tuned' | 'baseline' | None.
        """
        tune = self.runs.get("tune")
        if tune is not None and not tune.stale and tune.artifacts.get("model") is not None:
            return tune.artifacts["model"], "tuned"
        mdl = self.runs.get("model")
        if mdl is not None and not mdl.stale and mdl.artifacts.get("model") is not None:
            return mdl.artifacts["model"], "baseline"
        return None, None

    # ── views ───────────────────────────────────────────────────────────
    def stage_status(self) -> list:
        order = DATA_STAGES + MODEL_STAGES
        out = []
        for sid in order:
            run = self.runs.get(sid)
            out.append({
                "stage_id": sid,
                "ran": run is not None,
                "stale": bool(run.stale) if run else False,
                "ran_at": run.ran_at if run else None,
            })
        return out

    def get_run(self, stage_id: str) -> Optional[StageRun]:
        return self.runs.get(stage_id)


class SessionStore:
    """Process-wide registry of active sessions.

    The in-memory dict is the hot cache. When a ``persistence`` backend is
    injected, every created/mutated session is mirrored to it (write-through),
    and ``get`` rehydrates from it on a cache miss — so sessions survive a
    backend restart. With no backend the store is pure in-memory, as before.
    """

    def __init__(self, persistence=None):
        self._sessions: dict[str, Session] = {}
        self._persistence = persistence

    def create(self, filename: str, raw_df: pd.DataFrame) -> Session:
        s = Session(filename, raw_df)
        self._sessions[s.id] = s
        self.save(s)
        return s

    def get(self, session_id: str) -> Optional[Session]:
        s = self._sessions.get(session_id)
        if s is None and self._persistence is not None:
            s = self._persistence.load(session_id)
            if s is not None:
                self._sessions[session_id] = s  # warm the cache
        return s

    def save(self, session: Optional[Session]) -> None:
        """Persist a session after a mutation. No-op without a backend."""
        if session is not None and self._persistence is not None:
            self._persistence.save(session)

    def drop(self, session_id: str):
        self._sessions.pop(session_id, None)
        if self._persistence is not None:
            self._persistence.drop(session_id)

    def list(self) -> list:
        """Metadata for every known session, newest first (CRUD menu)."""
        if self._persistence is not None:
            return self._persistence.list_meta()
        # Pure in-memory fallback (persistence disabled): no durable summary.
        return [
            {"id": s.id, "filename": s.filename, "created_at": s.created_at,
             "updated_at": s.created_at, "size_bytes": None, "summary": None}
            for s in sorted(self._sessions.values(), key=lambda s: s.created_at, reverse=True)
        ]

    def rename(self, session_id: str, name: str) -> Optional[Session]:
        """Set a session's display name (its ``filename``) and persist it."""
        s = self.get(session_id)
        if s is None:
            return None
        s.filename = name
        self.save(s)
        return s


def _build_default_store() -> SessionStore:
    """Wire the shared store, honouring the persistence env toggles."""
    import os

    if os.environ.get("ML_PERSIST_SESSIONS", "1") == "0":
        return SessionStore()
    try:
        from .persistence import SessionPersistence
        backend = SessionPersistence(db_path=os.environ.get("ML_SESSION_DB") or None)
        return SessionStore(persistence=backend)
    except Exception:  # any wiring failure -> degrade to in-memory, never crash import
        return SessionStore()


# Single shared store for the running app.
SESSIONS = _build_default_store()
