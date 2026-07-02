"""
Generate the synthetic spam-detection demo (`data/spam.csv`).

Binary, moderately balanced (~32% spam) tabular dataset of message-derived
features (length, digits, capitalisation, currency/urgency keyword counts, URL
and phone presence). A pedagogical companion to the phishing dataset: same
detection framing, different feature space, more balanced classes. Class-
conditional distributions (spam is shorter-but-louder: more caps, exclamation,
currency and "free/urgent" keywords) make the target learnable, never random.
Deterministic (fixed seed).

Run from anywhere:
    python data/generators/spam_messages.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

N_HAM, N_SPAM = 2050, 950
OUT = Path(__file__).resolve().parent.parent / "spam.csv"

_LANG = ["fr", "en"]


def _ham(rng):
    n = N_HAM
    return pd.DataFrame({
        "char_length": rng.normal(90, 45, n).clip(5, 400).round().astype(int),
        "num_words": rng.normal(17, 8, n).clip(1, 80).round().astype(int),
        "num_digits": rng.poisson(1.2, n).clip(0, 20),
        "uppercase_ratio": rng.beta(1.5, 12, n).round(3),
        "num_exclamation": rng.poisson(0.4, n).clip(0, 10),
        "num_currency": rng.poisson(0.05, n).clip(0, 5),
        "num_free_keywords": rng.poisson(0.08, n).clip(0, 6),
        "num_urgent_keywords": rng.poisson(0.1, n).clip(0, 6),
        "has_url": (rng.random(n) < 0.12).astype(int),
        "has_phone": (rng.random(n) < 0.08).astype(int),
        "avg_word_length": rng.normal(4.6, 0.8, n).clip(2, 9).round(2),
        "language": rng.choice(_LANG, n, p=[0.6, 0.4]),
        "is_spam": 0,
    })


def _spam(rng):
    n = N_SPAM
    return pd.DataFrame({
        "char_length": rng.normal(135, 40, n).clip(20, 500).round().astype(int),
        "num_words": rng.normal(24, 9, n).clip(3, 90).round().astype(int),
        "num_digits": rng.poisson(6.5, n).clip(0, 40),
        "uppercase_ratio": rng.beta(4, 6, n).round(3),
        "num_exclamation": rng.poisson(2.6, n).clip(0, 15),
        "num_currency": rng.poisson(1.7, n).clip(0, 12),
        "num_free_keywords": rng.poisson(1.9, n).clip(0, 12),
        "num_urgent_keywords": rng.poisson(2.2, n).clip(0, 12),
        "has_url": (rng.random(n) < 0.72).astype(int),
        "has_phone": (rng.random(n) < 0.55).astype(int),
        "avg_word_length": rng.normal(5.2, 1.0, n).clip(2, 10).round(2),
        "language": rng.choice(_LANG, n, p=[0.5, 0.5]),
        "is_spam": 1,
    })


def build() -> pd.DataFrame:
    rng = np.random.default_rng(2024)
    df = pd.concat([_ham(rng), _spam(rng)], ignore_index=True)
    return df.sample(frac=1, random_state=11).reset_index(drop=True)


if __name__ == "__main__":
    df = build()
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} {df.shape} | spam rate {df['is_spam'].mean():.1%}")
