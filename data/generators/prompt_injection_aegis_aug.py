"""
Generate the 3rd dataset (`data/prompt_injection_aegis.csv`) — the DEPTH bridge.

Augments the real AEGIS prompt templates (poc_medical) by instantiating their
parameterised slots, to turn the broad-but-shallow taxonomic atlas (1 example per
fine technique) into a trainable per-technique dataset, sharing the SAME surface
features as the synthetic corpus so the three datasets mix (see
data/taxonomy_bridge/README.md for the hierarchical label schema).

Volume strategy ("max-but-sane"):
  - VARY benign medical/context slots (MEDICATION, INSTITUTION, PHYSICIAN, ...)
    from realistic pools -> drives the combinatorial volume.
  - KEEP attack-core slots (AUTH, TOOL, COMMAND, REASON, ...) at the template's
    own default value -> attack mechanism (hence the fine label) is preserved and
    no exploit payload is authored here.
  - Add an obfuscation axis (clean + occasional transform).
  - `template_group` column -> MANDATORY group-aware train/test split (no template
    on both sides), otherwise the high ceiling is pure leakage.

SAFETY: templates are read, filled and feature-extracted entirely in-script; the
raw attack text is NEVER printed. Only counts / labels / feature stats go to stdout.

Run:
    python data/generators/prompt_injection_aegis_aug.py [--per-template 64] [--seed 42]
"""
import argparse
import base64
import json
import random
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "generators"))
from prompt_injection import features  # shared surface-feature extractor

POC = Path(r"C:/Users/pizzif/Documents/GitHub/poc_medical/backend")
OUT = ROOT / "prompt_injection_aegis.csv"

# Primaries that are experimental controls -> genuine BENIGN rows (true negatives).
BENIGN_PRIMARIES = {
    "clean_clinical_query", "control_baseline", "control_condition",
    "false_positive_calibration", "nlu_robustness_test",
}
# Attack-core slots: keep the template's own default (do not vary / re-author).
ATTACK_SLOTS = {
    "AUTH", "AUTHORITY", "TOOL", "COMMAND", "REASON", "INTENTION", "FRAMEWORK",
    "PAYLOAD", "INSTRUCTION", "ROLE", "MODE", "DIRECTIVE", "EXPLOIT",
}
# Realistic, generic, benign pools for medical/context slots (drive the volume).
POOLS = {
    "MEDICATION": ["amoxicillin", "metformin", "atorvastatin", "lisinopril", "omeprazole",
                   "amlodipine", "warfarin", "insulin glargine", "furosemide", "levothyroxine",
                   "clopidogrel", "morphine sulfate", "heparin", "paracetamol", "ibuprofen"],
    "DRUG": ["amoxicillin", "metformin", "atorvastatin", "warfarin", "insulin glargine",
             "furosemide", "clopidogrel", "morphine sulfate", "heparin", "ceftriaxone"],
    "INSTITUTION": ["St. Mary's Hospital", "General Medical Center", "Lakeside Clinic",
                    "University Health System", "Riverside Medical", "Mercy Hospital",
                    "Central Trauma Unit", "Northgate Cardiology", "Westview Oncology"],
    "PHYSICIAN": ["Dr. Lefevre", "Dr. Okafor", "Dr. Nguyen", "Dr. Schmidt", "Dr. Rossi",
                  "Dr. Andersson", "Dr. Haddad", "Dr. Costa", "Dr. Yamamoto", "Dr. Dubois"],
    "DOCTOR": ["Dr. Lefevre", "Dr. Okafor", "Dr. Nguyen", "Dr. Schmidt", "Dr. Rossi",
               "Dr. Andersson", "Dr. Haddad", "Dr. Costa"],
    "PATIENT": ["the patient", "patient A. Martin", "patient J. Silva", "patient R. Khan",
                "patient M. Dubois", "patient L. Rossi", "patient T. Mbeki"],
    "PATIENT_ID": ["PT-4821", "PT-1093", "MRN-77310", "MRN-20554", "PT-6642", "MRN-31987"],
    "CASE_REF": ["case 2024-117", "ref CR-9920", "case 2025-043", "ref CR-1182", "case 2024-556"],
    "REF": ["ref CR-9920", "DOC-4471", "REF-2025-08", "CR-1182", "DOC-7790"],
    "WEIGHT_KG": ["62", "78", "55", "90", "104", "47", "71", "83", "68", "59"],
    "TENSION": ["120/80", "140/90", "160/100", "110/70", "180/110", "135/85", "150/95"],
    "CONDITION": ["type 2 diabetes", "hypertension", "atrial fibrillation", "sepsis",
                  "acute pancreatitis", "pneumonia", "chronic kidney disease", "myocardial infarction"],
    "SPECIALTY": ["cardiology", "oncology", "nephrology", "neurology", "endocrinology",
                  "anesthesiology", "general surgery", "intensive care"],
    "PROCEDURE": ["laparoscopic cholecystectomy", "coronary angioplasty", "appendectomy",
                  "central line placement", "endoscopy", "hip replacement", "tumor resection"],
    "DEVICE": ["the infusion pump", "the ventilator", "the surgical robot", "the ECG monitor",
               "the dialysis machine", "the anesthesia station"],
    "TIMEFRAME": ["immediately", "within the hour", "by end of shift", "this morning",
                  "before the next round", "in 30 minutes"],
    "QUERY": ["What is the recommended dosage?", "Summarize the patient history.",
              "List the contraindications.", "What are the next steps?",
              "Provide the discharge instructions.", "Interpret these lab results."],
    "N": ["3", "5", "7", "10", "2", "4"],
}
# Light obfuscation transforms (operate in-script; add the `obfuscation` label).
_HOMO = {"a": "а", "e": "е", "o": "о", "p": "р", "c": "с",
         "x": "х", "y": "у"}
