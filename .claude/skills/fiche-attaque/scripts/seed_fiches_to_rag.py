"""
Seed completed Fiche d'Attaque documents into ChromaDB for cross-referencing.

Indexes structured summaries of completed fiches into the aegis_corpus collection,
allowing future fiches to cross-reference previous analyses.

Usage:
    python seed_fiches_to_rag.py                   # Seed all done fiches
    python seed_fiches_to_rag.py --template 13     # Seed specific template
    python seed_fiches_to_rag.py --dry-run          # Show what would be seeded
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
CHROMA_DB_PATH = PROJECT_ROOT / "backend" / "chroma_db"
PROMPTS_DIR = PROJECT_ROOT / "backend" / "prompts"
INDEX_PATH = PROJECT_ROOT / "research_archive" / "doc_references" / "prompt_analysis" / "fiche_index.json"
COLLECTION_NAME = "aegis_corpus"
BIBLIOGRAPHY_COLLECTION = "aegis_bibliography"

# Chunking params (matching seed_rag.py)
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


def get_client():
    """Get ChromaDB PersistentClient."""
    try:
        import chromadb
    except ImportError:
        print("ERROR: chromadb not installed. Run: pip install chromadb")
        sys.exit(1)
    return chromadb.PersistentClient(path=str(CHROMA_DB_PATH))


def chunk_text(text: str) -> list:
    """Split text into chunks with overlap, matching seed_rag.py strategy."""
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP
    return chunks


def deterministic_id(template_num: str, chunk_index: int) -> str:
    """Generate deterministic ID for idempotent upserts."""
    raw = f"fiche_attaque_{template_num}_chunk_{chunk_index}"
    return "fiche_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_fiche_summary(num_str: str, entry: dict, md_content: str = "") -> str:
    """Build a structured French summary for ChromaDB indexing."""
    name = entry.get("name", "Unknown")
    target_delta = entry.get("target_delta", "-")
    conjecture = entry.get("conjecture", "-")
    svc = entry.get("svc_score", "-")
    asr = entry.get("asr", "-")
    sep_valid = entry.get("sep_m_valid", False)
    date = entry.get("date", "-")
    notes = entry.get("notes", "")

    summary = (
        f"Fiche d'Attaque #{num_str} -- {name}\n"
        f"Categorie: {entry.get('category', '-')} | "
        f"Couche ciblee: {target_delta} | "
        f"Conjecture: {conjecture}\n"
        f"SVC: {svc} | ASR: {asr} | "
        f"Sep(M) valide: {'oui' if sep_valid else 'non'}\n"
        f"Date: {date}\n"
        f"Notes: {notes}\n"
    )

    # Add first 500 chars of .md analysis if available
    if md_content:
        summary += f"\nAnalyse (extrait):\n{md_content[:500]}\n"

    return summary


def find_md_for_template(num_str: str) -> str:
    """Try to find and read the .md analysis file for a template."""
    try:
        num = int(num_str)
        pattern = f"{num:02d}-*.md"
    except ValueError:
        # Non-numeric like "C1"
        return ""

    md_files = list(PROMPTS_DIR.glob(pattern))
    if md_files:
        try:
            return md_files[0].read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


def seed_fiche(num_str: str, entry: dict, collection, dry_run: bool = False) -> int:
    """Seed one fiche into ChromaDB. Returns number of chunks seeded."""
    md_content = find_md_for_template(num_str)
    summary = build_fiche_summary(num_str, entry, md_content)
    chunks = chunk_text(summary)

    if dry_run:
        print(f"  #{num_str}: {entry.get('name', '?')} — {len(chunks)} chunk(s), "
              f"{len(summary)} chars")
        return len(chunks)

    ids = []
    documents = []
    metadatas = []

    for i, chunk in enumerate(chunks):
        chunk_id = deterministic_id(num_str, i)
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "doc_type": "fiche_attaque",
            "template_num": num_str,
            "template_id": entry.get("name", f"template_{num_str}"),
            "svc_score": str(entry.get("svc_score", "-")),
            "target_delta": entry.get("target_delta", "-"),
            "conjecture": entry.get("conjecture", "-"),
            "asr": str(entry.get("asr", "-")),
            "date": entry.get("date", ""),
            "source": f"fiche_attaque_{num_str}",
            "chunk_index": i,
            "ingested_at": datetime.now(tz=None).isoformat(),
        })

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(chunks)


def seed_all(specific_template: str = None, dry_run: bool = False,
             also_bibliography: bool = False):
    """Seed all completed fiches (or one specific) into ChromaDB."""
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    if not dry_run:
        client = get_client()
        collection = client.get_or_create_collection(COLLECTION_NAME)
        bib_collection = client.get_or_create_collection(BIBLIOGRAPHY_COLLECTION) if also_bibliography else None
    else:
        collection = None
        bib_collection = None

    total_chunks = 0
    total_fiches = 0

    for num_str, entry in sorted(index.get("fiches", {}).items()):
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != "done":
            continue
        if specific_template and num_str != specific_template:
            continue

        chunks = seed_fiche(num_str, entry, collection, dry_run)
        if bib_collection and not dry_run:
            seed_fiche(num_str, entry, bib_collection, dry_run)
        total_chunks += chunks
        total_fiches += 1

    collections_str = COLLECTION_NAME
    if also_bibliography:
        collections_str += " + " + BIBLIOGRAPHY_COLLECTION
    action = "Would seed" if dry_run else "Seeded"
    print(f"\n{action}: {total_fiches} fiche(s), {total_chunks} chunk(s) "
          f"into collection(s) '{collections_str}'")

    # HOOK: Signal au SCIENTIST que du nouveau contenu a ete seede
    if not dry_run and total_fiches > 0:
        _signal_scientist(total_fiches, specific_template)


def _signal_scientist(n_fiches: int, template: str = None):
    """Ecrit un signal pour que le SCIENTIST sache qu'il doit produire une note."""
    signal_dir = PROJECT_ROOT / "research_archive" / "_staging" / "scientist"
    signal_dir.mkdir(parents=True, exist_ok=True)
    signal_file = signal_dir / "PENDING_SCIENTIST_REVIEW.md"

    timestamp = datetime.now(tz=None).isoformat(timespec="seconds")
    template_str = f"template {template}" if template else f"{n_fiches} fiches"

    # Append au fichier signal (ne pas ecraser les signaux precedents non traites)
    with open(signal_file, "a", encoding="utf-8") as f:
        f.write(f"- [{timestamp}] {template_str} seede(s) dans ChromaDB — NOTE SCIENTIST REQUISE\n")

    print(f"HOOK: Signal SCIENTIST ecrit dans {signal_file}")


def main():
    parser = argparse.ArgumentParser(description="Seed fiches into ChromaDB")
    parser.add_argument("--template", type=str, default=None,
                        help="Specific template number to seed (e.g., 13, C1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be seeded without writing")
    parser.add_argument("--also-bibliography", action="store_true",
                        help="Also seed into aegis_bibliography for bibliography-maintainer")
    args = parser.parse_args()

    seed_all(args.template, args.dry_run, args.also_bibliography)


if __name__ == "__main__":
    main()
