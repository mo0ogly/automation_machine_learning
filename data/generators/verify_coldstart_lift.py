"""
Post-forge verification — measure the technique_l3 lift after new AEGIS templates
are added (brief: data/taxonomy_bridge/forge_brief_coldstart.md).

Reads the CURRENT poc_medical template library live, instantiates it, and reports
F1 macro (GroupKFold by template) on technique_l3 restricted to techniques that
now reach >= N distinct templates — the subset that became learnable. Compares to
the cold-start floor so a real lift is visible after each forge tier.

Fast: surface (15) + HashingVectorizer char n-grams only (no model download).
SAFETY: text is instantiated/vectorised in-script, never printed.

Run after a forge tier:
    python data/generators/verify_coldstart_lift.py [--min-templates 3] [--per-template 48]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_val_score
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generators"))
import build_aegis_text_features as B  # provides instantiate()
from prompt_injection import features

REPORT = ROOT / "coldstart_lift_report.json"
FLOOR = 0.04  # technique_l3 GroupKFold floor over the full label set (reference)


def gkf_f1(X, y, groups, clf):
    yv = y.astype(str).values
    return cross_val_score(clf, X, yv, cv=GroupKFold(5).split(X, yv, groups),
                           scoring="f1_macro", n_jobs=-1).mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-templates", type=int, default=3)
    ap.add_argument("--per-template", type=int, default=48)
    args = ap.parse_args()

    texts, lab = B.instantiate(per_template=args.per_template)
    lab = lab.reset_index(drop=True)
    g = lab["template_group"].values

    # depth: distinct templates per technique (current poc_medical state)
    tpt = lab.groupby("technique_l3")["template_group"].nunique()
    learnable = sorted(tpt[tpt >= args.min_templates].index)
    print("=== profondeur courante (templates distincts / technique) ===")
    print("techniques totales        :", int(tpt.size))
    print("  avec 1 template         :", int((tpt == 1).sum()))
    print("  avec 2 templates        :", int((tpt == 2).sum()))
    print("  avec >=%d templates      :" % args.min_templates, len(learnable))
    if not learnable:
        print("\nAucune technique a >=%d templates — forge d'abord (Tier 1)." % args.min_templates)
        return

    mask = lab["technique_l3"].isin(learnable).values
    y = lab["technique_l3"][mask]
    gm = g[mask]
    idx = np.where(mask)[0]
    Xs = pd.DataFrame([features(texts[i]) for i in idx])[B.SURFACE_COLS].to_numpy("float32")
    hv = HashingVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                           n_features=2 ** 18, alternate_sign=False, norm="l2")
    Xh = hv.transform([texts[i] for i in idx])

    f1_surface = gkf_f1(Xs, y, gm, RandomForestClassifier(n_estimators=200, random_state=0, n_jobs=-1))
    f1_hash = gkf_f1(Xh, y, gm, LinearSVC())
    best = max(f1_surface, f1_hash)

    print("\n=== lift technique_l3 sur le sous-ensemble apprenable ===")
    print("classes (>=%d templates) :" % args.min_templates, len(learnable))
    print("lignes                   :", int(mask.sum()))
    print("F1 macro surface         : %.3f" % f1_surface)
    print("F1 macro hashing         : %.3f" % f1_hash)
    print("plancher reference       : %.3f" % FLOOR)
    print("lift (best - plancher)   : %+.3f  (x%.1f)" % (best - FLOOR, best / FLOOR if FLOOR else 0))
    verdict = "LIFT" if best > 2 * FLOOR else "PAS DE LIFT (forger plus de templates distincts)"
    print("verdict                  :", verdict)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "min_templates": args.min_templates,
        "techniques_total": int(tpt.size),
        "techniques_learnable": len(learnable),
        "learnable_ids": learnable,
        "rows": int(mask.sum()),
        "f1_surface": round(float(f1_surface), 4),
        "f1_hashing": round(float(f1_hash), 4),
        "floor": FLOOR,
        "lift_best": round(float(best - FLOOR), 4),
        "verdict": verdict,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nrapport ->", REPORT)


if __name__ == "__main__":
    main()
