#!/usr/bin/env python3
"""Tracer l'évolution temporelle des scores C1-C7 via l'historique git.

Lit l'historique git de CONJECTURES_TRACKER.md, extrait les scores Cn à chaque
commit, et produit un ASCII chart ou un PNG (si --matplotlib est disponible).

Usage:
    python progression_curve.py                      # ASCII chart tout historique
    python progression_curve.py --conjecture C3      # une seule conjecture
    python progression_curve.py --since 2026-01-01   # filtre date
    python progression_curve.py --matplotlib         # PNG (si disponible)
    python progression_curve.py --json               # export JSON
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent.parent  # poc_medical/
DISCOVERIES = ROOT / "research_archive" / "discoveries"
CONJECTURES_FILE = DISCOVERIES / "CONJECTURES_TRACKER.md"
STAGING_DIR = ROOT / "_staging" / "research-lab"

# Regex identique à session_snapshot.py._parse_conjectures()
_CONJ_PATTERN = re.compile(
    r"(C\d+)[^\n]*?(\d+)/10[^\n]*?(FERMÉE|ACTIVE|CANDIDATE|HYPOTH[EÈ]SE|INVALID[EÉ]E)?",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Accès git
# ---------------------------------------------------------------------------

def _check_git_available() -> bool:
    """Vérifie que git est disponible dans le PATH."""
    try:
        subprocess.run(
            ["git", "--version"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def _get_repo_root() -> Path | None:
    """Retourne la racine du dépôt git contenant CONJECTURES_FILE, ou None."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            cwd=str(DISCOVERIES),
            timeout=10,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


