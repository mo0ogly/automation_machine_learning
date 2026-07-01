"""
inference_params.py — validation and clamping of LLM sampling parameters.

Sampling parameters (temperature, max_tokens, top_p, penalties) reach the app
from two untrusted-ish places: a backend's persisted defaults (edited in the
"Backends IA" panel) and per-request overrides (the AI cockpit / chat). Both go
through :func:`sanitize` so a bad value can never reach the provider payload —
unknown keys are dropped, numbers are coerced and clamped to each provider's
accepted range.

Field defaults mirror the values the agent used implicitly before the cockpit
existed (temperature 0.2, max_tokens 4096), so behaviour is unchanged when no
one touches the settings.
"""

# name -> (min, max, default, is_int). Ranges follow the OpenAI-compatible wire
# format shared by every provider in ai_providers.py.
_SPEC = {
    "temperature": (0.0, 2.0, 0.2, False),
    "top_p": (0.0, 1.0, 1.0, False),
    "max_tokens": (1, 32000, 4096, True),
    "presence_penalty": (-2.0, 2.0, 0.0, False),
    "frequency_penalty": (-2.0, 2.0, 0.0, False),
}

# The fields the UI exposes, in display order (source of truth for the panel via
# GET /api/ai/param-spec).
FIELDS = [
    {"name": "temperature", "min": 0.0, "max": 2.0, "step": 0.05, "default": 0.2,
     "label": "Température", "help": "Créativité : 0 = déterministe, 2 = très aléatoire."},
    {"name": "top_p", "min": 0.0, "max": 1.0, "step": 0.05, "default": 1.0,
     "label": "Top-p", "help": "Noyau de probabilité : restreint le vocabulaire échantillonné."},
    {"name": "max_tokens", "min": 1, "max": 32000, "step": 1, "default": 4096,
     "label": "Tokens max", "help": "Longueur maximale de la réponse générée."},
    {"name": "presence_penalty", "min": -2.0, "max": 2.0, "step": 0.1, "default": 0.0,
     "label": "Pénalité de présence", "help": "Positif = encourage de nouveaux sujets."},
    {"name": "frequency_penalty", "min": -2.0, "max": 2.0, "step": 0.1, "default": 0.0,
     "label": "Pénalité de fréquence", "help": "Positif = réduit les répétitions."},
]


def _coerce(value, is_int: bool):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return int(round(f)) if is_int else f


def sanitize(params) -> dict:
    """Keep only known keys, coerce to number, and clamp to the accepted range.

    Returns a dict with a subset of :data:`_SPEC` keys — never raises, so a
    malformed payload simply yields ``{}`` (the caller then falls back to
    defaults). Unknown keys are silently dropped (defence against the client).
    """
    if not isinstance(params, dict):
        return {}
    clean = {}
    for name, (lo, hi, _default, is_int) in _SPEC.items():
        if name not in params or params[name] is None:
            continue
        num = _coerce(params[name], is_int)
        if num is None:
            continue
        clean[name] = max(lo, min(hi, num))
    return clean


def resolve(backend_defaults=None, overrides=None) -> dict:
    """Effective sampling parameters for a call: field defaults, overlaid by the
    backend's persisted defaults, overlaid by per-request overrides. Every layer
    is sanitised, so the result is always a complete, valid parameter set."""
    effective = {name: spec[2] for name, spec in _SPEC.items()}
    effective.update(sanitize(backend_defaults))
    effective.update(sanitize(overrides))
    return effective
