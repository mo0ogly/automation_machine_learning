"""
conv_memory.py — conversational retrieval for the AI cockpit (semantic recall).

The chat replays only the last N turns verbatim; beyond that window the copilot
"forgets". This module adds long-term memory: it embeds past exchanges and, for
each new question, retrieves the most RELEVANT earlier exchanges (cosine
similarity) to inject alongside the recent turns — so the assistant recalls the
right past even when it scrolled out of the window.

Embedder (lazy, local, no API): primary is a sentence-transformers model
(true semantic); if it cannot load (offline first run, missing model), it falls
back to a scikit-learn TF-IDF vectoriser (lexical) already available in the venv.
No ChromaDB — vectors are computed on demand over the (bounded) conversation.
"""

from __future__ import annotations

import os

import numpy as np

import prompt_guard

_ST_MODEL_NAME = "all-MiniLM-L6-v2"
# Calibrated for MiniLM / French: generic sentences share a high baseline cosine,
# so a low cut-off lets topical noise through. Recall must be selective.
_MIN_SIM = 0.45
_MAX_CANDIDATES = 400   # bound the per-turn embedding cost on very long sessions
_model = None           # lazy sentence-transformers singleton
_backend = None         # "st" | "tfidf" — resolved on first use


def _load_embedder():
    """Resolve the embedding backend once: sentence-transformers if it loads,
    else TF-IDF. Never raises — always leaves a usable backend."""
    global _model, _backend
    if _backend is not None:
        return
    # Cache-only: never hit the network (avoids slow HF retries when offline / a
    # cert is missing). Loads instantly from cache if present, else fails fast to
    # the TF-IDF fallback.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_ST_MODEL_NAME)
        _backend = "st"
    except Exception:
        _model = None
        _backend = "tfidf"


def embedding_backend() -> str:
    _load_embedder()
    return _backend


def _embed(texts: list) -> np.ndarray:
    """L2-normalised embedding matrix for ``texts`` (one row per text)."""
    _load_embedder()
    if _backend == "st":
        vecs = np.asarray(_model.encode(texts, normalize_embeddings=True), dtype=float)
        return vecs
    # TF-IDF fallback: fit on this batch (query + candidates), already L2-normalised.
    from sklearn.feature_extraction.text import TfidfVectorizer
    tfidf = TfidfVectorizer().fit_transform(texts)
    return np.asarray(tfidf.todense(), dtype=float)


def _exchanges(thread: list) -> list:
    """Pair each user turn with the following assistant reply. Skips exchanges
    whose reply is a static failure message (``source`` none/error) — those are
    hidden from replay too, so they must not be recalled either. Returns a list
    of ``{"i": last_turn_index, "user": ..., "assistant": ..., "text": ...}``."""
    out = []
    i = 0
    n = len(thread)
    while i < n:
        t = thread[i]
        if t.get("role") == "user":
            user = str(t.get("content") or "")
            assistant, j, src = "", i, None
            if i + 1 < n and thread[i + 1].get("role") == "assistant":
                assistant = str(thread[i + 1].get("content") or "")
                src = thread[i + 1].get("source")
                j = i + 1
            if src not in ("none", "error"):   # do not recall unusable turns
                out.append({"i": j, "user": user, "assistant": assistant,
                            "text": (user + "\n" + assistant).strip()})
            i = j + 1
        else:
            i += 1
    return out


def relevant_exchanges(query: str, thread: list, k: int = 3,
                       exclude_recent_turns: int = 20) -> list:
    """Top-``k`` earlier exchanges most relevant to ``query``.

    Exchanges whose last turn falls in the last ``exclude_recent_turns`` turns are
    skipped — they are already replayed verbatim, so recall targets what scrolled
    out of the window (default matches ``chat_history``'s 20-turn window to avoid
    duplicating what is already in context). Exchanges whose content looks like a
    prompt injection are dropped: recall must not proactively RE-SERVE a payload
    that already aged out of context. Returns ``[{user, assistant, score}]``
    (empty if nothing relevant or the conversation is too short). Never raises."""
    query = str(query or "").strip()
    if not query or not thread:
        return []
    try:
        cutoff = max(0, len(thread) - int(exclude_recent_turns))
        cands = [e for e in _exchanges(thread) if e["i"] < cutoff and e["text"]
                 and not prompt_guard.looks_like_injection(e["user"])
                 and not prompt_guard.looks_like_injection(e["assistant"])]
        cands = cands[-_MAX_CANDIDATES:]   # bound the embedding cost
        if not cands:
            return []
        mat = _embed([query] + [e["text"] for e in cands])
        q, rest = mat[0], mat[1:]
        sims = rest @ q / ((np.linalg.norm(rest, axis=1) * (np.linalg.norm(q) or 1.0)) + 1e-9)
        order = np.argsort(-sims)[:max(1, int(k))]
        return [{"user": cands[i]["user"], "assistant": cands[i]["assistant"],
                 "score": round(float(sims[i]), 3)}
                for i in order if sims[i] >= _MIN_SIM]
    except Exception:
        return []   # memory recall is best-effort, never breaks a chat turn
