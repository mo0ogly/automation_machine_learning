#!/usr/bin/env python3
"""Ingest une note de recherche dans ChromaDB (collection aegis_research_notes).

Inspiré d'agentRxiv (arXiv 2503.18102) : permet aux sessions futures de
retrouver par similarité sémantique les notes pertinentes avant de relancer
une expérimentation, pour construire un apprentissage cumulatif.

Embeddings : chromadb.DefaultEmbeddingFunction() — all-MiniLM-L6-v2 local.
Aucune clé API, aucun token consommé.

Usage:
    python ingest_research_note.py SESSION-043_2026-04-05.md
    python ingest_research_note.py research_archive/research_notes/SESSION-043*.md
    python ingest_research_note.py --all            # ré-indexe toutes les notes
    python ingest_research_note.py --dry-run note.md

Structure des chunks :
    Chaque note est découpée par section (§1-§12). Chaque chunk hérite du
    frontmatter (session_id, date, conjectures, gaps). Les §5 (résultats),
    §8 (conclusions) et §10 (prochaines étapes) sont marqués high_priority.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent.parent  # poc_medical/
RESEARCH_NOTES = ROOT / "research_archive" / "research_notes"
CHROMA_DIR = ROOT / "backend" / "chroma_db"
COLLECTION_NAME = "aegis_research_notes"

# Sections à marquer high_priority pour la recherche par similarité
HIGH_PRIORITY_SECTIONS = {"5", "8", "10"}

# Pattern de découpage des sections : "## 3. Titre" ou "## §3 Titre"
SECTION_PATTERN = re.compile(
    r"^##\s*(?:§\s*)?(\d+)[.\s]\s*(.+?)$",
    re.MULTILINE,
)

# Pattern frontmatter YAML
FRONTMATTER_PATTERN = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extrait le frontmatter YAML simple en dict + retourne le corps."""
    m = FRONTMATTER_PATTERN.match(text)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = text[m.end():]
    meta = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"\'')
    return meta, body


def _extract_conjectures_mentioned(text: str) -> list[str]:
    """Trouve les conjectures C1-C10 citées dans le texte."""
    return sorted(set(re.findall(r"\bC\d+\b", text)))


def _extract_gaps_mentioned(text: str) -> list[str]:
    """Trouve les G-XXX cités dans le texte."""
    return sorted(set(re.findall(r"\bG-\d{3}\b", text)))


def _extract_sessions_cited(text: str) -> list[str]:
    """Trouve les SESSION-XXX citées (pour cross-citation Option D)."""
    return sorted(set(re.findall(r"\bSESSION-\d{3}\b", text)))


def _chunk_by_section(body: str) -> list[dict]:
    """Découpe le corps en chunks section-par-section."""
    chunks = []
    matches = list(SECTION_PATTERN.finditer(body))
    if not matches:
        # Pas de sections numérotées → un seul chunk
        chunks.append({
            "section_num": "0",
            "section_title": "full",
            "text": body.strip(),
        })
        return chunks

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_num = m.group(1)
        section_title = m.group(2).strip()
        chunk_text = body[start:end].strip()
        if len(chunk_text) < 50:  # trop court, on skip
            continue
        chunks.append({
            "section_num": section_num,
            "section_title": section_title,
            "text": chunk_text,
        })
    return chunks


def _chunk_id(session_id: str, section_num: str) -> str:
    """ID déterministe pour un chunk (permet ré-indexation idempotente)."""
    raw = f"{session_id}::{section_num}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def parse_note(path: Path) -> dict:
    """Parse une note complète en metadata + chunks."""
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    # Deviner le session_id depuis le frontmatter ou le nom de fichier
    session_id = meta.get("session_id")
    if not session_id:
        m = re.search(r"(SESSION-\d+)", path.name)
        session_id = m.group(1) if m else path.stem

    # Date : frontmatter ou mtime
    date = meta.get("date")
    if not date:
        date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")

    # Enrichissement global
    conjectures = _extract_conjectures_mentioned(body)
    gaps = _extract_gaps_mentioned(body)
    sessions_cited = _extract_sessions_cited(body)

    chunks = _chunk_by_section(body)
    for c in chunks:
        c["chunk_id"] = _chunk_id(session_id, c["section_num"])
        c["high_priority"] = c["section_num"] in HIGH_PRIORITY_SECTIONS

    return {
        "session_id": session_id,
        "date": date,
        "source_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "conjectures": conjectures,
        "gaps": gaps,
        "sessions_cited": sessions_cited,
        "chunks": chunks,
    }


