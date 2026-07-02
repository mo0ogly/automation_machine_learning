"""
Generate the synthetic CVE-severity demo (`data/cve_severity.csv`).

Multiclass (low / medium / high / critical) vulnerability-prioritisation dataset
built from CVSS v3-style base-metric components. A latent base score is computed
from the components with an additive model + noise, bucketed into the four
official CVSS severity bands; the RAW base score is then DROPPED so it cannot leak
the target — the pedagogical task is to predict severity from the vector itself
(attack vector, complexity, privileges, impact on C/I/A, scope) plus EPSS and
exploit maturity. Deterministic (fixed seed).

Run from anywhere:
    python data/generators/cve_severity.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

N = 4200
OUT = Path(__file__).resolve().parent.parent / "cve_severity.csv"

# CVSS v3 metric weights (approximate the official base-score direction, not the
# exact formula — enough for a learnable, non-trivial target).
_AV = {"network": 0.85, "adjacent": 0.62, "local": 0.55, "physical": 0.2}
_AC = {"low": 0.77, "high": 0.44}
_PR = {"none": 0.85, "low": 0.62, "high": 0.27}
_UI = {"none": 0.85, "required": 0.62}
_IMPACT = {"none": 0.0, "low": 0.22, "high": 0.56}


def _cat(rng, mapping, p):
    keys = list(mapping.keys())
    return rng.choice(keys, N, p=p)


def build() -> pd.DataFrame:
    rng = np.random.default_rng(90210)
    av = _cat(rng, _AV, [0.55, 0.15, 0.25, 0.05])
    ac = _cat(rng, _AC, [0.7, 0.3])
    pr = _cat(rng, _PR, [0.45, 0.35, 0.2])
    ui = _cat(rng, _UI, [0.6, 0.4])
    scope = rng.choice(["unchanged", "changed"], N, p=[0.75, 0.25])
    conf = _cat(rng, _IMPACT, [0.25, 0.35, 0.4])
    integ = _cat(rng, _IMPACT, [0.3, 0.35, 0.35])
    avail = _cat(rng, _IMPACT, [0.3, 0.3, 0.4])

    exploitability = 8.22 * np.array([_AV[x] for x in av]) * np.array([_AC[x] for x in ac]) \
        * np.array([_PR[x] for x in pr]) * np.array([_UI[x] for x in ui])
    iscbase = 1 - (1 - np.array([_IMPACT[x] for x in conf])) \
        * (1 - np.array([_IMPACT[x] for x in integ])) * (1 - np.array([_IMPACT[x] for x in avail]))
    changed = scope == "changed"
    impact = np.where(changed, 7.52 * (iscbase - 0.029) - 3.25 * (iscbase - 0.02) ** 15,
                      6.42 * iscbase)
    base = np.where(impact <= 0, 0.0,
                    np.where(changed, np.minimum(1.08 * (impact + exploitability), 10),
                             np.minimum(impact + exploitability, 10)))
    base = np.clip(base + rng.normal(0, 0.4, N), 0, 10)

    severity = np.where(base >= 9.0, "critical",
                np.where(base >= 7.0, "high",
                np.where(base >= 4.0, "medium", "low")))

    df = pd.DataFrame({
        "attack_vector": av, "attack_complexity": ac, "privileges_required": pr,
        "user_interaction": ui, "scope": scope,
        "confidentiality_impact": conf, "integrity_impact": integ, "availability_impact": avail,
        "epss_score": rng.beta(1.5, 12, N).round(4),          # exploitation probability
        "exploit_maturity": rng.choice(
            ["unproven", "poc", "functional", "high"], N, p=[0.45, 0.3, 0.18, 0.07]),
        "days_since_published": rng.gamma(2.0, 120, N).clip(0, 3000).round().astype(int),
        "severity": severity,   # target (base score dropped -> no leakage)
    })
    return df.sample(frac=1, random_state=3).reset_index(drop=True)


if __name__ == "__main__":
    df = build()
    df.to_csv(OUT, index=False)
    dist = df["severity"].value_counts(normalize=True).round(3).to_dict()
    print(f"wrote {OUT} {df.shape} | severity dist {dist}")
