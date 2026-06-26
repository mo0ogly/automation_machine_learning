"""
persistence.py — SQLite-backed write-through store for pipeline sessions.

A :class:`~pipeline.session.Session` holds DataFrames, fitted scikit-learn /
XGBoost models, numpy arrays and encoders — none of which are JSON-serialisable.
Rather than hand-serialise each artefact type (fragile, and it would need
touching every time a stage produces a new artefact), we persist each session as
a single ``joblib`` blob keyed by its id. ``session.py`` was written for exactly
this swap: *"structured so that swapping in a persistent store later is
mechanical."*

This is safe here because the only blob ever unpickled is one this same app
wrote to its own local SQLite file — there is no untrusted input. The layer is
deliberately a thin write-through behind :class:`SessionStore`: the in-memory
dict stays the hot cache, SQLite is the durable mirror that survives a restart.

Configuration (read by the ``SESSIONS`` singleton, see ``session.py``):

* ``ML_PERSIST_SESSIONS`` — ``"0"`` disables persistence (pure in-memory).
* ``ML_SESSION_DB``       — override the SQLite file path.

A blob that fails to load (e.g. a stale pickle from an incompatible code
version) is treated as *absent* rather than fatal: the session is simply lost,
never the whole app.
"""

import io
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib

logger = logging.getLogger(__name__)

# Default location: alongside the backend package (gitignored).
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "sessions.db"


def _session_summary(session) -> dict:
    """Cheap metadata snapshot for the session-list view — no blob reload.

    Computed from attributes already in memory (shape, context, recorded runs)
    so the CRUD menu can show problem type, size and whether a model exists
    without rehydrating every session. Defensive: a missing attribute never
    breaks listing.
    """
    try:
        df = getattr(session, "raw_df", None)
        n_rows, n_cols = (int(df.shape[0]), int(df.shape[1])) if df is not None else (None, None)
        ctx = getattr(session, "ctx", None)
        model = None
        try:
            mdl, _origin = session.current_model()
            model = type(mdl).__name__ if mdl is not None else None
        except Exception:
            model = None
        runs = getattr(session, "runs", {}) or {}
        stages_done = sorted(sid for sid, r in runs.items()
                             if r is not None and not getattr(r, "stale", False))
        return {
            "problem_type": getattr(ctx, "problem_type", None),
            "target": getattr(ctx, "target_col", None),
            "n_rows": n_rows, "n_cols": n_cols,
            "model": model, "stages_done": stages_done,
        }
    except Exception:  # metadata is best-effort, never fatal
        return {}


class SessionPersistence:
    """Durable mirror of the session registry, one joblib blob per session."""

    def __init__(self, db_path: Optional[str] = None, enabled: bool = True):
        self.enabled = enabled
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB
        if self.enabled:
            try:
                self._init_db()
            except Exception as exc:  # never let a DB hiccup brick startup
                logger.warning("Session persistence disabled (init failed): %s", exc)
                self.enabled = False

    # ── connection / schema ─────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path), timeout=10.0)
        # WAL gives readers/writers better concurrency under the uvicorn threadpool.
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS sessions ("
                "  id TEXT PRIMARY KEY,"
                "  filename TEXT,"
                "  created_at TEXT,"
                "  updated_at TEXT,"
                "  summary TEXT,"
                "  blob BLOB NOT NULL"
                ")"
            )
            # Additive migration for DBs created before the summary column existed.
            cols = [r[1] for r in con.execute("PRAGMA table_info(sessions)").fetchall()]
            if "summary" not in cols:
                con.execute("ALTER TABLE sessions ADD COLUMN summary TEXT")

    # ── write-through ───────────────────────────────────────────────────
    def save(self, session) -> None:
        """Upsert the full session blob. Best-effort: a failure is logged, not raised."""
        if not self.enabled or session is None:
            return
        try:
            buf = io.BytesIO()
            joblib.dump(session, buf, compress=3)
            now = datetime.now(timezone.utc).isoformat()
            summary = json.dumps(_session_summary(session))
            with self._connect() as con:
                con.execute(
                    "INSERT INTO sessions (id, filename, created_at, updated_at, summary, blob) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "  filename=excluded.filename, "
                    "  updated_at=excluded.updated_at, "
                    "  summary=excluded.summary, "
                    "  blob=excluded.blob",
                    (session.id, session.filename, session.created_at, now, summary, buf.getvalue()),
                )
        except Exception as exc:  # persistence must never break a live request
            logger.warning("Session %s not persisted: %s", getattr(session, "id", "?"), exc)

    # ── read ────────────────────────────────────────────────────────────
    def load(self, session_id: str):
        """Rehydrate one session, or ``None`` if absent / unreadable."""
        if not self.enabled:
            return None
        try:
            with self._connect() as con:
                row = con.execute(
                    "SELECT blob FROM sessions WHERE id=?", (session_id,)
                ).fetchone()
        except Exception as exc:
            logger.warning("Session %s could not be read: %s", session_id, exc)
            return None
        if not row:
            return None
        try:
            return joblib.load(io.BytesIO(row[0]))
        except Exception as exc:  # stale/incompatible blob -> treat as missing
            logger.warning("Session %s blob unreadable (dropped): %s", session_id, exc)
            self.drop(session_id)
            return None

    def load_all_ids(self) -> list:
        """Ids of every persisted session, newest first (for diagnostics / warm-up)."""
        if not self.enabled:
            return []
        try:
            with self._connect() as con:
                rows = con.execute(
                    "SELECT id FROM sessions ORDER BY updated_at DESC"
                ).fetchall()
            return [r[0] for r in rows]
        except Exception as exc:
            logger.warning("Could not list persisted sessions: %s", exc)
            return []

    def drop(self, session_id: str) -> None:
        if not self.enabled:
            return
        try:
            with self._connect() as con:
                con.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        except Exception as exc:
            logger.warning("Session %s could not be deleted: %s", session_id, exc)

    def list_meta(self) -> list:
        """Lightweight metadata for every session, newest first (for the CRUD menu).

        Reads only the indexed columns + the cached ``summary`` JSON — never a
        blob — so listing stays cheap. Rows persisted before the summary column
        existed are backfilled once (load → compute → persist) so legacy sessions
        still show their problem type and whether they carry a trained model.
        """
        if not self.enabled:
            return []
        try:
            with self._connect() as con:
                rows = con.execute(
                    "SELECT id, filename, created_at, updated_at, summary, length(blob) "
                    "FROM sessions ORDER BY updated_at DESC"
                ).fetchall()
        except Exception as exc:
            logger.warning("Could not list sessions: %s", exc)
            return []
        out = []
        for sid, fn, created, updated, summ, blen in rows:
            summary = None
            if summ:
                try:
                    summary = json.loads(summ)
                except Exception:
                    summary = None
            if summary is None:  # legacy row -> backfill once
                summary = self._backfill_summary(sid)
            out.append({
                "id": sid, "filename": fn, "created_at": created,
                "updated_at": updated, "size_bytes": blen, "summary": summary,
            })
        return out

    def _backfill_summary(self, session_id: str) -> Optional[dict]:
        """Compute + persist the summary of a legacy row. Returns it (or None)."""
        session = self.load(session_id)  # may drop + return None on a stale blob
        if session is None:
            return None
        summary = _session_summary(session)
        try:
            with self._connect() as con:
                con.execute("UPDATE sessions SET summary=? WHERE id=?",
                            (json.dumps(summary), session_id))
        except Exception as exc:
            logger.warning("Session %s summary not backfilled: %s", session_id, exc)
        return summary
