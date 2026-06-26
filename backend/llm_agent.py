"""
llm_agent.py — Per-stage refinement agent (Groq).

The agent is what makes the loop *agentic*: at each stage it reads the real,
deterministically-computed diagnostics and proposes a refined configuration
(the "affinage") with a rationale, in French, as strict JSON.

Design choices:
- The LLM never invents numbers — it is handed the actual diagnostics and is
  instructed to ground every claim in them.
- Its ``suggested_config`` is sanitised against the stage's own config schema
  before it can reach ``run`` (no invalid keys / out-of-range values).
- If Groq is unreachable (no key, network/API error), a clearly-labelled
  deterministic heuristic keeps the loop usable. The ``source`` field always
  states which path produced the recommendation.
"""

import json

import httpx

import env_loader
import agent_prompts

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = env_loader.get("GROQ_MODEL", "openai/gpt-oss-120b")

# Curated chat models selectable from the UI (id, friendly label, indicative Groq
# price input/output per 1M tokens). The active model is switchable at runtime via
# set_model(); it resets to GROQ_MODEL on restart.
AVAILABLE_MODELS = [
    {"id": "openai/gpt-oss-120b", "label": "GPT OSS 120B", "price": "$0.15 / $0.60"},
    {"id": "openai/gpt-oss-20b", "label": "GPT OSS 20B", "price": "$0.075 / $0.30"},
    {"id": "meta-llama/llama-4-scout-17b-16e-instruct", "label": "Llama 4 Scout 17B", "price": "$0.11 / $0.34"},
    {"id": "qwen/qwen3-32b", "label": "Qwen3 32B", "price": "$0.29 / $0.59"},
    {"id": "qwen/qwen3.6-27b", "label": "Qwen 3.6 27B", "price": "$0.60 / $3.00"},
    {"id": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B", "price": "$0.59 / $0.79"},
    {"id": "llama-3.1-8b-instant", "label": "Llama 3.1 8B", "price": "$0.05 / $0.08"},
]
_VALID_IDS = {m["id"] for m in AVAILABLE_MODELS}
_active_model = DEFAULT_MODEL if DEFAULT_MODEL in _VALID_IDS else "openai/gpt-oss-120b"


def get_active_model() -> str:
    return _active_model


def set_model(model_id: str) -> bool:
    """Switch the active agent model (must be one of AVAILABLE_MODELS). Returns success."""
    global _active_model
    if model_id not in _VALID_IDS:
        return False
    _active_model = model_id
    return True


def available_models() -> list:
    return AVAILABLE_MODELS

# The agent's prompt (system instructions + per-stage few-shot examples) lives in
# agent_prompts.py — see build_messages().


def agent_status() -> dict:
    """Agent configuration for the UI: active model + the selectable list."""
    key = env_loader.get("GROQ_API_KEY")
    return {
        "configured": bool(key),
        "model": get_active_model(),
        "provider": "groq",
        "available_models": AVAILABLE_MODELS,
    }


def recommend(stage_meta: dict, problem_type: str, diagnostics: dict,
              schema: list, current_config: dict, journal: str = "") -> dict:
    """Produce a refinement recommendation for one stage."""
    key = env_loader.get("GROQ_API_KEY")
    if not key:
        rec = _heuristic(stage_meta["stage_id"], diagnostics, current_config, problem_type)
        rec.update({"source": "heuristic-fallback", "available": False,
                    "reason": "GROQ_API_KEY absente — recommandation heuristique déterministe.",
                    "model": None})
        rec["suggested_config"] = sanitize_config(schema, rec.get("suggested_config", {}))
        return rec

    messages = agent_prompts.build_messages(
        stage_meta, problem_type, _compact_schema(schema), current_config, diagnostics, journal)
    try:
        content = _call_groq(key, messages)
        parsed = json.loads(_extract_json(content))
        suggested = sanitize_config(schema, parsed.get("suggested_config", {}))
        return {
            "source": "llm",
            "available": True,
            "model": get_active_model(),
            "summary": str(parsed.get("summary", "")).strip(),
            "rationale": [str(r) for r in parsed.get("rationale", [])][:6],
            "suggested_config": suggested,
            "risk": str(parsed.get("risk", "")).strip(),
            "confidence": _clamp_float(parsed.get("confidence", 0.5), 0.0, 1.0),
        }
    except Exception as e:  # network, JSON, API — degrade gracefully but honestly.
        rec = _heuristic(stage_meta["stage_id"], diagnostics, current_config, problem_type)
        rec.update({"source": "heuristic-fallback", "available": False,
                    "reason": f"Agent Groq indisponible ({type(e).__name__}) — repli heuristique.",
                    "model": get_active_model()})
        rec["suggested_config"] = sanitize_config(schema, rec.get("suggested_config", {}))
        return rec


def interpret(stage_title: str, problem_type: str, payload: dict, journal: str = "") -> dict:
    """Generate a natural-language interpretation/conclusion of a stage's results."""
    key = env_loader.get("GROQ_API_KEY")
    if not key:
        return {"source": "none", "available": False, "model": None, "verdict": "", "confidence": 0.0,
                "interpretation": ["Interprétation IA indisponible (GROQ_API_KEY absente)."]}
    try:
        content = _call_groq(key, agent_prompts.build_interpret_messages(stage_title, problem_type, payload, journal))
        p = json.loads(_extract_json(content))
        return {"source": "llm", "available": True, "model": get_active_model(),
                "interpretation": [str(x) for x in p.get("interpretation", [])][:6],
                "verdict": str(p.get("verdict", "")).strip(),
                "confidence": _clamp_float(p.get("confidence", 0.5), 0.0, 1.0)}
    except Exception as e:
        return {"source": "error", "available": False, "model": get_active_model(), "verdict": "",
                "confidence": 0.0, "interpretation": [f"Interprétation indisponible ({type(e).__name__})."]}


def assist(stage_title: str, problem_type: str, topic: str, focus: dict,
           journal: str = "", level: str = "novice",
           schema: list = None, current_config: dict = None) -> dict:
    """Explain a specific sub-step element to the analyst, and (when relevant)
    propose an APPLICABLE config change so the advice is one-click actionable."""
    key = env_loader.get("GROQ_API_KEY")
    if not key:
        return _assist_heuristic(topic, focus, level)
    try:
        compact = _compact_schema(schema) if schema else None
        content = _call_groq(key, agent_prompts.build_assist_messages(
            stage_title, problem_type, topic, focus, journal, level, compact, current_config))
        p = json.loads(_extract_json(content))
        suggested = sanitize_config(schema, p.get("suggested_config", {})) if schema else {}
        return {"source": "llm", "available": True, "model": get_active_model(),
                "explanation": [str(x) for x in p.get("explanation", [])][:6],
                "takeaway": str(p.get("takeaway", "")).strip(),
                "suggested_config": suggested,
                "confidence": _clamp_float(p.get("confidence", 0.5), 0.0, 1.0)}
    except Exception as e:
        out = _assist_heuristic(topic, focus, level)
        out["reason"] = f"Agent Groq indisponible ({type(e).__name__}) — explication déterministe."
        return out


def _assist_heuristic(topic: str, focus: dict, level: str) -> dict:
    """Deterministic fallback: surface the element's key data points, no invention."""
    points = []
    data = focus.get(topic, focus) if isinstance(focus, dict) else focus
    if isinstance(data, dict):
        for k, v in list(data.items())[:4]:
            points.append(f"{k} : {v}")
    elif isinstance(data, list):
        points.append(f"{len(data)} élément(s).")
        for row in data[:3]:
            points.append(str(row))
    else:
        points.append(str(data))
    return {"source": "heuristic-fallback", "available": False, "model": None,
            "explanation": points or ["Aucune donnée exploitable pour cet élément."],
            "takeaway": "Lecture brute des données (assistant IA indisponible).",
            "suggested_config": {}, "confidence": 0.0}


def _call_groq(key: str, messages: list) -> str:
    model = get_active_model()
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }
    # Reasoning models: keep reasoning minimal, else it can exhaust the token budget
    # and Groq's JSON validation fails (observed on qwen3.6-27b).
    if "gpt-oss" in model:
        payload["reasoning_effort"] = "low"
    elif "qwen" in model:
        payload["reasoning_effort"] = "none"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = httpx.post(GROQ_URL, json=payload, headers=headers, timeout=40.0)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _extract_json(content: str) -> str:
    """Pull the JSON object out of a reply, tolerant to reasoning tags / code fences."""
    content = (content or "").strip()
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[-1].strip()
    if content.startswith("```"):
        content = content.strip("`").strip()
        if content[:4].lower() == "json":
            content = content[4:].strip()
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end != -1 and end > start:
        content = content[start:end + 1]
    return content


