#!/usr/bin/env python3
"""Ingest une fiche de paper de methodologie (format P006) dans ChromaDB.

Collection : `aegis_methodology_papers` — separee de `aegis_bibliography`
(papers securite LLM) et de `aegis_research_notes` (notes de session). Cette
collection regroupe les papers qui fondent le chapitre "Methodologie" de la
these AEGIS (ENS, 2026) : Agent Laboratory, AI Scientist v1/v2, AI co-scientist,
ScienceAgentBench, Autonomous Agents for Scientific Discovery, Survey of AI
Scientists, Tongyi DeepResearch, Jr. AI Scientist, Securing MCP, Step DeepResearch,
SAGA, Why LLMs Aren't Scientists Yet, etc.

Source unique de verite : les fiches longues au format template P006 stockees
dans `research_archive/doc_references/{YEAR}/methodology/M*.md`. Le format P006
commence par un titre H2 `## [Authors, YEAR] — Title`, suivi de metadonnees
(`**Reference** : arXiv:XXXX`, `**Revue/Conf** : ...`, `**Lu le** : ...`) puis
d'un corps decoupe en sections H3 (`### Abstract original`, `### Resume`, ...,
`### Pertinence these AEGIS`, `### Citations cles`, `### Classification`).

Embeddings : chromadb.DefaultEmbeddingFunction() -- all-MiniLM-L6-v2 local.
Aucune cle API, aucun token consomme.

Usage:
    python ingest_methodology_paper.py --all
    python ingest_methodology_paper.py research_archive/doc_references/2025/methodology/M010_*.md
    python ingest_methodology_paper.py --all --dry-run
    python ingest_methodology_paper.py --all --quiet

Format de chunk ID :
    SHA1 court (16 car.) de "{arxiv_id}::{section_slug}".
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent.parent  # poc_medical/
DOC_REFERENCES_DIR = ROOT / "research_archive" / "doc_references"
# Glob pour atteindre tous les M*.md dans */methodology/ quel que soit YEAR
METHODOLOGY_GLOB = "*/methodology/M*.md"
CHROMA_DIR = ROOT / "backend" / "chroma_db"
COLLECTION_NAME = "aegis_methodology_papers"

# Sections P006 marquees high_priority : on normalise le titre (lowercase +
# suppression des accents) puis on teste plusieurs patterns regex. Cela tolere
# les variations redactionnelles entre fiches : "Pertinence these AEGIS" vs
# "Pertinence thèse AEGIS", "Citations cles" vs "Citations directement
# utilisables dans la these AEGIS", "Mecanismes formellement applicables dans
# AEGIS" vs "Mecanismes repris dans AEGIS".
HIGH_PRIORITY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"pertinence.*aegis"),
    re.compile(r"citation"),
    re.compile(r"mecanism.*aegis"),
]

# Pattern de decoupe P006 : les sections sont en H3 (### Titre)
SECTION_PATTERN = re.compile(r"^###\s+(.+?)$", re.MULTILINE)

# Parsing du header P006
# Ligne 1 : `## [Authors et al., YYYY] — Titre complet`
# On tolere les tirets em (—), en (–) et hyphen (-), et l'absence de virgule.
HEADER_TITLE_PATTERN = re.compile(
    r"^##\s+\[(?P<authors>.+?),\s*(?P<year>\d{4})\]\s*[—–-]\s*(?P<title>.+?)\s*$",
    re.MULTILINE,
)
# `**Reference** : arXiv:2501.04227v2` ou sans suffixe de version
REFERENCE_PATTERN = re.compile(
    r"^\*\*Reference\*\*\s*:\s*arXiv:(?P<arxiv_id>\d{4}\.\d{4,5})(?:v\d+)?",
    re.MULTILINE,
)
# `**Revue/Conf** : arXiv preprint cs.AI (v1 2025-10-10...)`
VENUE_PATTERN = re.compile(
    r"^\*\*Revue/Conf\*\*\s*:\s*(?P<venue>.+?)$",
    re.MULTILINE,
)

# Corps d'une section : premiere phrase non vide (utile pour relevance_to_aegis)
FIRST_PARA_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]")


# ---------------------------------------------------------------------------
# Parsing du header P006 et du corps
# ---------------------------------------------------------------------------

def _strip_accents(s: str) -> str:
    """Normalise accents et casse pour comparaison robuste."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _section_slug(title: str) -> str:
    """Slugifie un titre de section pour l'ID de chunk."""
    normalized = _strip_accents(title)
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def _is_high_priority(section_title: str) -> bool:
    """Detecte si une section P006 est high-priority.

    Normalise le titre (lowercase + suppression des accents) puis teste les
    patterns definis dans HIGH_PRIORITY_PATTERNS. Tolere les variations
    redactionnelles d'une fiche a l'autre.
    """
    normalized = _strip_accents(section_title)
    return any(p.search(normalized) for p in HIGH_PRIORITY_PATTERNS)


