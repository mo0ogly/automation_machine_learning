#!/usr/bin/env python3
"""Agrégation des tokens consommés par session apex — AEGIS Research Lab.

Lit les checkpoints JSON (_staging/research-lab/CHECKPOINT_*.json),
les fichiers JSONL d'iterations si présents, et les tags [TOKENS: N] dans
les notes de recherche pour construire un tableau de coût par session.

Usage:
    python cost_tracker.py                       # table markdown toutes sessions
    python cost_tracker.py --session SESSION-043 # filtrer une session
    python cost_tracker.py --json                # export JSON
    python cost_tracker.py --since 2026-01-01    # filtre date (ISO 8601)
    python cost_tracker.py --summary             # totaux seulement
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent.parent  # poc_medical/
CHECKPOINT_DIR = ROOT / "_staging" / "research-lab"
ITERATIONS_DIR = ROOT / "_staging" / "research-lab" / "iterations"
RESEARCH_NOTES = ROOT / "research_archive" / "research_notes"


# ---------------------------------------------------------------------------
# Sources de données
# ---------------------------------------------------------------------------

def _collect_from_checkpoints() -> dict[str, dict]:
    """Retourne un dict session_id → données partielles depuis les checkpoints."""
    result: dict[str, dict] = {}
    if not CHECKPOINT_DIR.exists():
        return result

    # Exclure les checkpoints de ligne parallèle (_line_A, _line_B, etc.)
    pattern = re.compile(r"^CHECKPOINT_(SESSION-[\w-]+)(?:_line_\w+)?\.json$")
    for path in CHECKPOINT_DIR.glob("CHECKPOINT_*.json"):
        m = pattern.match(path.name)
        if not m:
            continue
        # On ne traite que les checkpoints principaux (pas les lignes)
        if "_line_" in path.name:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        session_id = data.get("session_id") or m.group(1)
        timestamp = data.get("timestamp", "")
        phase = data.get("phase_courante", "?")
        tokens = data.get("tokens_consumed_estimate", 0) or 0
        delegations_done = len(data.get("delegations_terminees", []))

        # Garder le checkpoint avec le plus grand nombre de tokens (dernier état)
        existing = result.get(session_id)
        if existing is None or tokens >= existing.get("tokens", 0):
            result[session_id] = {
                "session_id": session_id,
                "timestamp": timestamp,
                "phase": phase,
                "tokens": tokens,
                "delegations": delegations_done,
                "source": "checkpoint",
            }

    return result


def _collect_from_jsonl() -> dict[str, int]:
    """Scanne les fichiers JSONL d'iterations — retourne session_id → tokens."""
    result: dict[str, int] = {}
    if not ITERATIONS_DIR.exists():
        return result

    session_pattern = re.compile(r"(SESSION-[\w-]+)")
    for path in ITERATIONS_DIR.glob("*.jsonl"):
        m = session_pattern.search(path.name)
        session_id = m.group(1) if m else path.stem

        tokens = 0
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    tokens += entry.get("tokens_consumed_estimate", 0) or 0
                    tokens += entry.get("tokens", 0) or 0
                except (json.JSONDecodeError, TypeError):
                    continue
        except OSError:
            continue

        if tokens > 0:
            result[session_id] = result.get(session_id, 0) + tokens

    return result


def _collect_from_notes() -> dict[str, dict]:
    """Cherche les tags [TOKENS: N] dans le frontmatter YAML des notes SESSION-*.md."""
    result: dict[str, dict] = {}
    if not RESEARCH_NOTES.exists():
        return result

    token_tag = re.compile(r"\[TOKENS:\s*(\d+)\]", re.IGNORECASE)
    date_tag = re.compile(r"^date[:\s]+(\d{4}-\d{2}-\d{2})", re.IGNORECASE | re.MULTILINE)
    signed_tag = re.compile(r"SESSION-\d{3}[_\w]*\.md$")

    for path in RESEARCH_NOTES.glob("SESSION-*.md"):
        # Extraire le session_id depuis le nom du fichier
        name_match = re.match(r"(SESSION-\d{3,})", path.name)
        if not name_match:
            continue
        session_id = name_match.group(1)

        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        # Lire uniquement le frontmatter (entre les --- )
        frontmatter = ""
        if content.startswith("---"):
            end = content.find("\n---", 3)
            if end != -1:
                frontmatter = content[: end + 4]
            else:
                frontmatter = content[:500]
        else:
            frontmatter = content[:500]

        tokens_m = token_tag.search(frontmatter) or token_tag.search(content[:1000])
        if not tokens_m:
            continue

        tokens = int(tokens_m.group(1))
        date_m = date_tag.search(frontmatter)
        date_str = date_m.group(1) if date_m else ""

        is_signed = "_DRAFT" not in path.name
        result[session_id] = {
            "session_id": session_id,
            "timestamp": date_str + "T00:00:00" if date_str else "",
            "tokens": tokens,
            "signed": is_signed,
        }

    return result


# ---------------------------------------------------------------------------
# Fusion des sources
# ---------------------------------------------------------------------------

