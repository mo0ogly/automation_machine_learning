"""
Pytest bootstrap for the backend test-suite.

The end-to-end tests import the real ``app`` (and thus the shared ``SESSIONS``
singleton). We disable session persistence for that singleton *before* the app
is imported so the suite never writes a stray ``sessions.db`` into the repo and
stays purely in-memory. The dedicated persistence tests build their own store
with a temp-file DB, so they are unaffected by this toggle.
"""

import os

os.environ.setdefault("ML_PERSIST_SESSIONS", "0")