def _extract_header_metadata(text: str, path: Path) -> dict:
    """Extrait arxiv_id, title, authors, year, venue depuis le header P006."""
    m_title = HEADER_TITLE_PATTERN.search(text)
    if not m_title:
        raise ValueError(
            f"Header P006 introuvable dans {path.name} (ligne 1 attendue : "
            f"'## [Authors, YEAR] — Title')"
        )
    authors = m_title.group("authors").strip()
    year = int(m_title.group("year"))
    title = m_title.group("title").strip()

    m_ref = REFERENCE_PATTERN.search(text)
    if m_ref:
        arxiv_id = m_ref.group("arxiv_id")
    else:
        # Fallback : extraire depuis le nom de fichier si possible
        stem_match = re.search(r"(\d{4}\.\d{4,5})", path.name)
        arxiv_id = stem_match.group(1) if stem_match else path.stem

    m_venue = VENUE_PATTERN.search(text)
    if m_venue:
        # On garde la partie avant le premier tiret — pour compacite
        venue_raw = m_venue.group("venue").strip()
        venue = re.split(r"\s[—–-]\s", venue_raw, maxsplit=1)[0].strip()
        # Limiter la longueur pour ChromaDB metadata
        venue = venue[:200]
    else:
        venue = "arXiv"

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue,
    }


def _extract_relevance(body: str) -> str:
    """Extrait une courte phrase de relevance_to_aegis depuis 'Pertinence these AEGIS'.

    Strategie : trouver la section H3 dont le titre normalise matche
    'pertinence.*aegis' (tolerant aux accents), puis prendre la premiere phrase
    significative du contenu (hors bullets de sous-categorie en gras).
    """
    # On itere sur toutes les sections H3 pour trouver celle qui matche
    section_matches = list(SECTION_PATTERN.finditer(body))
    pattern = re.compile(r"pertinence.*aegis")
    target_start = -1
    target_end = len(body)
    for i, m in enumerate(section_matches):
        title = m.group(1).strip()
        if pattern.search(_strip_accents(title)):
            target_start = m.end()
            target_end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(body)
            break
    if target_start < 0:
        return ""
    content = body[target_start:target_end]
    # Chercher la premiere phrase significative (hors ** ou bullets)
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("**") or line.startswith("---"):
            continue
        if line.startswith("-") or line.startswith("*"):
            line = line.lstrip("-*").strip()
        # Enlever les balises markdown bold/italic
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        m_sentence = FIRST_PARA_SENTENCE_RE.search(line)
        if m_sentence:
            sentence = m_sentence.group(0).strip()
            return sentence[:500]
        if len(line) > 20:
            return line[:500]
    return ""


def _chunk_by_section(body: str) -> list[dict]:
    """Decoupe le corps en chunks section H3 par section H3 (format P006)."""
    chunks: list[dict] = []
    matches = list(SECTION_PATTERN.finditer(body))

    if not matches:
        chunks.append({
            "section_title": "full",
            "text": body.strip(),
        })
        return chunks

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_title = m.group(1).strip()
        chunk_text = body[start:end].strip()
        if len(chunk_text) < 50:  # trop court, on ignore
            continue
        chunks.append({
            "section_title": section_title,
            "text": chunk_text,
        })
    return chunks


def parse_paper(path: Path) -> dict:
    """Parse une fiche P006 en metadata + chunks ingerables."""
    text = path.read_text(encoding="utf-8")
    header = _extract_header_metadata(text, path)

    # Corps = tout le texte ; SECTION_PATTERN decoupe sur les H3 directement.
    # Le header (ligne 1 H2 + metadonnees pre-abstract) ne contient pas de H3,
    # donc il est ignore par le decoupage. Parfait.
    chunks_raw = _chunk_by_section(text)

    relevance = _extract_relevance(text)

    chunks: list[dict] = []
    for c in chunks_raw:
        high = _is_high_priority(c["section_title"])
        slug = _section_slug(c["section_title"])
        raw = f"{header['arxiv_id']}::{slug}"
        chunk_id = hashlib.sha1(raw.encode()).hexdigest()[:16]
        chunks.append({
            "section_title": c["section_title"],
            "text": c["text"],
            "chunk_id": chunk_id,
            "high_priority": high,
        })

    return {
        **header,
        "tags": [],          # pas de tags dans le format P006 — reserve pour extension future
        "tags_csv": "",
        "relevance_to_aegis": relevance,
        "source_file": str(path.relative_to(ROOT)).replace("\\", "/"),
        "chunks": chunks,
    }


# ---------------------------------------------------------------------------
# Acces ChromaDB
# ---------------------------------------------------------------------------

