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

# Catalog ported from recette_IA_agents (recette/llm/openai_wire.py): the full set
# of OpenAI-wire vendors. ``api_base`` is the URL up to (not including)
# ``/chat/completions``; for bare-host vendors that is host + ``/v1``, for vendors
# whose endpoint already carries a version it is the versioned URL verbatim. Env
# keys mirror recette's .env.example exactly. Models lists are curated only where
# already validated; new vendors use free-text model entry (``models: []``).
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
        "id": "xai", "label": "xAI (Grok)",
        "env_key": "XAI_API_KEY",
        "api_base": "https://api.x.ai/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "openrouter", "label": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "api_base": "https://openrouter.ai/api/v1",
        "base_url": None,
        "default_model": "",
        "models": [],  # aggregator: type the full model slug (e.g. anthropic/claude-3.7-sonnet)
    },
    {
        "id": "together", "label": "Together AI",
        "env_key": "TOGETHER_API_KEY",
        "api_base": "https://api.together.xyz/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "fireworks", "label": "Fireworks AI",
        "env_key": "FIREWORKS_API_KEY",
        "api_base": "https://api.fireworks.ai/inference/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "moonshot", "label": "Moonshot (Kimi)",
        "env_key": "KIMI_API_KEY",
        "api_base": "https://api.moonshot.ai/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "zai", "label": "Z.AI (GLM)",
        "env_key": "GLM_API_KEY",
        "api_base": "https://api.z.ai/api/paas/v4",
        "base_url": None,
        "default_model": "glm-5.2",
        "models": [
            "glm-5.2", "glm-5.1", "glm-5", "glm-4.7", "glm-4.6", "glm-4.5",
        ],
    },
    {
        "id": "dashscope", "label": "Alibaba DashScope (Qwen)",
        "env_key": "DASHSCOPE_API_KEY",
        "api_base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "nvidia", "label": "Nvidia NIM",
        "env_key": "NVIDIA_API_KEY",
        "api_base": "https://integrate.api.nvidia.com/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "nous", "label": "Nous Research",
        "env_key": "NOUS_API_KEY",
        "api_base": "https://inference.nousresearch.com/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "ollama_cloud", "label": "Ollama Cloud",
        "env_key": "OLLAMA_API_KEY",
        "api_base": "https://ollama.com/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "novita", "label": "Novita AI",
        "env_key": "NOVITA_API_KEY",
        "api_base": "https://api.novita.ai/openai/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "stepfun", "label": "StepFun",
        "env_key": "STEPFUN_API_KEY",
        "api_base": "https://api.stepfun.ai/step_plan/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "arcee", "label": "Arcee AI",
        "env_key": "ARCEEAI_API_KEY",
        "api_base": "https://api.arcee.ai/api/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "xiaomi", "label": "Xiaomi MiMo",
        "env_key": "XIAOMI_API_KEY",
        "api_base": "https://api.xiaomimimo.com/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "gmi", "label": "GMI Serving",
        "env_key": "GMI_API_KEY",
        "api_base": "https://api.gmi-serving.com/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "huggingface", "label": "Hugging Face Router",
        "env_key": "HF_TOKEN",
        "api_base": "https://router.huggingface.co/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "opencode_zen", "label": "OpenCode Zen",
        "env_key": "OPENCODE_ZEN_API_KEY",
        "api_base": "https://opencode.ai/zen/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "kilocode", "label": "Kilo Code",
        "env_key": "KILOCODE_API_KEY",
        "api_base": "https://api.kilo.ai/api/gateway",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "alibaba_coding", "label": "Alibaba Coding Plan (Qwen)",
        "env_key": "ALIBABA_CODING_PLAN_API_KEY",
        "api_base": "https://coding-intl.dashscope.aliyuncs.com/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "qwen", "label": "Qwen Portal",
        "env_key": "QWEN_API_KEY",
        "api_base": "https://portal.qwen.ai/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
    },
    {
        "id": "cerebras", "label": "Cerebras",
        "env_key": "CEREBRAS_API_KEY",
        "api_base": "https://api.cerebras.ai/v1",
        "base_url": None,
        "default_model": "",
        "models": [],
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