def _get_commit_history(repo_root: Path, rel_path: str) -> list[dict]:
    """Retourne la liste des commits touchant rel_path, du plus ancien au plus récent.

    Chaque entrée : {"hash": str, "date": str (ISO), "subject": str}
    """
    try:
        result = subprocess.run(
            [
                "git", "log",
                "--follow",
                "--format=%H|%aI|%s",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=30,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        print(f"Erreur git log : {exc}", file=sys.stderr)
        return []

    if result.returncode != 0:
        return []

    commits = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        commit_hash, iso_date = parts[0], parts[1]
        subject = parts[2] if len(parts) > 2 else ""
        # Date ISO → date simple YYYY-MM-DD
        date_str = iso_date[:10] if iso_date else ""
        commits.append({"hash": commit_hash, "date": date_str, "subject": subject})

    # Du plus ancien au plus récent
    commits.reverse()
    return commits


def _get_file_at_commit(repo_root: Path, commit_hash: str, rel_path: str) -> str | None:
    """Retourne le contenu du fichier à un commit donné."""
    try:
        result = subprocess.run(
            ["git", "show", f"{commit_hash}:{rel_path}"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


# ---------------------------------------------------------------------------
# Parsing des conjectures
# ---------------------------------------------------------------------------

def _parse_conjectures(text: str) -> dict[str, int]:
    """Extrait {Cn: score} depuis le contenu de CONJECTURES_TRACKER.md.

    Copie exacte du pattern de session_snapshot.py._parse_conjectures().
    """
    seen: set[str] = set()
    scores: dict[str, int] = {}
    for m in _CONJ_PATTERN.finditer(text):
        cid = m.group(1).upper()
        score = int(m.group(2))
        if cid not in seen:
            seen.add(cid)
            scores[cid] = score
        if len(scores) >= 10:
            break
    return scores


# ---------------------------------------------------------------------------
# Construction de la timeline
# ---------------------------------------------------------------------------

def _build_timeline(
    repo_root: Path,
    rel_path: str,
    commits: list[dict],
    since: str | None = None,
) -> list[dict]:
    """Construit la liste [{date, hash, scores: {Cn: int}}] pour tous les commits."""
    since_date: date | None = None
    if since:
        try:
            since_date = date.fromisoformat(since)
        except ValueError:
            print(
                f"Avertissement : date --since invalide ({since}), filtre ignoré.",
                file=sys.stderr,
            )

    timeline: list[dict] = []
    for commit in commits:
        commit_date_str = commit["date"]
        if since_date and commit_date_str:
            try:
                if date.fromisoformat(commit_date_str) < since_date:
                    continue
            except ValueError:
                pass

        content = _get_file_at_commit(repo_root, commit["hash"], rel_path)
        if content is None:
            continue

        scores = _parse_conjectures(content)
        if not scores:
            continue

        timeline.append({
            "date": commit_date_str,
            "hash": commit["hash"][:8],
            "scores": scores,
        })

    return timeline


# ---------------------------------------------------------------------------
# ASCII chart
# ---------------------------------------------------------------------------

def _ascii_chart(
    timeline: list[dict],
    conjecture_filter: str | None = None,
) -> str:
    if not timeline:
        return "Aucun point de données — historique vide ou fichier non versionné."

    # Collecter tous les identifiants de conjectures présents
    all_ids: set[str] = set()
    for point in timeline:
        all_ids.update(point["scores"].keys())

    if conjecture_filter:
        cid = conjecture_filter.upper()
        if cid not in all_ids:
            return f"Conjecture {cid} introuvable dans l'historique."
        ids_to_show = [cid]
    else:
        ids_to_show = sorted(all_ids)

    date_start = timeline[0]["date"] if timeline else "?"
    date_end = timeline[-1]["date"] if timeline else "?"

    # En-tête de période (mois/an)
    period_start = date_start[:7].replace("-", "-")
    period_end = date_end[:7].replace("-", "-")

    lines: list[str] = []
    lines.append(f"Progression {', '.join(ids_to_show)} — {period_start} → {period_end}")
    lines.append("")

    # Largeur max du libellé de conjecture
    label_width = max(len(cid) for cid in ids_to_show) + 2

    for cid in ids_to_show:
        scores_seq = [point["scores"].get(cid) for point in timeline]
        # Remplir les valeurs manquantes par propagation vers l'avant
        filled: list[int] = []
        last_known: int | None = None
        for s in scores_seq:
            if s is not None:
                last_known = s
            filled.append(last_known if last_known is not None else 0)

        if not filled:
            continue

        first_val = filled[0]
        last_val = filled[-1]
        delta = last_val - first_val

        # Construire la chaîne de scores séparés par "─"
        chain = "─".join(str(v) for v in filled)

        # Déterminer le statut ACTIVE depuis le dernier point
        last_status = ""
        for point in reversed(timeline):
            if cid in point["scores"]:
                break

        label = f"{cid:<{label_width}}"
        delta_str = f"+{delta}" if delta >= 0 else str(delta)
        lines.append(f"{label}{chain}   ({first_val}→{last_val}, {delta_str})")

    lines.append("")
    n_commits = len(timeline)
    lines.append(
        f"Commits analysés : {n_commits} · du {date_start} au {date_end}"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Export JSON
# ---------------------------------------------------------------------------

def _format_json(timeline: list[dict], conjecture_filter: str | None = None) -> str:
    if conjecture_filter:
        cid = conjecture_filter.upper()
        filtered = [
            {
                "date": point["date"],
                "hash": point["hash"],
                "score": point["scores"].get(cid),
            }
            for point in timeline
            if cid in point["scores"]
        ]
        payload = {
            "conjecture": cid,
            "commits_count": len(filtered),
            "history": filtered,
        }
    else:
        payload = {
            "commits_count": len(timeline),
            "history": timeline,
        }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Export matplotlib (optionnel)
# ---------------------------------------------------------------------------

def _plot_matplotlib(
    timeline: list[dict],
    conjecture_filter: str | None,
    output_dir: Path,
) -> str:
    """Génère un PNG dans output_dir et retourne le chemin."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # backend non interactif
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        return ""

    all_ids: set[str] = set()
    for point in timeline:
        all_ids.update(point["scores"].keys())

    ids_to_show = (
        [conjecture_filter.upper()]
        if conjecture_filter and conjecture_filter.upper() in all_ids
        else sorted(all_ids)
    )

    # Construire les séries temporelles
    dates_parsed: list[datetime] = []
    for point in timeline:
        try:
            dates_parsed.append(datetime.strptime(point["date"], "%Y-%m-%d"))
        except ValueError:
            dates_parsed.append(datetime.now())

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.set_title("AEGIS — Progression des conjectures C1-C7", fontsize=13)
    ax.set_xlabel("Date")
    ax.set_ylabel("Score /10")
    ax.set_ylim(0, 10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha="right")

    for cid in ids_to_show:
        scores_seq = []
        dates_seq = []
        last_known: int | None = None
        for i, point in enumerate(timeline):
            s = point["scores"].get(cid)
            if s is not None:
                last_known = s
            if last_known is not None:
                scores_seq.append(last_known)
                dates_seq.append(dates_parsed[i])
        if scores_seq:
            ax.plot(dates_seq, scores_seq, marker="o", markersize=4, label=cid, linewidth=1.5)

    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    output_dir.mkdir(parents=True, exist_ok=True)
    date_tag = datetime.now().strftime("%Y-%m-%d")
    outfile = output_dir / f"progression_curve_{date_tag}.png"
    fig.savefig(str(outfile), dpi=150)
    plt.close(fig)
    return str(outfile)


# ---------------------------------------------------------------------------
# Entrée principale
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tracer l'évolution temporelle des scores C1-C7 — AEGIS."
    )
    parser.add_argument(
        "--conjecture",
        metavar="Cn",
        help="Filtrer sur une seule conjecture (ex: C3)",
    )
    parser.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Ne montrer que les commits depuis cette date",
    )
    parser.add_argument(
        "--matplotlib",
        action="store_true",
        dest="use_matplotlib",
        help="Générer un PNG (si matplotlib est installé, sinon fallback ASCII)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Export JSON au lieu du chart",
    )
    args = parser.parse_args()

    # --- Vérifications préalables ---

    if not _check_git_available():
        print(
            "Erreur : git n'est pas disponible dans le PATH.\n"
            "Installe git ou ajoute-le à la variable PATH pour utiliser ce script.",
            file=sys.stderr,
        )
        sys.exit(1)

    repo_root = _get_repo_root()
    if repo_root is None:
        print(
            f"Erreur : {CONJECTURES_FILE} n'est pas dans un dépôt git "
            "(ou git rev-parse a échoué).\n"
            "Initialise un dépôt git à la racine du projet pour activer le suivi.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not CONJECTURES_FILE.exists():
        print(
            f"Erreur : fichier introuvable — {CONJECTURES_FILE}\n"
            "La phase OPEN doit avoir écrit ce fichier avant d'utiliser ce script.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Chemin relatif au repo root (compatible Windows et Unix)
    try:
        rel_path = CONJECTURES_FILE.relative_to(repo_root).as_posix()
    except ValueError:
        # CONJECTURES_FILE est hors du repo_root (cas improbable)
        rel_path = str(CONJECTURES_FILE)

    # --- Récupération de l'historique ---

    commits = _get_commit_history(repo_root, rel_path)
    if not commits:
        print(
            f"Aucun commit trouvé pour {rel_path}.\n"
            "Assure-toi que le fichier a déjà été commité au moins une fois.",
            file=sys.stderr,
        )
        sys.exit(0)

    # --- Construction de la timeline ---

    timeline = _build_timeline(repo_root, rel_path, commits, since=args.since)

    # --- Sortie ---

    if args.as_json:
        print(_format_json(timeline, conjecture_filter=args.conjecture))
        return

    if args.use_matplotlib:
        outfile = _plot_matplotlib(timeline, args.conjecture, STAGING_DIR)
        if outfile:
            print(f"PNG généré : {outfile}")
            return
        else:
            print(
                "matplotlib non installé ou erreur de rendu — "
                "fallback sur le chart ASCII.\n",
                file=sys.stderr,
            )

    # ASCII chart (défaut ou fallback)
    print(_ascii_chart(timeline, conjecture_filter=args.conjecture))


if __name__ == "__main__":
    main()
