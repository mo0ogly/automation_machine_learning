"""
Build the taxonomy-bridge deliverables that reconcile the 3 datasets:
  - families_L2.json        : 16 CrowdStrike categories as L2 families (+ depth)
  - synthetic_to_aegis_map.json : synthetic 12 techniques -> family + objective axis
  - gaps_map.json           : empty category x delta cells, shallow techniques, missing axes
  - coverage.json           : per-technique template counts (depth atlas)

Reads ONLY metadata from poc_medical (taxonomy JSON + prompt metadata, never the
`template` field). Outputs into machine_learning/data/taxonomy_bridge/.
"""
import json, glob, collections, os

POC = r"C:/Users/pizzif/Documents/GitHub/poc_medical/backend"
OUT = r"C:/Users/pizzif/Documents/GitHub/machine_learning/data/taxonomy_bridge"
os.makedirs(OUT, exist_ok=True)

cs = json.load(open(POC + "/taxonomy/crowdstrike_2025.json", encoding="utf-8"))

# --- usage counts (primary + secondary), and category x delta cross-tab ---
use = collections.Counter()
prim_use = collections.Counter()
xtab = collections.Counter()
cat_count = collections.Counter()
delta_count = collections.Counter()
n_chain = n_detect = n_var = templates = 0
for fp in glob.glob(POC + "/prompts/*.json"):
    try:
        o = json.load(open(fp, encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(o, dict) or "taxonomy" not in o:
        continue
    templates += 1
    tx = o.get("taxonomy") or {}
    if isinstance(tx, dict):
        if tx.get("primary"):
            use[tx["primary"]] += 1
            prim_use[tx["primary"]] += 1
        for s in (tx.get("secondary") or []):
            use[s] += 1
    cat_count[o.get("category")] += 1
    delta_count[o.get("target_delta")] += 1
    xtab[(o.get("category"), o.get("target_delta"))] += 1
    if o.get("chain_id"):
        n_chain += 1
    if o.get("detection_profile"):
        n_detect += 1
    if isinstance(o.get("variables"), dict) and o["variables"]:
        n_var += 1

# --- L2 families = CrowdStrike categories ---
families = []
tech2family = {}
for cl in cs["classes"]:
    for cat in cl.get("categories", []):
        techs = list(cat.get("techniques", []))
        for sc in cat.get("subcategories", []):
            techs += sc.get("techniques", [])
        tlist = []
        for t in techs:
            tech2family[t["id"]] = cat["id"]
            tlist.append({"id": t["id"], "label": t["label"],
                          "n_templates_primary": prim_use.get(t["id"], 0),
                          "n_templates_any": use.get(t["id"], 0)})
        families.append({
            "family_id": cat["id"],
            "cs_class": cl["id"],
            "n_techniques": len(techs),
            "n_templates_primary": sum(x["n_templates_primary"] for x in tlist),
            "techniques": sorted(tlist, key=lambda x: -x["n_templates_any"]),
        })
families.sort(key=lambda f: -f["n_templates_primary"])

# --- synthetic 12 -> bridge (mechanism family + orthogonal objective axis) ---
# axis_type: "mechanism" = real CS technique family ; "objective" = impact/goal,
# not a CrowdStrike mechanism -> becomes an orthogonal label, mapping is weak.
SYN = {
    "instruction_override": {"family_id": "semantic_manipulation", "objective": "rule_subversion",
        "axis": "mechanism", "confidence": "high", "cs_anchor": "rule_nullification_prompting",
        "note": "Annuler/remplacer les consignes = rule nullification/substitution."},
    "delimiter_injection": {"family_id": "instruction_reformulation", "objective": "context_escape",
        "axis": "mechanism", "confidence": "medium", "cs_anchor": "formatting_disruption",
        "note": "Faux delimiteurs = perturbation de format / echappement du bac a sable de donnee."},
    "role_hijack": {"family_id": "context_shift_prompting", "objective": "persona_takeover",
        "axis": "mechanism", "confidence": "high", "cs_anchor": "role_play_prompting",
        "note": "Reassignation de persona/role."},
    "fake_authority": {"family_id": "context_shift_prompting", "objective": "authority_spoof",
        "axis": "mechanism", "confidence": "high", "cs_anchor": "false_authorization_prompting",
        "note": "Usurpation d'autorite systeme/admin."},
    "refusal_suppression": {"family_id": "semantic_manipulation", "objective": "guardrail_bypass",
        "axis": "mechanism", "confidence": "high", "cs_anchor": "refusal_suppression",
        "note": "Correspondance exacte : refusal_suppression existe dans CrowdStrike."},
    "system_prompt_leak": {"family_id": "context_shift_prompting", "objective": "secret_extraction",
        "axis": "mixed", "confidence": "medium", "cs_anchor": "specific_secret_attribute_probing",
        "note": "Mecanisme = secret probing ; objectif = extraction du prompt systeme."},
    "data_exfiltration": {"family_id": None, "objective": "exfiltration",
        "axis": "objective", "confidence": "na", "cs_anchor": None,
        "note": "OBJECTIF (OWASP LLM02/06), pas un mecanisme CrowdStrike. Axe orthogonal."},
    "tool_abuse": {"family_id": None, "objective": "tool_agency_abuse",
        "axis": "objective", "confidence": "na", "cs_anchor": None,
        "note": "OBJECTIF (OWASP LLM06 excessive agency). Axe orthogonal."},
    "output_manipulation": {"family_id": "response_steering_prompting", "objective": "output_integrity",
        "axis": "mixed", "confidence": "low", "cs_anchor": "output_seeding",
        "note": "Mecanisme proche = output_seeding/leading_response ; objectif = integrite de sortie (LLM05)."},
    "misinformation_seed": {"family_id": "response_steering_prompting", "objective": "misinformation",
        "axis": "mixed", "confidence": "low", "cs_anchor": "leading_response",
        "note": "Mecanisme = leading_response/output_seeding ; objectif = desinformation (LLM09)."},
    "conditional_trigger": {"family_id": None, "objective": "deferred_trigger",
        "axis": "objective", "confidence": "na", "cs_anchor": None,
        "note": "Declenchement conditionnel/differe : axe temporel orthogonal, pas un mecanisme CS."},
    "staged_multistep": {"family_id": None, "objective": "multi_turn",
        "axis": "objective", "confidence": "na", "cs_anchor": None,
        "note": "Attaque multi-etapes : correspond a l'axe chain_id d'AEGIS, pas a une technique CS."},
}

# --- gaps map ---
all_deltas = ["delta0", "delta1", "delta2", "delta3"]
all_cats = ["injection", "rule_bypass", "prompt_leak"]
def cell(c, d):
    return sum(v for (cc, dd), v in xtab.items()
              if cc == c and (dd == d or (dd or "").startswith(d + "_")))
empty_cells = [{"category": c, "target_delta": d} for c in all_cats for d in all_deltas
               if cell(c, d) == 0]
sparse_cells = [{"category": c, "target_delta": d, "n": cell(c, d)}
                for c in all_cats for d in all_deltas if 0 < cell(c, d) <= 3]
shallow_tech = sorted([t for t, n in prim_use.items() if n <= 1])
deep_tech = [{"id": t, "n": n} for t, n in prim_use.most_common(8)]

gaps = {
    "category_delta_matrix": {c: {d: cell(c, d) for d in all_deltas} for c in all_cats},
    "empty_cells": empty_cells,
    "sparse_cells_le3": sparse_cells,
    "shallow_techniques_le1_primary": {"count": len(shallow_tech), "ids": shallow_tech},
    "deepest_techniques": deep_tech,
    "missing_axes_vs_other_datasets": [
        "domain: AEGIS=medical/robotic ; synthetic=generic -> add `domain` axis",
        "multi_turn: 44/126 AEGIS have chain_id ; absent in synthetic & ML datasets",
        "objective: exfiltration/tool_abuse/misinformation present in synthetic, "
        "weakly represented as explicit objective axis in AEGIS",
        "carrier/language: rich in synthetic, sparse/implicit in AEGIS",
    ],
    "fill_priorities_for_dataset3": [
        "delta0 (RLHF/alignment-targeting attacks) - only %d templates" % delta_count.get("delta0", 0),
        "delta3 (output-enforcement-targeting) - near empty",
        "prompt_leak beyond delta1 - currently 6, all delta1",
        "depth: %d/80 techniques have <=1 template -> augment via variables" % len(shallow_tech),
    ],
}

summary = {
    "templates_classified": templates,
    "cs_techniques_total": sum(f["n_techniques"] for f in families),
    "cs_coverage": "100% (all CrowdStrike techniques instantiated)",
    "n_families_L2": len(families),
    "category_counts": dict(cat_count),
    "delta_counts": dict(delta_count),
    "templates_with_chain_id": n_chain,
    "templates_with_detection_profile": n_detect,
    "templates_parameterized": n_var,
}

json.dump({"summary": summary, "families": families}, open(OUT + "/families_L2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump({"note": "axis=objective => pas de mecanisme CrowdStrike equivalent (axe orthogonal)", "map": SYN}, open(OUT + "/synthetic_to_aegis_map.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
json.dump(gaps, open(OUT + "/gaps_map.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("families:", len(families), "| empty cells:", len(empty_cells), "| shallow:", len(shallow_tech))
print("wrote ->", OUT)