# ── config sanitisation ───────────────────────────────────────────────────
def _compact_schema(schema: list) -> list:
    out = []
    for c in schema:
        item = {"name": c["name"], "type": c["type"], "default": c.get("default")}
        if c["type"] == "select":
            item["allowed"] = [o["value"] for o in c.get("options", [])]
        if c["type"] in ("range", "number"):
            item["min"], item["max"] = c.get("min"), c.get("max")
        if c["type"] == "column_table":
            # The value is a list of column names to drop; expose the valid names.
            item["columns"] = [r.get("column") for r in c.get("columns", [])]
        out.append(item)
    return out


def sanitize_config(schema: list, proposed: dict) -> dict:
    """Keep only valid keys/values from a proposed config (defence against the LLM)."""
    if not isinstance(proposed, dict):
        return {}
    by_name = {c["name"]: c for c in schema}
    clean = {}
    for name, val in proposed.items():
        ctrl = by_name.get(name)
        if ctrl is None:
            continue
        t = ctrl["type"]
        if t == "select":
            allowed = [o["value"] for o in ctrl.get("options", [])]
            if val in allowed:
                clean[name] = val
        elif t == "toggle":
            clean[name] = bool(val)
        elif t == "column_table":
            # Value is a list of column names to drop — keep only names that exist.
            valid = {r.get("column") for r in ctrl.get("columns", [])}
            if isinstance(val, list):
                clean[name] = [str(x) for x in val if x in valid]
        elif t in ("range", "number"):
            num = _coerce_number(val)
            if num is None:
                continue
            lo, hi = ctrl.get("min"), ctrl.get("max")
            if lo is not None:
                num = max(num, lo)
            if hi is not None:
                num = min(num, hi)
            clean[name] = num
    return clean


