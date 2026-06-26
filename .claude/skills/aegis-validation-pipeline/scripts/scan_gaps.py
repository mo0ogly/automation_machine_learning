#!/usr/bin/env python3
"""Scan THESIS_GAPS.md for IMPLEMENTE gaps without empirical proof.

Usage:
    python scan_gaps.py [G-032|all] [--json]

Output: JSON list of gaps to validate.
"""
import json
import re
import sys
from pathlib import Path

THESIS_GAPS_PATH = Path(__file__).parent.parent.parent.parent.parent \
    / "research_archive" / "discoveries" / "THESIS_GAPS.md"

# Mapping gap → chains most relevant to test
GAP_CHAIN_MAP = {
    "G-032": ["hyde", "xml_agent", "functions_agent"],
    "G-037": ["hyde", "xml_agent", "functions_agent", "stepback"],
    "G-038": ["hyde", "xml_agent"],
    "G-041": ["rag_fusion", "hyde"],
    "G-028": ["hyde", "xml_agent"],
    "G-035": ["hyde", "xml_agent", "functions_agent"],
}

HIGH_ASR_CHAINS = ["hyde", "xml_agent"]  # 96.7% in THESIS-001


def scan_gaps(target_gap: str = None) -> list:
    """Return list of IMPLEMENTE gaps without empirical proof."""
    if not THESIS_GAPS_PATH.exists():
        print(f"ERROR: {THESIS_GAPS_PATH} not found", file=sys.stderr)
        return []

    text = THESIS_GAPS_PATH.read_text(encoding="utf-8")

    # Find all gap sections
    # Pattern: "G-NNN" heading or table row with IMPLEMENTE status
    gap_blocks = re.split(r'(?=### G-\d{3}|## G-\d{3})', text)

    results = []
    impl_re = re.compile(r'\*\*IMPLEMENTE\s+(\d{4}-\d{2}-\d{2})\*\*', re.IGNORECASE)
    proof_re = re.compile(r'THESIS-002|ASR_AFTER|VALIDÉ EMPIRIQUEMENT|wilson_ci', re.IGNORECASE)
    gap_id_re = re.compile(r'###?\s*(G-(\d{3}))')
    impl_file_re = re.compile(r'`([^`]+\.py[^`]*)`')

    for block in gap_blocks:
        m = gap_id_re.search(block)
        if not m:
            continue
        gap_id = m.group(1)

        if target_gap and gap_id != target_gap:
            continue

        impl_m = impl_re.search(block)
        if not impl_m:
            continue  # not implemented yet

        has_proof = bool(proof_re.search(block))
        impl_files = impl_file_re.findall(block)
        chains = GAP_CHAIN_MAP.get(gap_id, HIGH_ASR_CHAINS)

        results.append({
            "gap_id": gap_id,
            "status": f"IMPLEMENTE {impl_m.group(1)}",
            "impl_files": impl_files[:4],  # top 4
            "chains": chains,
            "has_empirical_proof": has_proof,
            "priority": "high" if any(c in HIGH_ASR_CHAINS for c in chains) else "normal",
        })

    # Filter: only gaps without empirical proof
    pending = [g for g in results if not g["has_empirical_proof"]]

    # Sort: high-ASR chains first
    pending.sort(key=lambda g: (0 if g["priority"] == "high" else 1, g["gap_id"]))
    return pending


def main():
    target = None
    as_json = "--json" in sys.argv
    for arg in sys.argv[1:]:
        if arg.startswith("G-"):
            target = arg
        elif arg in ("all", "pending"):
            target = None

    gaps = scan_gaps(target)

    if as_json or not sys.stdout.isatty():
        print(json.dumps(gaps, indent=2, ensure_ascii=False))
    else:
        if not gaps:
            print("✓ Aucun gap IMPLEMENTE sans preuve empirique.")
            return
        print(f"Gaps IMPLEMENTE sans preuve empirique ({len(gaps)}) :\n")
        for g in gaps:
            proof = "✗ sans preuve" if not g["has_empirical_proof"] else "✓ validé"
            print(f"  {g['gap_id']}  [{g['status']}]  {proof}")
            print(f"    Chaînes : {', '.join(g['chains'])}")
            if g["impl_files"]:
                print(f"    Fichiers : {g['impl_files'][0]}")
        print()
        print(f"Commande suggérée :")
        ids = " ".join(g["gap_id"] for g in gaps)
        print(f"  python backend/run_thesis_campaign.py --chains hyde xml_agent --n-trials 30 --aegis-shield")


if __name__ == "__main__":
    main()
