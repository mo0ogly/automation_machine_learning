"""
ai_store.py — persisted registry of configured AI backends (+ their secrets).

A *backend* pins a provider + model (+ ``base_url`` for ``openai_compat``). API
keys are **write-only from the UI**: stored here server-side and never returned —
the API only exposes ``key_configured``. State lives in a gitignored JSON next to
the backend (``backend/ai_backends.json``, override with ``ML_AI_STORE``).

On first run a Groq backend is **auto-seeded** when ``GROQ_API_KEY`` is present,
so the app is usable out of the box and the panel shows one ready backend.

The key resolution order for a call (see :meth:`resolve`) mirrors recette_IA_agents
(R8): the per-backend stored secret first, else the provider's env var.
"""

import json
import os
import threading
from pathlib import Path

import env_loader
from ai_providers import get_provider, resolve_endpoint

_DEFAULT_PATH = Path(__file__).resolve().parent / "ai_backends.json"


class AiStore:
    """Thread-safe JSON-backed store of backends, secrets and the active id."""

    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get("ML_AI_STORE") or _DEFAULT_PATH)
        self._lock = threading.RLock()
        self._data = {"backends": [], "active": None, "secrets": {}}
        self._load()
        self._autoseed()

    # ── persistence ─────────────────────────────────────────────────────
    def _load(self):
        try:
            if self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                self._data = {
                    "backends": d.get("backends", []),
                    "active": d.get("active"),
                    "secrets": d.get("secrets", {}),
                }
        except Exception:
            self._data = {"backends": [], "active": None, "secrets": {}}

    def _save(self):
        try:
            self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass  # best-effort: a write failure must never break a request

    def _autoseed(self):
        with self._lock:
            if self._data["backends"]:
                return
            if env_loader.get("GROQ_API_KEY"):
                p = get_provider("groq")
                self._data["backends"].append(
                    {"id": "groq-default", "provider": "groq", "model": p["default_model"]})
                self._data["active"] = "groq-default"
                self._save()

    # ── reads ───────────────────────────────────────────────────────────
    def _get(self, backend_id):
        return next((b for b in self._data["backends"] if b["id"] == backend_id), None)

    def _public(self, b):
        return {
            "id": b["id"], "provider": b["provider"], "model": b["model"],
            "base_url": b.get("base_url"),
            "key_configured": b["id"] in self._data["secrets"],
            "active": b["id"] == self._data["active"],
        }

    def list_backends(self) -> list:
        """Configured backends WITHOUT secrets (UI-safe)."""
        with self._lock:
            return [self._public(b) for b in self._data["backends"]]

    def active_id(self):
        with self._lock:
            return self._data["active"]

    # ── writes ──────────────────────────────────────────────────────────
    def create(self, backend: dict) -> dict:
        with self._lock:
            bid = str(backend.get("id") or "").strip()
            if not bid:
                raise ValueError("L'identifiant du backend est requis.")
            if self._get(bid):
                raise ValueError(f"Le backend « {bid} » existe déjà.")
            prov = get_provider(backend.get("provider"))
            if prov is None:
                raise ValueError(f"Provider inconnu : {backend.get('provider')}")
            entry = {"id": bid, "provider": prov["id"], "model": str(backend.get("model") or "").strip()}
            if prov["base_url"] is not None and backend.get("base_url"):
                entry["base_url"] = str(backend["base_url"]).strip()
            if prov["base_url"] == "required" and not entry.get("base_url"):
                raise ValueError("Ce provider exige une Base URL.")
            self._data["backends"].append(entry)
            if self._data["active"] is None:
                self._data["active"] = bid
            self._save()
            return self._public(entry)

    def update_model(self, backend_id: str, model: str) -> dict:
        with self._lock:
            b = self._get(backend_id)
            if b is None:
                raise ValueError("Backend inconnu.")
            b["model"] = str(model).strip()
            self._save()
            return self._public(b)

    def delete(self, backend_id: str):
        with self._lock:
            self._data["backends"] = [b for b in self._data["backends"] if b["id"] != backend_id]
            self._data["secrets"].pop(backend_id, None)
            if self._data["active"] == backend_id:
                self._data["active"] = self._data["backends"][0]["id"] if self._data["backends"] else None
            self._save()

    def set_secret(self, backend_id: str, key: str):
        with self._lock:
            if self._get(backend_id) is None:
                raise ValueError("Backend inconnu.")
            self._data["secrets"][backend_id] = str(key)
            self._save()

    def delete_secret(self, backend_id: str):
        with self._lock:
            self._data["secrets"].pop(backend_id, None)
            self._save()

    def set_active(self, backend_id: str):
        with self._lock:
            if self._get(backend_id) is None:
                raise ValueError("Backend inconnu.")
            self._data["active"] = backend_id
            self._save()

    # ── resolution (used by the agent at call time) ─────────────────────
    def resolve(self, backend_id: str = None):
        """``{api_base, key, model, provider, id}`` for a backend (default: the
        active one), or ``None`` if there is none / the endpoint is unresolved.
        ``key`` may be ``None`` when neither a stored secret nor an env var exists."""
        with self._lock:
            bid = backend_id or self._data["active"]
            b = self._get(bid)
            if b is None:
                return None
            api_base = resolve_endpoint(b["provider"], b.get("base_url"))
            if not api_base:
                return None
            key = self._data["secrets"].get(bid)
            if not key:
                prov = get_provider(b["provider"])
                if prov and prov["env_key"]:
                    key = env_loader.get(prov["env_key"])
            return {"api_base": api_base, "key": key, "model": b["model"],
                    "provider": b["provider"], "id": bid}


# Process-wide store.
STORE = AiStore()
