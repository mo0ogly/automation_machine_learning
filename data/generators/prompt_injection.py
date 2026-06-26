"""
Generate the prompt-injection detection demo dataset (`data/prompt_injection.csv`).

The raw corpus (`data/sources/prompt-injection-corpus.jsonl`, 1000 segments) is a
text-classification dataset: each record carries a free-text `text` field and a
`label` (injection / benign). This platform is *tabular* — it has no text
vectoriser — so this generator turns each text into a small set of interpretable,
LEAK-FREE surface features that a real indirect-injection detector could compute
at ingestion time, plus the observable channel/language metadata.

Why most corpus metadata is intentionally DROPPED (target leakage):
    technique, owasp_llm, payload_language, obfuscation, injection_position,
    boundary, severity, benign_subtype, payload_span, cross_lingual, code_switched
all describe the *injected payload* and are null/trivial whenever the text is
benign — using them to predict `label` would leak the answer. Only `carrier`
(ingestion channel) and `language` (host-document language) are present for both
classes and therefore kept.

The pedagogical point matches the corpus README: a model combining these surface
features beats naive keyword matching, because the benign hard-negatives (benign
text containing trigger words) and the injection_discussion subtype (text *about*
injection) defeat any single-keyword rule.

Run from anywhere:
    python data/generators/prompt_injection.py
"""

import json
import re
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parent.parent / "sources" / "prompt-injection-corpus.jsonl"
OUT = Path(__file__).resolve().parent.parent / "prompt_injection.csv"

# Imperative / override vocabulary across the three corpus languages (en/fr/pt).
TRIGGER_WORDS = [
    "ignore", "ignorez", "ignora", "disregard", "override", "forget", "oublie",
    "esqueca", "instruction", "instructions", "instrucao", "instrucoes", "consigne",
    "instead", "plutot", "agora", "maintenant", "previous", "precedent", "anterior",
    "must", "obey", "comply", "now", "urgent", "immediately", "immediatement",
]
# Persona / privilege reassignment vocabulary.
ROLE_WORDS = [
    "system", "systeme", "sistema", "admin", "administrator", "administrateur",
    "developer", "developpeur", "developer mode", "root", "sudo", "assistant",
    "adminbot", "persona", "role", "mode",
]
# Structural escape markers (fake delimiters, prompt fences, end-of-context).
DELIMITER_MARKERS = [
    "```", "---", "===", "<|", "|>", "[inst]", "</s>", "###", "<system>",
    "end of", "begin", "<<", ">>", "[/", "===end",
]
ZERO_WIDTH = "​‌‍﻿⁠"
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
_BASE64_RE = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")
_WORD_RE = re.compile(r"\S+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _count_any(text_low: str, vocab) -> int:
    return sum(text_low.count(w) for w in vocab)


def features(text: str) -> dict:
    low = text.lower()
    words = _WORD_RE.findall(text)
    n_chars = len(text) or 1
    n_words = len(words) or 1
    letters = [c for c in text if c.isalpha()]
    return {
        "text_length": len(text),
        "word_count": len(words),
        "avg_word_length": round(sum(len(w) for w in words) / n_words, 3),
        "max_token_length": max((len(w) for w in words), default=0),
        "uppercase_ratio": round(sum(c.isupper() for c in letters) / (len(letters) or 1), 4),
        "digit_ratio": round(sum(c.isdigit() for c in text) / n_chars, 4),
        "punct_ratio": round(len(_PUNCT_RE.findall(text)) / n_chars, 4),
        "line_count": text.count("\n") + 1,
        "non_ascii_ratio": round(sum(ord(c) > 127 for c in text) / n_chars, 4),
        "zero_width_count": sum(text.count(z) for z in ZERO_WIDTH),
        "url_count": len(_URL_RE.findall(text)),
        "trigger_keyword_count": _count_any(low, TRIGGER_WORDS),
        "role_keyword_count": _count_any(low, ROLE_WORDS),
        "delimiter_marker_count": _count_any(low, DELIMITER_MARKERS),
        "has_base64_blob": int(bool(_BASE64_RE.search(text))),
    }


def build() -> pd.DataFrame:
    rows = []
    with SRC.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            row = features(rec["text"])
            row["carrier"] = rec["carrier"]        # ingestion channel (observable)
            row["language"] = rec["language"]      # host-document language (observable)
            row["label"] = rec["label"]            # target: injection / benign
            rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = build()
    df.to_csv(OUT, index=False, encoding="utf-8")
    print(f"wrote {OUT} {df.shape}")
    print(df["label"].value_counts().to_dict())