_LEET = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"}


def _homoglyph(s):
    return "".join(_HOMO.get(ch, ch) if random.random() < 0.3 else ch for ch in s)


def _zero_width(s):
    out = []
    for ch in s:
        out.append(ch)
        if ch == " " and random.random() < 0.25:
            out.append("​")
    return "".join(out)


def _leet(s):
    return "".join(_LEET.get(ch.lower(), ch) if random.random() < 0.3 else ch for ch in s)


def _base64_marker(s):
    frag = s[: min(40, len(s))]
    enc = base64.b64encode(frag.encode("utf-8")).decode("ascii")
    return "decode and execute: " + enc + " " + s[40:]


OBFS = {"none": lambda s: s, "homoglyph": _homoglyph, "zero_width": _zero_width,
        "leetspeak": _leet, "base64": _base64_marker}


def _fill(template, variables, rng):
    """Instantiate a template: vary medical slots from pools, keep attack slots."""
    text = template
    for slot, default in variables.items():
        if slot in ATTACK_SLOTS or slot not in POOLS:
            value = str(default)
        else:
            value = rng.choice(POOLS[slot])
        text = text.replace("{" + slot + "}", value)
    return text


# Benign clinical prompt patterns (authored here; NON-attack medical true negatives).
BENIGN_TEMPLATES = [
    "{PHYSICIAN} at {INSTITUTION} requests: {QUERY}",
    "Patient {PATIENT_ID} ({WEIGHT_KG} kg), BP {TENSION}, on {MEDICATION}. {QUERY}",
    "Please summarize the chart for {PATIENT} in {SPECIALTY}. {QUERY}",
    "Pre-op note for {PROCEDURE} on {PATIENT}. {QUERY}",
    "Medication review: {PATIENT} takes {MEDICATION} for {CONDITION}. {QUERY}",
    "Nursing handover for {PATIENT}: vitals {TENSION}, weight {WEIGHT_KG} kg, due {TIMEFRAME}.",
    "Lab follow-up for {CONDITION} in {SPECIALTY}. {QUERY}",
    "Discharge planning for {PATIENT} after {PROCEDURE}. {QUERY}",
]