def _get_collection():
    """Recupere (ou cree) la collection ChromaDB aegis_methodology_papers."""
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    emb_fn = embedding_functions.DefaultEmbeddingFunction()

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=emb_fn,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Ingestion d'une fiche
# ---------------------------------------------------------------------------

def ingest(path: Path, collection, dry_run: bool = False) -> dict:
    """Ingere une fiche P006 dans la collection. Retourne un resume."""
    parsed = parse_paper(path)

    ids: list[str] = []
    docs: list[str] = []
    metadatas: list[dict] = []

    for c in parsed["chunks"]:
        ids.append(c["chunk_id"])
        docs.append(c["text"])
        metadatas.append({
            "arxiv_id": parsed["arxiv_id"],
            "title": parsed["title"],
            "authors": parsed["authors"],
            "year": parsed["year"],
            "venue": parsed["venue"],
            "tags_csv": parsed["tags_csv"],
            "relevance_to_aegis": parsed["relevance_to_aegis"],
            "source_file": parsed["source_file"],
            "section_title": c["section_title"],
            # ChromaDB ne supporte que les scalaires -> bool converti en int
            "high_priority": int(c["high_priority"]),
        })

    summary = {
        "arxiv_id": parsed["arxiv_id"],
        "title": parsed["title"],
        "year": parsed["year"],
        "file": parsed["source_file"],
        "chunks_total": len(parsed["chunks"]),
        "chunks_high_priority": sum(1 for c in parsed["chunks"] if c["high_priority"]),
        "dry_run": dry_run,
    }

    if dry_run:
        return summary

    if ids:
        collection.upsert(ids=ids, documents=docs, metadatas=metadatas)

    return summary


# ---------------------------------------------------------------------------
# Point d'entree CLI
# ---------------------------------------------------------------------------

def _discover_all() -> list[Path]:
    """Decouvre toutes les fiches P006 dans doc_references/{YEAR}/methodology/."""
    if not DOC_REFERENCES_DIR.exists():
        print(
            f"ERROR: {DOC_REFERENCES_DIR} n'existe pas.",
            file=sys.stderr,
        )
        sys.exit(1)
    return sorted(DOC_REFERENCES_DIR.glob(METHODOLOGY_GLOB))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest des fiches P006 de papers methodologie dans ChromaDB "
            "(collection aegis_methodology_papers). Source unique : "
            "research_archive/doc_references/{YEAR}/methodology/M*.md"
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Fiche(s) P006 markdown a ingerer (chemin absolu ou relatif)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Re-indexe toutes les fiches P006 trouvees dans "
            "research_archive/doc_references/{YEAR}/methodology/M*.md"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse et affiche le resume sans ecrire dans ChromaDB",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="N'affiche que les erreurs",
    )
    args = parser.parse_args()

    # Resoudre la liste des fichiers a traiter
    files: list[Path] = []
    if args.all:
        files = _discover_all()
    else:
        for p in args.paths:
            path = Path(p)
            if path.exists():
                files.append(path)
                continue
            # Support glob depuis cwd
            matches = list(Path(".").glob(p))
            if matches:
                files.extend(sorted(matches))
                continue
            print(f"SKIP  {p} (introuvable)", file=sys.stderr)

    if not files:
        print(
            "Aucun fichier a ingerer. Utilisez --all ou passez un ou plusieurs chemins.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Charger la collection une seule fois (sauf dry-run)
    collection = None
    if not args.dry_run:
        try:
            collection = _get_collection()
        except ImportError as exc:
            print(
                f"ERROR: chromadb n'est pas installe ({exc}). pip install chromadb",
                file=sys.stderr,
            )
            sys.exit(2)

    total_chunks = 0
    errors = 0

    for f in files:
        if not f.exists():
            print(f"SKIP  {f} (introuvable)", file=sys.stderr)
            errors += 1
            continue
        try:
            summary = ingest(f, collection, dry_run=args.dry_run)
            total_chunks += summary["chunks_total"]
            if not args.quiet:
                tag = "[DRY]" if args.dry_run else "[OK] "
                print(
                    f"{tag} {summary['arxiv_id']:15s} "
                    f"({summary['year']}) "
                    f"chunks={summary['chunks_total']:2d} "
                    f"high_priority={summary['chunks_high_priority']:2d} "
                    f"{f.name}"
                )
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR {f.name}: {exc}", file=sys.stderr)
            errors += 1

    if not args.quiet:
        action = "Parses" if args.dry_run else "Ingeres"
        print(
            f"\n{action} {len(files) - errors}/{len(files)} fiches, "
            f"{total_chunks} chunks au total."
        )
        if not args.dry_run:
            print(f"Collection: {COLLECTION_NAME} @ {CHROMA_DIR}")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