def _coerce_number(v):
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def _clamp_float(v, lo, hi):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.5


# ── deterministic heuristic fallback ──────────────────────────────────────
def _heuristic(stage_id, d, cfg, problem_type) -> dict:
    cfg = cfg or {}
    rationale, suggested = [], {}

    if stage_id == "clean":
        ov = d.get("overview", {})
        if ov.get("missing_pct", 0) > 0:
            suggested.update({"impute_num": "median", "impute_cat": "constant"})
            rationale.append(f"{ov['missing_pct']}% de cellules manquantes : imputer (médiane / 'None').")
        if ov.get("duplicated_rows", 0) > 0:
            suggested["drop_duplicates"] = True
            rationale.append(f"{ov['duplicated_rows']} doublon(s) : à supprimer.")
        if any(r.get("type") == "Catégorielle ordinale" for r in d.get("typologie", [])):
            suggested["normalize_ordinals"] = True
            rationale.append("Variables ordinales présentes : normaliser sur l'échelle ordonnée (Po=1…Ex=5).")
        if len(d.get("outliers_iqr", [])) >= 3:
            suggested.update({"outlier_method": "iqr_clip", "outlier_k": 1.5})
            rationale.append("Plusieurs variables présentent des valeurs aberrantes (IQR) : borner.")
        summary = "Imputer les manquants, normaliser les ordinales, et envisager le bornage des aberrants."

    elif stage_id == "transform":
        skew = d.get("skewness", [])
        if skew and skew[0]["abs_skew"] > 1:
            suggested.update({"skew_correction": True, "skew_threshold": 1.0, "skew_method": "yeo-johnson"})
            rationale.append(f"Asymétrie élevée (|skew|={skew[0]['abs_skew']} sur {skew[0]['column']}) : redresser.")
        card = d.get("cardinality", [])
        if card and card[0]["n_unique"] > 12:
            suggested["encoding"] = "ordinal"
            rationale.append(f"Cardinalité élevée ({card[0]['n_unique']}) : ordinal plutôt que One-Hot.")
        else:
            suggested["encoding"] = cfg.get("encoding", "ordinal")
        suggested["scaler"] = "standard"
        rationale.append("StandardScaler pour homogénéiser les échelles.")
        summary = "Redresser les variables asymétriques, encoder le catégoriel, standardiser."

    elif stage_id == "integrate":
        pairs = d.get("high_correlation_pairs", [])
        tcorr = {x["column"]: x.get("abs_corr", 0) for x in d.get("target_correlation", [])}
        drop, seen = [], set()
        for p in pairs:
            a, b = p.get("a"), p.get("b")
            if a in seen or b in seen:
                continue
            loser = b if tcorr.get(a, 0) >= tcorr.get(b, 0) else a
            seen.add(loser)
            drop.append(loser)
        if drop:
            suggested["dropped_features"] = drop
            rationale.append(f"{len(drop)} variable(s) redondante(s) à retirer (on garde la plus liée à la cible).")
        else:
            suggested["dropped_features"] = []
            rationale.append("Aucune redondance forte : conserver toutes les variables.")
        suggested["pca"] = False
        summary = "Retirer les variables redondantes ; l'expert ajuste la sélection finale."

    elif stage_id == "separate":
        if problem_type == "classification":
            suggested["stratify"] = True
            rationale.append("Classification : stratifier pour préserver l'équilibre des classes.")
        suggested["test_size"] = cfg.get("test_size", 0.25)
        if d.get("leakage_candidates"):
            rationale.append("Fuite possible détectée : vérifier les variables quasi-identiques à la cible.")
        summary = "Découpage train/test stratifié et contrôle de fuite."

    elif stage_id == "model":
        suggested.update({"algorithm": "RandomForest", "n_estimators": 100})
        rationale.append("Random Forest : robuste par défaut sur données tabulaires.")
        summary = "Démarrer avec un Random Forest, puis ajuster les hyperparamètres selon l'évaluation."

    else:  # evaluate
        summary = "Aucun paramètre à régler — lire les métriques et revenir affiner une étape amont si besoin."
        rationale.append("Comparer R²/RMSE (régression) ou Accuracy/F1 (classification) au besoin métier.")

    return {"summary": summary, "rationale": rationale, "suggested_config": suggested,
            "risk": "Recommandation déterministe (règles data-science), à valider par l'expert.",
            "confidence": 0.6}