def _merge_sources() -> list[dict]:
    """Fusionne les trois sources et retourne une liste de sessions."""
    from_checkpoints = _collect_from_checkpoints()
    from_jsonl = _collect_from_jsonl()
    from_notes = _collect_from_notes()

    all_ids: set[str] = set(from_checkpoints) | set(from_jsonl) | set(from_notes)
    sessions: list[dict] = []

    for session_id in sorted(all_ids, reverse=True):
        ck = from_checkpoints.get(session_id, {})
        jl_tokens = from_jsonl.get(session_id, 0)
        nt = from_notes.get(session_id, {})

        # Tokens = max de toutes les sources (on prend la valeur la plus élevée
        # pour ne pas sous-estimer — un JSONL peut ajouter des tokens si le
        # checkpoint n'a pas été mis à jour en fin de session)
        tokens_ck = ck.get("tokens", 0)
        tokens_nt = nt.get("tokens", 0)
        tokens = max(tokens_ck, jl_tokens, tokens_nt)

        # Date : préférer checkpoint, puis note, puis vide
        timestamp = ck.get("timestamp") or nt.get("timestamp") or ""
        date_str = timestamp[:10] if timestamp else ""

        phase = ck.get("phase", "?")
        delegations = ck.get("delegations", 0)
        signed = nt.get("signed", False) if nt else ("_DRAFT" not in session_id)
        note_status = "signed" if signed else ("draft" if nt else "-")

        sessions.append({
            "session_id": session_id,
            "date": date_str,
            "phase": phase,
            "delegations": delegations,
            "tokens": tokens,
            "note_status": note_status,
        })

    return sessions


# ---------------------------------------------------------------------------
# Filtres
# ---------------------------------------------------------------------------

def _apply_filters(
    sessions: list[dict],
    session_filter: str | None,
    since: str | None,
) -> list[dict]:
    if session_filter:
        sessions = [s for s in sessions if s["session_id"] == session_filter]
    if since:
        try:
            since_date = date.fromisoformat(since)
            sessions = [
                s for s in sessions
                if s["date"] and date.fromisoformat(s["date"]) >= since_date
            ]
        except ValueError:
            print(
                f"Avertissement : date --since invalide ({since}), filtre ignoré.",
                file=sys.stderr,
            )
    return sessions


# ---------------------------------------------------------------------------
# Formatage
# ---------------------------------------------------------------------------

def _format_tokens(n: int) -> str:
    if n == 0:
        return "—"
    return f"~{n:,}".replace(",", "\u202f")  # espace fine comme séparateur milliers


def _format_markdown(sessions: list[dict], summary_only: bool = False) -> str:
    lines: list[str] = []
    lines.append("== AEGIS Research Lab — Cost Tracker ==")
    lines.append("")

    if not sessions:
        lines.append(
            "Aucune donnée de coût. Lance une session pour commencer à collecter."
        )
        return "\n".join(lines)

    total_tokens = sum(s["tokens"] for s in sessions)
    max_session = max(sessions, key=lambda s: s["tokens"])

    if not summary_only:
        header = (
            "| Session      | Date       | Phase   | Délégations | Tokens estim. | Notes  |"
        )
        sep = (
            "|--------------|------------|---------|-------------|---------------|--------|"
        )
        lines.append(header)
        lines.append(sep)
        for s in sessions:
            line = (
                f"| {s['session_id']:<12s} "
                f"| {s['date']:<10s} "
                f"| {s['phase']:<7s} "
                f"| {s['delegations']:<11d} "
                f"| {_format_tokens(s['tokens']):<13s} "
                f"| {s['note_status']:<6s} |"
            )
            lines.append(line)
        lines.append("")

    lines.append(
        f"Totaux : {len(sessions)} session{'s' if len(sessions) > 1 else ''}, "
        f"{_format_tokens(total_tokens)} tokens estimés"
    )
    if len(sessions) > 0:
        avg = total_tokens // len(sessions)
        lines.append(f"Moyenne par session : {_format_tokens(avg)}")
    if max_session["tokens"] > 0:
        lines.append(
            f"Session la plus coûteuse : {max_session['session_id']} "
            f"({_format_tokens(max_session['tokens'])})"
        )

    return "\n".join(lines)


def _format_json(sessions: list[dict]) -> str:
    total_tokens = sum(s["tokens"] for s in sessions)
    avg = total_tokens // len(sessions) if sessions else 0
    max_s = max(sessions, key=lambda s: s["tokens"]) if sessions else {}
    payload = {
        "generated_at": datetime.now().isoformat(),
        "sessions": sessions,
        "totals": {
            "count": len(sessions),
            "tokens_total": total_tokens,
            "tokens_avg": avg,
            "most_expensive_session": max_s.get("session_id") if max_s else None,
            "most_expensive_tokens": max_s.get("tokens", 0) if max_s else 0,
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Entrée principale
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agrégation des tokens consommés par session apex AEGIS."
    )
    parser.add_argument(
        "--session",
        metavar="SESSION-ID",
        help="Filtrer sur une session précise (ex: SESSION-043)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Export JSON au lieu de markdown",
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Ne montrer que les sessions depuis cette date",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Afficher uniquement les totaux, sans le tableau détaillé",
    )
    args = parser.parse_args()

    sessions = _merge_sources()
    sessions = _apply_filters(sessions, args.session, args.since)

    if args.as_json:
        print(_format_json(sessions))
    else:
        print(_format_markdown(sessions, summary_only=args.summary))


if __name__ == "__main__":
    main()
