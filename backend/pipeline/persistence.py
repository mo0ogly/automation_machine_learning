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
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib

logger = logging.getLogger(__name__)

# Default location: alongside the backend package (gitignored).
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "sessions.db"


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
                "  blob BLOB NOT NULL"
                ")"
            )

    # ── write-through ───────────────────────────────────────────────────
    def save(self, session) -> None:
        """Upsert the full session blob. Best-effort: a failure is logged, not raised."""
        if not self.enabled or session is None:
            return
        try:
            buf = io.BytesIO()
            joblib.dump(session, buf, compress=3)
            now = datetime.now(timezone.utc).isoformat()
            with self._connect() as con:
                con.execute(
                    "INSERT INTO sessions (id, filename, created_at, updated_at, blob) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET "
                    "  filename=excluded.filename, "
                    "  updated_at=excluded.updated_at, "
                    "  blob=excluded.blob",
                    (session.id, session.filename, session.created_at, now, buf.getvalue()),
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
