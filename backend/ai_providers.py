"""
ai_providers.py — catalog of LLM providers the agent can talk to.

Every provider here is **OpenAI-compatible** (POST ``{api_base}/chat/completions``
with a Bearer key), so a single client serves them all. The catalog is the single
source of truth: the settings UI builds its dropdowns from ``GET /api/ai/providers``,
so adding a provider here surfaces in the UI with **no frontend change**.

``base_url`` modes (mirrors the recette_IA_agents panel):
* ``None``     — provider has a fixed host (``api_base`` below).
* ``"required"`` — the operator must supply the endpoint (Ollama / LiteLLM / vLLM).
* ``"optional"`` — fixed host, but overridable.
"""

import env_loader

PROVIDERS = [
    {
        "id": "groq", "label": "Groq",
        "env_key": "GROQ_API_KEY",
        "api_base": "https://api.groq.com/openai/v1",
        "base_url": None,
        "default_model": "openai/gpt-oss-120b",
        "models": [
            "openai/gpt-oss-120b", "openai/gpt-oss-20b",
            "meta-llama/llama-4-scout-17b-16e-instruct", "qwen/qwen3-32b",
            "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
        ],
    },
    {
        "id": "openai", "label": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "api_base": "https://api.openai.com/v1",
        "base_url": None,
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o", "gpt-4o-mini", "o4-mini"],
    },
    {
        "id": "mistral", "label": "Mistral",
        "env_key": "MISTRAL_API_KEY",
        "api_base": "https://api.mistral.ai/v1",
        "base_url": None,
        "default_model": "mistral-small-latest",
        "models": ["mistral-large-latest", "mistral-small-latest"],
    },
    {
        "id": "deepseek", "label": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "api_base": "https://api.deepseek.com/v1",
        "base_url": None,
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    {
        # Zhipu AI / z.ai — GLM family. OpenAI-compatible endpoint
        # (POST {api_base}/chat/completions, Bearer key).
        # base URL: https://api.z.ai/api/paas/v4  (docs.z.ai/api-reference/introduction)
        "id": "zai", "label": "Z.AI (GLM)",
        "env_key": "ZAI_API_KEY",
        "api_base": "https://api.z.ai/api/paas/v4",
        "base_url": None,
        "default_model": "glm-5.2",
        "models": [
            "glm-5.2", "glm-5.1", "glm-5", "glm-4.7", "glm-4.6", "glm-4.5",
        ],
    },
    {
        # Local / self-hosted gateways: Ollama, LiteLLM proxy, vLLM. The endpoint
        # is supplied per backend; a key is optional (most local servers need none).
        "id": "openai_compat", "label": "OpenAI-compatible (Ollama / LiteLLM / vLLM)",
        "env_key": None,
        "api_base": None,
        "base_url": "required",
        "default_model": "llama3.1",
        "models": [],  # free-text model id (depends on what the gateway serves)
    },
]
_BY_ID = {p["id"]: p for p in PROVIDERS}


def get_provider(provider_id: str):
    return _BY_ID.get(provider_id)


def public_catalog() -> list:
    """``AiProviderInfo[]`` for the UI — what the form needs to build its dropdowns,
    plus ``env_present`` so the UI can show which providers work out of the box."""
    out = []
    for p in PROVIDERS:
        out.append({
            "id": p["id"], "label": p["label"],
            "env_key": p["env_key"],
            "env_present": bool(p["env_key"] and env_loader.get(p["env_key"])),
            "default_model": p["default_model"],
            "models": list(p["models"]),
            "base_url": p["base_url"],
        })
    return out


def resolve_endpoint(provider_id: str, base_url: str = None):
    """The ``api_base`` to call: the provider's fixed host, or the backend's
    ``base_url`` for ``openai_compat``. Returns ``None`` when unresolved."""
    p = _BY_ID.get(provider_id)
    if p is None:
        return None
    if p["api_base"]:
        return p["api_base"]
    return (base_url or "").rstrip("/") or None
