"""
Generate the synthetic anomaly-detection demo dataset (`data/transactions.csv`).

Bank-transaction-like records, deliberately WITHOUT a label column (unsupervised):
~285 normal transactions + ~15 injected anomalies (extreme amounts, many countries,
brand-new accounts, nocturnal activity). Fully deterministic (fixed seeds) so the CSV
is reproducible byte-for-byte.

Run from anywhere:
    python data/generators/transactions.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

N_NORMAL, N_ANOM = 285, 15
OUT = Path(__file__).resolve().parent.parent / "transactions.csv"


def build() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    normal = pd.DataFrame({
        "montant_eur": rng.normal(80, 25, N_NORMAL).clip(5, 200),
        "frequence_mensuelle": rng.normal(12, 4, N_NORMAL).clip(1, 30),
        "anciennete_mois": rng.normal(48, 20, N_NORMAL).clip(1, 120),
        "nb_pays": rng.poisson(1.2, N_NORMAL).clip(1, 5),
        "ratio_nuit": rng.beta(2, 8, N_NORMAL),
    })
    anomalies = pd.DataFrame({
        "montant_eur": rng.uniform(400, 900, N_ANOM),
        "frequence_mensuelle": rng.uniform(40, 80, N_ANOM),
        "anciennete_mois": rng.uniform(0, 3, N_ANOM),
        "nb_pays": rng.integers(6, 12, N_ANOM),
        "ratio_nuit": rng.uniform(0.7, 0.98, N_ANOM),
    })
    df = (pd.concat([normal, anomalies], ignore_index=True)
          .sample(frac=1, random_state=7).reset_index(drop=True)
          .round({"montant_eur": 2, "frequence_mensuelle": 1,
                  "anciennete_mois": 1, "ratio_nuit": 3}))
    df["nb_pays"] = df["nb_pays"].astype(int)
    return df


if __name__ == "__main__":
    df = build()
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT} {df.shape}")
