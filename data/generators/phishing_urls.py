"""
Generate the synthetic phishing-URL detection demo (`data/phishing.csv`).

Binary, deliberately IMBALANCED (~22% phishing) tabular dataset of URL/hostname
features — the archetypal SOC triage task where a missed phishing URL (false
negative) costs far more than a false alert. Values are drawn from class-
conditional distributions (phishing URLs are longer, richer in digits/hyphens,
younger domains, odd TLDs) so the target is learnable but non-trivial, never a
random label. Fully deterministic (fixed seed) — reproducible byte-for-byte.

Run from anywhere:
    python data/generators/phishing_urls.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

N_LEGIT, N_PHISH = 3100, 900
OUT = Path(__file__).resolve().parent.parent / "phishing.csv"

_LEGIT_TLD = ["com", "org", "net", "fr", "gov", "edu"]
_PHISH_TLD = ["xyz", "top", "tk", "info", "zip", "click", "com", "net"]


def _legit(rng):
    n = N_LEGIT
    return pd.DataFrame({
        "url_length": rng.normal(52, 20, n).clip(12, 200).round().astype(int),
        "num_dots": rng.poisson(1.9, n).clip(1, 8),
        "num_hyphens": rng.poisson(0.6, n).clip(0, 8),
        "num_digits": rng.poisson(1.8, n).clip(0, 25),
        "num_subdomains": rng.poisson(1.1, n).clip(0, 6),
        "num_params": rng.poisson(0.9, n).clip(0, 10),
        "domain_age_days": rng.gamma(4, 300, n).clip(5, 6000).round().astype(int),
        "has_ip": (rng.random(n) < 0.03).astype(int),
        "has_at_symbol": (rng.random(n) < 0.02).astype(int),
        "https": (rng.random(n) < 0.9).astype(int),
        "shortened": (rng.random(n) < 0.07).astype(int),
        "brand_in_subdomain": (rng.random(n) < 0.06).astype(int),
        "host_entropy": rng.normal(3.0, 0.42, n).clip(1.5, 5.0).round(3),
        "tld": rng.choice(_LEGIT_TLD, n, p=[0.5, 0.15, 0.13, 0.14, 0.04, 0.04]),
        "is_phishing": 0,
    })


def _phish(rng):
    n = N_PHISH
    # Distributions deliberately OVERLAP the legit ones (a phishing URL is a
    # SHIFT, not a separate world) so the target is realistic (~0.93-0.96 acc),
    # not perfectly separable.
    return pd.DataFrame({
        "url_length": rng.normal(72, 26, n).clip(15, 260).round().astype(int),
        "num_dots": rng.poisson(2.7, n).clip(1, 10),
        "num_hyphens": rng.poisson(1.5, n).clip(0, 12),
        "num_digits": rng.poisson(4.5, n).clip(0, 40),
        "num_subdomains": rng.poisson(2.0, n).clip(0, 8),
        "num_params": rng.poisson(1.7, n).clip(0, 15),
        "domain_age_days": rng.gamma(2.2, 120, n).clip(0, 2500).round().astype(int),
        "has_ip": (rng.random(n) < 0.12).astype(int),
        "has_at_symbol": (rng.random(n) < 0.08).astype(int),
        "https": (rng.random(n) < 0.66).astype(int),
        "shortened": (rng.random(n) < 0.2).astype(int),
        "brand_in_subdomain": (rng.random(n) < 0.24).astype(int),
        "host_entropy": rng.normal(3.5, 0.5, n).clip(2.0, 5.4).round(3),
        "tld": rng.choice(_PHISH_TLD, n, p=[0.22, 0.18, 0.12, 0.12, 0.08, 0.1, 0.1, 0.08]),
        "is_phishing": 1,
    })


def build() -> pd.DataFrame:
    rng = np.random.default_rng(1337)
    df = pd.concat([_legit(rng), _phish(rng)], ignore_index=True)
    return df.sample(frac=1, random_state=7).reset_index(drop=True)


if __name__ == "__main__":
    df = build()
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} {df.shape} | phishing rate {df['is_phishing'].mean():.1%}")
