"""
Merge the 3 prompt-injection datasets into `data/prompt_injection_mixed.csv` under
the shared hierarchical schema (see data/taxonomy_bridge/README.md).

Sources:
  - synthetic benign      : benign rows of data/prompt_injection.csv (domain=generic)
  - synthetic injections  : data/prompt_injection_technique.csv, technique -> family_l2
                            via data/taxonomy_bridge/synthetic_to_aegis_map.json
  - aegis augmented       : data/prompt_injection_aegis.csv (full schema, domain=medical)

Shared columns = the 15 surface features + the label schema. Missing labels are
left null (e.g. target_delta exists only on aegis rows).

CAVEAT (documented): domain correlates with source (medical=aegis, generic=synthetic).
Keep `domain` as a feature only to *measure/neutralise* this bias, never as a free
predictor. For honest fine-grained eval, split GROUP-AWARE on `template_group`.

Run:
    python data/generators/build_mixed.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "prompt_injection_mixed.csv"
MAP = ROOT / "taxonomy_bridge" / "synthetic_to_aegis_map.json"

FEAT = ["text_length", "word_count", "avg_word_length", "max_token_length",
        "uppercase_ratio", "digit_ratio", "punct_ratio", "line_count",
        "non_ascii_ratio", "zero_width_count", "url_count", "trigger_keyword_count",
        "role_keyword_count", "delimiter_marker_count", "has_base64_blob"]
COLS = FEAT + ["label", "family_l2", "technique_l3", "target_delta", "objective",
               "domain", "multi_turn", "obfuscation", "language", "carrier",
               "template_group", "source"]


def _norm(df):
    for c in COLS:
        if c not in df.columns:
            df[c] = None
    return df[COLS]


def build():
    m = json.load(open(MAP, encoding="utf-8"))["map"]
    syn2fam = {k: (v["family_id"] or "objective_only") for k, v in m.items()}
    syn2obj = {k: v["objective"] for k, v in m.items()}

    det = pd.read_csv(ROOT / "prompt_injection.csv")
    ben = det[det.label == "benign"].copy()
    ben["domain"] = "generic"; ben["source"] = "synthetic"; ben["multi_turn"] = 0
    ben["obfuscation"] = "none"; ben["template_group"] = "syn_benign"

    tech = pd.read_csv(ROOT / "prompt_injection_technique.csv").copy()
    tech["label"] = "injection"
    tech["technique_l3"] = tech["technique"]
    tech["family_l2"] = tech["technique"].map(syn2fam)
    tech["objective"] = tech["technique"].map(syn2obj)
    tech["domain"] = "generic"; tech["source"] = "synthetic"; tech["multi_turn"] = 0
    tech["obfuscation"] = "unknown"
    tech["template_group"] = "syn_" + tech["technique"].astype(str)

    aeg = pd.read_csv(ROOT / "prompt_injection_aegis.csv").copy()
    aeg["source"] = "aegis_aug"; aeg["objective"] = None

    return pd.concat([_norm(ben), _norm(tech), _norm(aeg)], ignore_index=True)


if __name__ == "__main__":
    mixed = build()
    mixed.to_csv(OUT, index=False, encoding="utf-8")
    print(f"wrote {OUT} {mixed.shape}")
    print("source:", mixed["source"].value_counts().to_dict())
    print("label:", mixed["label"].value_counts().to_dict())
    print("family_l2 non-null:", int(mixed["family_l2"].notna().sum()),
          "| target_delta non-null:", int(mixed["target_delta"].notna().sum()))
