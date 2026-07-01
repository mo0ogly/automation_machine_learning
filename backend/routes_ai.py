"""
routes_ai.py — multi-provider AI-backend management.

Mirrors the recette_IA_agents pattern: a server-side provider **catalog** (single
source of truth for the UI dropdowns) + CRUD over configured **backends**, each
pinning a provider + model (+ base_url for openai_compat). Keys are write-only
(set/remove only; never returned — the list exposes ``key_configured``). A Test
probe sends a one-word prompt and returns latency + reply.
"""

import time

import httpx
from fastapi import APIRouter, Body, HTTPException

import ai_providers
import ai_store
import inference_params

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/providers")
def list_providers():
    """The provider catalog (AiProviderInfo[]). Adding a provider server-side
    surfaces here with no frontend change."""
    return {"providers": ai_providers.public_catalog()}


@router.get("/param-spec")
def param_spec():
    """Editable sampling parameters (name, range, step, default, label, help) —
    single source of truth for the inference-settings controls in the UI."""
    return {"fields": inference_params.FIELDS}


@router.put("/backends/{backend_id}/params")
def set_params(backend_id: str, body: dict = Body(default={})):
    """Set a backend's default sampling parameters. Values are sanitised/clamped;
    ``{}`` clears them (the backend then uses the global defaults)."""
    try:
        return ai_store.STORE.update_params(backend_id, body.get("params") or {})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/backends")
def list_backends():
    return {"backends": ai_store.STORE.list_backends(), "active": ai_store.STORE.active_id()}


@router.post("/backends")
def create_backend(body: dict = Body(default={})):
    try:
        return ai_store.STORE.create({
            "id": body.get("id"), "provider": body.get("provider"),
            "model": body.get("model"), "base_url": body.get("base_url"),
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/backends/{backend_id}")
def delete_backend(backend_id: str):
    ai_store.STORE.delete(backend_id)
    return {"deleted": backend_id, "active": ai_store.STORE.active_id()}


@router.post("/backends/{backend_id}/secret")
def set_secret(backend_id: str, body: dict = Body(default={})):
    """Store an API key for a backend (write-only — never read back)."""
    key = str(body.get("key") or "")
    if not key:
        raise HTTPException(status_code=400, detail="Clé vide.")
    try:
        ai_store.STORE.set_secret(backend_id, key)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"id": backend_id, "key_configured": True}


@router.delete("/backends/{backend_id}/secret")
def delete_secret(backend_id: str):
    ai_store.STORE.delete_secret(backend_id)
    return {"id": backend_id, "key_configured": False}


@router.post("/active")
def set_active(body: dict = Body(default={})):
    try:
        ai_store.STORE.set_active(str(body.get("id") or ""))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"active": ai_store.STORE.active_id()}


@router.post("/backends/{backend_id}/test")
def test_backend(backend_id: str, body: dict = Body(default={})):
    """Connectivity/ask probe: send a prompt (default a one-word ping) and return
    latency + the model's reply (or the error). Uses the stored key or the
    provider env var — key material never reaches the client."""
    r = ai_store.STORE.resolve(backend_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Backend inconnu.")
    if not r.get("key"):
        return {"ok": False, "latency_ms": 0,
                "error": "Aucune clé (ni stockée ni variable d'environnement du provider)."}
    prompt = (str(body.get("prompt") or "").strip() or "ping (réponds en un seul mot)")[:2000]
    model = r["model"]
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "temperature": 0, "max_tokens": 64}
    if "gpt-oss" in model:
        payload["reasoning_effort"] = "low"
    elif "qwen" in model:
        payload["reasoning_effort"] = "none"
    headers = {"Authorization": f"Bearer {r['key']}", "Content-Type": "application/json"}
    url = r["api_base"].rstrip("/") + "/chat/completions"
    t0 = time.monotonic()
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        latency = int((time.monotonic() - t0) * 1000)
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
        return {"ok": True, "latency_ms": latency, "text": (text or "").strip()[:400]}
    except Exception as e:
        latency = int((time.monotonic() - t0) * 1000)
        return {"ok": False, "latency_ms": latency, "error": f"{type(e).__name__}: {str(e)[:200]}"}
