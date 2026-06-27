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
import base64 as _b64
import json
import random
from pathlib import Path

import pandas as pd

from prompt_injection import features  # même extracteur de features de surface

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "prompt_injection_mixed.csv"
MAP = ROOT / "taxonomy_bridge" / "synthetic_to_aegis_map.json"

# ── benign hard-negatives ────────────────────────────────────────────────────
# Textes BÉNINS qui portent les mêmes signaux de surface que des injections
# (base64, non-ASCII, fences de code, URLs, mots « système/ignore » en contexte
# légitime). Sans eux, la classe benign (étroite, synthétique) est trivialement
# séparable des injections augmentées (AEGIS/encoding) -> modèle saturé (~99 %)
# inutilisable dans la vue Exploiter. Ces hard-negatives créent le recouvrement
# réaliste : un détecteur sur features de surface DOIT s'y tromper parfois.
_HN_BODY = ("documentation update config value server log entry meeting notes summary "
            "report data pipeline release backup invoice schedule roadmap changelog").split()
_HN_NONASCII = ["Café résumé naïve über", "日本語の設定ファイル", "Ольга приехала вчера",
                "açaí jalapeño façade", "Grüße aus München ✦", "παράδειγμα κειμένου 😀"]
_HN_TRIGGERS = [
    "Please ignore the previous typo, the correct total is 42.",
    "As an administrator of our internal wiki, I updated this page.",
    "The system requirements are listed in the section below.",
    "Forget what I said earlier about the deadline — it moved to Friday.",
    "Now, let's review the developer onboarding instructions.",
]


def _rand_b64(rng, n):
    return _b64.b64encode(bytes(rng.randrange(256) for _ in range(n))).decode()


def _benign_hn_text(rng):
    parts = [" ".join(rng.choice(_HN_BODY) for _ in range(rng.randint(8, 45)))]
    if rng.random() < 0.55:
        parts.append(rng.choice(_HN_TRIGGERS))                          # trigger/role words, benign
    if rng.random() < 0.45:
        parts.append("```\n" + " ".join(rng.choice(_HN_BODY) for _ in range(rng.randint(3, 14))) + "\n```")
    if rng.random() < 0.40:
        parts.append("data:image/png;base64," + _rand_b64(rng, rng.randint(30, 130)))  # legit embedded blob
    if rng.random() < 0.45:
        parts.append(rng.choice(_HN_NONASCII))                          # non-ASCII benign
    if rng.random() < 0.35:
        parts.append("Refs: https://example.com/docs and www.intranet.local/page")
    return "\n".join(parts)


def benign_hard_negatives(n=900, seed=7) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        f = features(_benign_hn_text(rng))
        f.update({"label": "benign", "domain": "generic", "source": "synthetic_hardneg",
                  "language": "en", "carrier": rng.choice(["doc", "email", "web", "chat"]),
                  "multi_turn": 0, "obfuscation": "none", "template_group": "syn_hardneg"})
        rows.append(f)
    return pd.DataFrame(rows)

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

    parts = [_norm(ben), _norm(tech), _norm(aeg)]
    tr_path = ROOT / "prompt_injection_transform.csv"
    if tr_path.exists():  # encoding/transform techniques (programmatic augmentation)
        parts.append(_norm(pd.read_csv(tr_path)))
    parts.append(_norm(benign_hard_negatives()))  # recouvrement réaliste (anti-saturation)
    out = pd.concat(parts, ignore_index=True)
    # Dédoublonnage sur les features de surface : templates et augmentations
    # produisent ~30 % de lignes au vecteur de features IDENTIQUE. Sous le split
    # aléatoire du pipeline (pas de group-aware ici), ces doublons fuient entre
    # train et test -> accuracy ~100 % artificielle. On garde une occurrence par
    # vecteur de features (un modèle ne peut de toute façon pas les distinguer).
    return out.drop_duplicates(subset=FEAT, keep="first").reset_index(drop=True)


if __name__ == "__main__":
    mixed = build()
    mixed.to_csv(OUT, index=False, encoding="utf-8")
    print(f"wrote {OUT} {mixed.shape}")
    print("source:", mixed["source"].value_counts().to_dict())
    print("label:", mixed["label"].value_counts().to_dict())
    print("family_l2 non-null:", int(mixed["family_l2"].notna().sum()),
          "| target_delta non-null:", int(mixed["target_delta"].notna().sum()))