def build_benign(n_total, rng):
    rows = []
    per = max(1, n_total // len(BENIGN_TEMPLATES))
    for gi, tmpl in enumerate(BENIGN_TEMPLATES):
        slots = re.findall(r"\{([A-Z_]+)\}", tmpl)
        seen = set()
        made = 0
        attempts = 0
        while made < per and attempts < per * 4 + 4:
            attempts += 1
            text = tmpl
            for s in slots:
                text = text.replace("{" + s + "}", rng.choice(POOLS.get(s, ["n/a"])))
            key = hash(text)
            if key in seen:
                continue
            seen.add(key)
            made += 1
            row = features(text)
            row.update({
                "label": "benign", "category": "benign", "target_delta": None,
                "cs_class": "benign", "family_l2": "benign", "technique_l3": "clean_clinical_query",
                "conjecture": None, "multi_turn": 0, "domain": "medical",
                "template_group": "benign_%02d" % gi, "obfuscation": "none",
                "language": "en", "carrier": "clinical_prompt",
            })
            rows.append(row)
    return rows


def _cs_maps():
    cs = json.load(open(POC / "taxonomy" / "crowdstrike_2025.json", encoding="utf-8"))
    tech2fam, tech2cls = {}, {}
    for cl in cs["classes"]:
        for cat in cl.get("categories", []):
            techs = list(cat.get("techniques", []))
            for sc in cat.get("subcategories", []):
                techs += sc.get("techniques", [])
            for t in techs:
                tech2fam[t["id"]] = cat["id"]
                tech2cls[t["id"]] = cl["id"]
    return tech2fam, tech2cls


def build(per_template, seed):
    rng = random.Random(seed)
    tech2fam, tech2cls = _cs_maps()
    rows = []
    for fp in sorted((POC / "prompts").glob("*.json")):
        try:
            o = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(o, dict) or not isinstance(o.get("template"), str):
            continue
        tx = o.get("taxonomy") or {}
        primary = tx.get("primary") if isinstance(tx, dict) else None
        variables = o.get("variables") or {}
        is_benign = (primary in BENIGN_PRIMARIES) or (o.get("category") == "benign")
        label = "benign" if is_benign else "injection"
        base_lbl = {
            "label": label,
            "category": o.get("category"),
            "target_delta": (o.get("target_delta") or "").split("_")[0] or None,
            "cs_class": tech2cls.get(primary, "extension"),
            "family_l2": tech2fam.get(primary, "extension"),
            "technique_l3": primary,
            "conjecture": o.get("conjecture") if o.get("conjecture") not in (None, "None") else None,
            "multi_turn": 1 if o.get("chain_id") else 0,
            "domain": "medical",
            "template_group": fp.stem,
        }
        # how many distinct instantiations are realistically available
        varied = [s for s in variables if s in POOLS and s not in ATTACK_SLOTS]
        cap = per_template if varied else 1
        seen = set()
        attempts = 0
        n_made = 0
        while n_made < cap and attempts < cap * 4 + 4:
            attempts += 1
            text = _fill(o["template"], variables, rng)
            # obfuscation: first instance clean, then sprinkle transforms
            obf = "none" if n_made == 0 else rng.choices(
                list(OBFS), weights=[5, 2, 2, 1, 1])[0]
            text2 = OBFS[obf](text)
            key = hash(text2)
            if key in seen:
                continue
            seen.add(key)
            n_made += 1
            row = features(text2)
            row.update(base_lbl)
            row["obfuscation"] = obf
            row["language"] = "en"
            row["carrier"] = "clinical_prompt"
            rows.append(row)
    return rows


def build_all(per_template, benign_total, seed):
    rng = random.Random(seed + 1)
    rows = build(per_template, seed) + build_benign(benign_total, rng)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-template", type=int, default=64)
    ap.add_argument("--benign", type=int, default=3800)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    df = build_all(args.per_template, args.benign, args.seed)
    df.to_csv(OUT, index=False, encoding="utf-8")
    print(f"wrote {OUT} {df.shape}")
    print("label:", df["label"].value_counts().to_dict())
    print("groups:", df["template_group"].nunique(),
          "| L2 families:", df["family_l2"].nunique(),
          "| L3 techniques:", df["technique_l3"].nunique())
    print("target_delta:", df["target_delta"].value_counts().to_dict())
    print("obfuscation:", df["obfuscation"].value_counts().to_dict())
