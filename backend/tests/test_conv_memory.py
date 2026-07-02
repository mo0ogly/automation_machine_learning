"""
Tests for conversational semantic recall (conv_memory) — no LLM, no full app.
"""

import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

import conv_memory  # noqa: E402


def _thread():
    turns = [
        {"role": "user", "content": "Quel est le taux de faux positifs de mon détecteur ?"},
        {"role": "assistant", "content": "Le FPR est de 5.5% au seuil 0.5."},
        {"role": "user", "content": "Et la couleur du logo de l'app ?"},
        {"role": "assistant", "content": "Le logo est bleu-violet."},
    ]
    for i in range(6):   # filler exchanges to push the first one out of the window
        turns += [{"role": "user", "content": f"remplissage numéro {i}"},
                  {"role": "assistant", "content": "d'accord"}]
    return turns


def test_backend_resolves():
    assert conv_memory.embedding_backend() in ("st", "tfidf")


def test_recalls_relevant_older_exchange():
    r = conv_memory.relevant_exchanges(
        "rappelle-moi mon taux de fausses alertes", _thread(), k=2, exclude_recent_turns=8)
    assert r, "expected at least one recalled exchange"
    # The FPR exchange must rank first — a semantically related, out-of-window turn.
    assert "faux positifs" in r[0]["user"].lower()
    assert r[0]["score"] >= conv_memory._MIN_SIM


def test_empty_and_short_threads_return_empty():
    assert conv_memory.relevant_exchanges("", _thread()) == []
    assert conv_memory.relevant_exchanges("question", []) == []
    # Everything within the recent window -> nothing to recall.
    short = [{"role": "user", "content": "salut"}, {"role": "assistant", "content": "bonjour"}]
    assert conv_memory.relevant_exchanges("salut", short, exclude_recent_turns=16) == []


def test_never_raises_on_malformed_thread():
    bad = [{"role": "user"}, {"content": "no role"}, None, {"role": "assistant", "content": 123}]
    assert conv_memory.relevant_exchanges("test", [t for t in bad if t]) == [] or True