def _get_collection():
    """Récupère (ou crée) la collection ChromaDB aegis_research_notes."""
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    emb_fn = embedding_functions.DefaultEmbeddingFunction()  # all-MiniLM-L6-v2 local

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"},
    )


def ingest(path: Path, collection, dry_run: bool = False) -> dict:
    """Ingère une note dans la collection. Retourne un résumé."""
    parsed = parse_note(path)

    ids = []
    docs = []
    metadatas = []
    for c in parsed["chunks"]:
        ids.append(c["chunk_id"])
        docs.append(c["text"])
        metadatas.append({
            "session_id": parsed["session_id"],
            "date": parsed["date"],
            "source_file": parsed["source_file"],
            "section_num": c["section_num"],
            "section_title": c["section_title"],
            "high_priority": c["high_priority"],
            # Listes converties en CSV car ChromaDB ne supporte que scalaires
            "conjectures_csv": ",".join(parsed["conjectures"]),
            "gaps_csv": ",".join(parsed["gaps"]),
            "sessions_cited_csv": ",".join(parsed["sessions_cited"]),
        })

    summary = {
        "session_id": parsed["session_id"],
        "date": parsed["date"],
        "file": parsed["source_file"],
        "chunks_total": len(parsed["chunks"]),
        "chunks_high_priority": sum(1 for c in parsed["chunks"] if c["high_priority"]),
        "conjectures": parsed["conjectures"],
        "gaps": parsed["gaps"],
        "sessions_cited": parsed["sessions_cited"],
        "dry_run": dry_run,
    }

    if dry_run:
        return summary

    if ids:
        # upsert = ré-indexation idempotente (même session_id → même chunk_ids)
        collection.upsert(ids=ids, documents=docs, metadatas=metadatas)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Ingest research notes into ChromaDB aegis_research_notes collection."
    )
    parser.add_argument("paths", nargs="*", help="Note file(s) to ingest")
    parser.add_argument("--all", action="store_true",
                        help="Re-index all notes in research_archive/research_notes/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and show summary without writing to ChromaDB")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Print only errors")
    args = parser.parse_args()

    # Résoudre la liste de fichiers
    files: list[Path] = []
    if args.all:
        if not RESEARCH_NOTES.exists():
            print(f"ERROR: {RESEARCH_NOTES} does not exist", file=sys.stderr)
            sys.exit(1)
        files = sorted(RESEARCH_NOTES.glob("SESSION-*.md"))
    else:
        for p in args.paths:
            path = Path(p)
            if not path.is_absolute():
                # Essai direct, puis research_notes/
                if path.exists():
                    pass
                elif (RESEARCH_NOTES / path).exists():
                    path = RESEARCH_NOTES / path
                else:
                    # Glob support
                    matches = list(Path(".").glob(p))
                    if not matches:
                        matches = list(RESEARCH_NOTES.glob(p))
                    if matches:
                        files.extend(matches)
                        continue
            files.append(path)

    if not files:
        print("No files to ingest. Use --all or pass one or more paths.", file=sys.stderr)
        sys.exit(1)

    # Charger la collection (une seule fois)
    collection = None
    if not args.dry_run:
        try:
            collection = _get_collection()
        except ImportError as e:
            print(f"ERROR: chromadb not installed ({e}). pip install chromadb",
                  file=sys.stderr)
            sys.exit(2)

    total_chunks = 0
    errors = 0
    for f in files:
        if not f.exists():
            print(f"SKIP  {f} (not found)", file=sys.stderr)
            errors += 1
            continue
        try:
            summary = ingest(f, collection, dry_run=args.dry_run)
            total_chunks += summary["chunks_total"]
            if not args.quiet:
                tag = "[DRY]" if args.dry_run else "[OK] "
                print(f"{tag} {summary['session_id']:20s} "
                      f"chunks={summary['chunks_total']:2d} "
                      f"high_priority={summary['chunks_high_priority']:2d} "
                      f"conj={','.join(summary['conjectures']) or '-':10s} "
                      f"gaps={len(summary['gaps'])}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {f.name}: {e}", file=sys.stderr)
            errors += 1

    if not args.quiet:
        action = "Parsed" if args.dry_run else "Ingested"
        print(f"\n{action} {len(files) - errors}/{len(files)} notes, "
              f"{total_chunks} chunks total.")
        if not args.dry_run:
            print(f"Collection: {COLLECTION_NAME} @ {CHROMA_DIR}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
