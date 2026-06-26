"""
Pytest bootstrap for the backend test-suite.

The end-to-end tests import the real ``app`` (and thus the shared ``SESSIONS``
singleton). We disable session persistence for that singleton *before* the app
is imported so the suite never writes a stray ``sessions.db`` into the repo and
stays purely in-memory. The dedicated persistence tests build their own store
with a temp-file DB, so they are unaffected by this toggle.
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("ML_PERSIST_SESSIONS", "0")

# Point the AI-backends store at a throwaway temp file (and start clean) so the
# suite never touches the real backend/ai_backends.json.
_ai_store = Path(tempfile.gettempdir()) / "mlauto_test_ai_backends.json"
os.environ.setdefault("ML_AI_STORE", str(_ai_store))
try:
    _ai_store.unlink()
except FileNotFoundError:
    pass
