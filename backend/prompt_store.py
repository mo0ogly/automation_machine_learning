"""
prompt_store.py — persisted overrides for the agent's AI prompts.

The default prompts (system instructions + per-stage few-shot examples) live in
``agent_prompts.py``. This store holds *overrides* edited from the UI (the
"Prompts IA" panel): a flat ``{prompt_id: value}`` map persisted to a gitignored
JSON next to the backend (``backend/prompt_overrides.json``, override with
``ML_PROMPT_STORE``).

A value is a plain string for text prompts (system instructions) or a JSON value
(list/dict) for few-shot examples. :meth:`resolve` returns the override when set,
else the supplied default — so editing a prompt takes effect on the next agent
call (hot reload) without restarting the backend.
"""

import json
import os
import threading
from pathlib import Path

_DEFAULT_PATH = Path(__file__).resolve().parent / "prompt_overrides.json"


class PromptStore:
    """Thread-safe JSON-backed map of prompt overrides keyed by prompt id."""

    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get("ML_PROMPT_STORE") or _DEFAULT_PATH)
        self._lock = threading.RLock()
        self._data = {"overrides": {}}
        self._load()

    # ── persistence ─────────────────────────────────────────────────────
    def _load(self):
        try:
            if self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                ov = d.get("overrides", {})
                self._data = {"overrides": ov if isinstance(ov, dict) else {}}
        except Exception:
            self._data = {"overrides": {}}

    def _save(self):
        try:
            self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass  # best-effort: a write failure must never break a request

    # ── reads ───────────────────────────────────────────────────────────
    def overrides(self) -> dict:
        with self._lock:
            return dict(self._data["overrides"])

    def is_overridden(self, prompt_id: str) -> bool:
        with self._lock:
            return prompt_id in self._data["overrides"]

    def resolve(self, prompt_id: str, default):
        """Return the stored override for ``prompt_id`` or ``default`` when unset."""
        with self._lock:
            return self._data["overrides"].get(prompt_id, default)

    # ── writes ──────────────────────────────────────────────────────────
    def set(self, prompt_id: str, value):
        with self._lock:
            self._data["overrides"][str(prompt_id)] = value
            self._save()

    def reset(self, prompt_id: str):
        with self._lock:
            self._data["overrides"].pop(prompt_id, None)
            self._save()


# Process-wide store.
STORE = PromptStore()
