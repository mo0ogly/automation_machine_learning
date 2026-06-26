#!/usr/bin/env python3
"""Phase OPEN automatisée — snapshot du laboratoire AEGIS.

Lit les 7 fichiers critiques et produit un snapshot structuré (JSON ou markdown).
Utilisé par /aegis-research-lab pour démarrer une session.

Usage:
    python session_snapshot.py            # markdown (terminal)
    python session_snapshot.py --json     # JSON (pour l'apex)
    python session_snapshot.py --session SESSION-043 --json
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent.parent  # poc_medical/
DISCOVERIES = ROOT / "research_archive" / "discoveries"
SIGNALS = ROOT / "research_archive" / "_staging" / "signals"
DATA_RAW = ROOT / "research_archive" / "data" / "raw"
RESEARCH_NOTES = ROOT / "research_archive" / "research_notes"
STAGING = ROOT / "_staging"


def _count_gaps(thesis_gaps_text: str) -> dict:
    """Compte les gaps par statut dans THESIS_GAPS.md."""
    open_count = len(re.findall(r'\bA CONCEVOIR\b', thesis_gaps_text))
    in_progress = len(re.findall(r'\bEN COURS\b', thesis_gaps_text))
    impl = re.findall(r'\*\*IMPLEMENTE\s+(\d{4}-\d{2}-\d{2})\*\*', thesis_gaps_text)
    closed = len(re.findall(r'\bFERM[ÉE]\b', thesis_gaps_text, re.IGNORECASE))

    # Impl without proof : has IMPLEMENTE but no THESIS-002/ASR_AFTER/VALIDÉ EMPIRIQUEMENT
    blocks = re.split(r'(?=### G-\d{3}|## G-\d{3})', thesis_gaps_text)
    impl_no_proof = 0
    impl_validated = 0
    for b in blocks:
        if re.search(r'\*\*IMPLEMENTE', b, re.IGNORECASE):
            if re.search(r'THESIS-002|ASR_AFTER|VALIDÉ EMPIRIQUEMENT|wilson_ci',
                         b, re.IGNORECASE):
                impl_validated += 1
            else:
                impl_no_proof += 1

    return {
        "a_concevoir": open_count,
        "en_cours": in_progress,
        "implemente_total": len(impl),
        "implemente_sans_preuve": impl_no_proof,
        "implemente_valide": impl_validated,
        "fermes": closed,
    }


def _parse_conjectures(text: str) -> list:
    """Extrait les scores C1-C7 depuis CONJECTURES_TRACKER.md."""
    results = []
    pattern = re.compile(
        r'(C\d+)[^\n]*?(\d+)/10[^\n]*?(FERMÉE|ACTIVE|CANDIDATE|HYPOTH[EÈ]SE|INVALID[EÉ]E)?',
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        cid, score, status = m.group(1), int(m.group(2)), (m.group(3) or "UNKNOWN").upper()
        if not any(r["id"] == cid for r in results):
            results.append({"id": cid, "score": score, "status": status})
        if len(results) >= 10:
            break
    return results


def _count_discoveries(text: str) -> dict:
    """Compte les discoveries D-XXX dans DISCOVERIES_INDEX.md."""
    ids = re.findall(r'\|\s*(D-(\d{3}))\s*\|', text)
    nums = [int(n) for _, n in ids]
    return {
        "total": len(nums),
        "max_id": max(nums) if nums else 0,
        "next_id": f"D-{max(nums) + 1:03d}" if nums else "D-001",
    }


def _list_signals() -> dict:
    """Liste les signaux non traités dans _staging/signals/."""
    if not SIGNALS.exists():
        return {"total": 0, "by_type": {}}

    by_type = {
        "CAMPAIGN_COMPLETE": [],
        "UNEXPECTED_FINDING": [],
        "CONJECTURE_VALIDATED": [],
        "ESCALADE_HUMAINE": [],
        "NEXT_CYCLE": [],
        "SESSION_COMPLETE": [],
        "other": [],
    }
    for f in SIGNALS.glob("*.json"):
        name = f.name
        matched = False
        for key in by_type:
            if key in name:
                by_type[key].append(name)
                matched = True
                break
        if not matched:
            by_type["other"].append(name)

    total = sum(len(v) for v in by_type.values())
    return {"total": total, "by_type": {k: v for k, v in by_type.items() if v}}


def _recent_campaigns() -> list:
    """Liste les 5 fichiers de campagne les plus récents."""
    if not DATA_RAW.exists():
        return []
    files = sorted(DATA_RAW.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
    return [{"name": f.name, "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()}
            for f in files]


def _recent_notes() -> list:
    """Liste les 3 dernières notes de recherche."""
    if not RESEARCH_NOTES.exists():
        return []
    files = sorted(RESEARCH_NOTES.glob("SESSION-*.md"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:3]
    return [{"name": f.name, "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()}
            for f in files]


def _latest_director_briefing() -> str | None:
    """Trouve le DIRECTOR_BRIEFING_RUN*.md le plus récent.

    Les briefings vivent dans `_staging/briefings/` depuis 2026-04-11.
    On scanne aussi la racine de `_staging/` pour rester compatible avec
    d'anciennes sessions, mais ce chemin est déprécié.
    """
    briefings_dir = STAGING / "briefings"
    candidates: list[Path] = []
    if briefings_dir.exists():
        candidates.extend(briefings_dir.glob("DIRECTOR_BRIEFING_RUN*.md"))
    if STAGING.exists():  # fallback héritage
        candidates.extend(STAGING.glob("DIRECTOR_BRIEFING_RUN*.md"))
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    # chemin relatif lisible depuis _staging/
    try:
        return str(latest.relative_to(STAGING)).replace("\\", "/")
    except ValueError:
        return latest.name


def build_snapshot(session_id: str = None) -> dict:
    """Construit le snapshot complet."""
    snap = {
        "session_id": session_id or f"SESSION-{datetime.now().strftime('%Y%m%d-%H%M')}",
        "timestamp": datetime.now().isoformat(),
        "state": {},
        "signals": {},
        "recent": {},
        "escalade": False,
    }

    # 1. THESIS_GAPS.md
    thesis_gaps = DISCOVERIES / "THESIS_GAPS.md"
    if thesis_gaps.exists():
        snap["state"]["gaps"] = _count_gaps(thesis_gaps.read_text(encoding="utf-8"))
    else:
        snap["state"]["gaps"] = {"error": "THESIS_GAPS.md not found"}

    # 2. CONJECTURES_TRACKER.md
    conj_file = DISCOVERIES / "CONJECTURES_TRACKER.md"
    if conj_file.exists():
        snap["state"]["conjectures"] = _parse_conjectures(conj_file.read_text(encoding="utf-8"))
    else:
        snap["state"]["conjectures"] = []

    # 3. DISCOVERIES_INDEX.md
    disc_file = DISCOVERIES / "DISCOVERIES_INDEX.md"
    if disc_file.exists():
        snap["state"]["discoveries"] = _count_discoveries(disc_file.read_text(encoding="utf-8"))
    else:
        snap["state"]["discoveries"] = {"total": 0, "max_id": 0}

    # 4. Signaux
    snap["signals"] = _list_signals()
    if snap["signals"]["by_type"].get("ESCALADE_HUMAINE"):
        snap["escalade"] = True

    # 5. Campagnes récentes
    snap["recent"]["campaigns"] = _recent_campaigns()

    # 6. Notes récentes
    snap["recent"]["notes"] = _recent_notes()

    # 7. DIRECTOR_BRIEFING
    snap["recent"]["director_briefing"] = _latest_director_briefing()

    # Maturité estimée
    g = snap["state"]["gaps"]
    if isinstance(g, dict) and "fermes" in g:
        total_gaps = g["fermes"] + g["implemente_valide"] + g["implemente_sans_preuve"] + g["a_concevoir"] + g["en_cours"]
        if total_gaps > 0:
            maturity = (g["fermes"] + g["implemente_valide"] * 0.7) / total_gaps * 100
            snap["maturity_estimate_pct"] = round(maturity, 1)

    return snap


def format_markdown(snap: dict) -> str:
    """Format le snapshot en markdown lisible."""
    lines = []
    lines.append(f"== AEGIS RESEARCH LAB — {snap['session_id']} — {snap['timestamp'][:16].replace('T', ' ')} ==")
    lines.append("")

    if snap.get("escalade"):
        lines.append("!! ESCALADE HUMAINE DÉTECTÉE — HALT avant toute action !!")
        for s in snap["signals"]["by_type"].get("ESCALADE_HUMAINE", []):
            lines.append(f"  - {s}")
        lines.append("")

    lines.append("État du laboratoire :")
    g = snap["state"]["gaps"]
    if "error" not in g:
        lines.append(f"  Gaps          : {g['a_concevoir']} ouverts / "
                     f"{g['implemente_sans_preuve']} IMPLEMENTE sans preuve / "
                     f"{g['implemente_valide']} IMPLEMENTE validés / "
                     f"{g['fermes']} FERMÉS")
    else:
        lines.append(f"  Gaps          : {g['error']}")

    conj = snap["state"]["conjectures"]
    if conj:
        lines.append("  Conjectures   : " + " · ".join(
            f"{c['id']} {c['score']}/10" for c in conj[:7]
        ))
    else:
        lines.append("  Conjectures   : (tracker non trouvé)")

    d = snap["state"]["discoveries"]
    lines.append(f"  Discoveries   : D-001 → {d.get('max_id', 0):03d} ({d.get('total', 0)} total, next={d.get('next_id', '?')})")
    lines.append(f"  Campagnes     : {len(snap['recent']['campaigns'])} récentes dans data/raw/")
    lines.append(f"  Notes         : {len(snap['recent']['notes'])} dans research_notes/")
    if "maturity_estimate_pct" in snap:
        lines.append(f"  Maturité estimée : ~{snap['maturity_estimate_pct']}%")
    lines.append("")

    lines.append("Signaux non traités :")
    sigs = snap["signals"]["by_type"]
    if sigs:
        for k, v in sigs.items():
            lines.append(f"  {k:20s} : {len(v)}")
    else:
        lines.append("  (aucun)")
    lines.append("")

    if snap["recent"]["notes"]:
        latest = snap["recent"]["notes"][0]
        lines.append(f"Dernière note : {latest['name']} ({latest['mtime'][:10]})")
    else:
        lines.append("Dernière note : (aucune)")

    if snap["recent"]["director_briefing"]:
        lines.append(f"Director briefing : {snap['recent']['director_briefing']}")

    return "\n".join(lines)


def main():
    as_json = "--json" in sys.argv
    session_id = None
    for i, arg in enumerate(sys.argv):
        if arg == "--session" and i + 1 < len(sys.argv):
            session_id = sys.argv[i + 1]

    snap = build_snapshot(session_id)

    if as_json:
        print(json.dumps(snap, indent=2, ensure_ascii=False))
    else:
        print(format_markdown(snap))

    # Exit 1 si escalade détectée
    if snap.get("escalade"):
        sys.exit(1)


if __name__ == "__main__":
    main()
