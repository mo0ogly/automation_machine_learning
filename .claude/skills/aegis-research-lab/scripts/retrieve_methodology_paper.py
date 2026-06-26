#!/usr/bin/env python3
"""Recherche par similarite semantique dans aegis_methodology_papers.

Interroge la collection ChromaDB dediee aux papers de methodologie (separee
de aegis_bibliography qui est reservee aux papers securite LLM). Permet de
retrouver les chunks les plus pertinents pour un query en langage naturel,
avec filtres optionnels sur le tag, l'annee, l'arxiv_id ou la priorite.

Embeddings : chromadb.DefaultEmbeddingFunction() -- all-MiniLM-L6-v2 local.
Aucune cle API, aucun token consomme.

Usage:
    python retrieve_methodology_paper.py "hostile reviewer loop in autonomous agents"
    python retrieve_methodology_paper.py --tag review_loop --top-k 5
    python retrieve_methodology_paper.py --arxiv-id 2501.04227 --high-priority
    python retrieve_methodology_paper.py --json --year 2025 "cumulative learning"
    python retrieve_methodology_paper.py --tag autonomy --year 2025 --top-k 3
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).parent.parent.parent.parent.parent  # poc_medical/
CHROMA_DIR = ROOT / "backend" / "chroma_db"
COLLECTION_NAME = "aegis_methodology_papers"


# ---------------------------------------------------------------------------
# Acces ChromaDB
# ---------------------------------------------------------------------------

def _get_collection():
    """Recupere la collection ChromaDB aegis_methodology_papers (doit exister)."""
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    emb_fn = embedding_functions.DefaultEmbeddingFunction()

    try:
        return client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=emb_fn,
        )
    except Exception as exc:  # noqa: BLE001
        print(
            f"ERROR: collection '{COLLECTION_NAME}' introuvable. "
            f"Lancez d'abord ingest_methodology_paper.py --all. ({exc})",
            file=sys.stderr,
        )
        sys.exit(2)


# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------

def retrieve(
    query: str,
    top_k: int = 5,
    tag: str | None = None,
    year: int | None = None,
    arxiv_id: str | None = None,
    high_priority_only: bool = False,
) -> list[dict]:
    """Retourne les top-K chunks les plus proches du query, avec filtres optionnels.

    Filtres :
        tag            -- post-filtre sur le champ tags_csv (sous-chaine)
        year           -- filtre ChromaDB exact sur le champ year (int)
        arxiv_id       -- filtre ChromaDB exact sur le champ arxiv_id
        high_priority  -- filtre ChromaDB exact (high_priority == 1)

    Notes sur l'implementation :
        ChromaDB where ne supporte pas $contains sur les metadonnees ; les filtres
        tag (sous-chaine) sont appliques en post-filtre cote client. Les filtres
        exact (year, arxiv_id, high_priority) sont passes directement via where.
    """
    collection = _get_collection()

    # Construction du filtre ChromaDB (scalaires uniquement)
    safe_where: dict = {}
    if year is not None:
        safe_where["year"] = year
    if arxiv_id:
        safe_where["arxiv_id"] = arxiv_id
    if high_priority_only:
        safe_where["high_priority"] = 1  # stocke en int (voir ingest)

    chroma_where = None
    if safe_where:
        if len(safe_where) == 1:
            chroma_where = safe_where
        else:
            chroma_where = {"$and": [{k: v} for k, v in safe_where.items()]}

    # Si query vide + filtre/tag -> utiliser get() (sans similarite),
    # sinon query() avec similarite semantique.
    has_any_filter = bool(safe_where) or bool(tag)
    if not query and has_any_filter:
        get_kwargs = {"limit": max(top_k * 5, 50), "include": ["documents", "metadatas"]}
        if chroma_where:
            get_kwargs["where"] = chroma_where
        raw = collection.get(**get_kwargs)
        ids = raw.get("ids", []) or []
        docs = raw.get("documents", []) or []
        metas = raw.get("metadatas", []) or []
        dists = [0.0] * len(ids)  # pas de distance en mode get
    else:
        query_kwargs: dict = {
            "query_texts": [query] if query else ["methodology research autonomous agents"],
            "n_results": top_k,
        }
        if chroma_where:
            query_kwargs["where"] = chroma_where
        results = collection.query(**query_kwargs)
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

    hits: list[dict] = []
    for i, cid in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else 1.0
        similarity = round(1.0 - dist, 4)

        tags_csv: str = meta.get("tags_csv") or ""

        # Post-filtre tag (sous-chaine dans tags_csv)
        if tag and tag not in tags_csv:
            continue

        hits.append({
            "chunk_id": cid,
            "similarity": similarity,
            "arxiv_id": meta.get("arxiv_id", ""),
            "title": meta.get("title", ""),
            "year": meta.get("year", ""),
            "venue": meta.get("venue", ""),
            "tags_csv": tags_csv,
            "section_title": meta.get("section_title", ""),
            "high_priority": bool(meta.get("high_priority", 0)),
            "source_file": meta.get("source_file", ""),
            "excerpt": (docs[i] if i < len(docs) else "")[:500],
        })

    return hits


# ---------------------------------------------------------------------------
# Formatage de la sortie
# ---------------------------------------------------------------------------

def format_markdown(hits: list[dict], query: str) -> str:
    """Formate les resultats en markdown lisible."""
    lines: list[str] = []
    lines.append(f'== Recherche methodologie : "{query}" ==')
    lines.append(f"({len(hits)} resultats)\n")

    if not hits:
        lines.append(
            "(aucun resultat -- la collection est peut-etre vide "
            "ou les filtres sont trop stricts)"
        )
        return "\n".join(lines)

    for i, h in enumerate(hits, 1):
        hp_tag = " [HIGH PRIORITY]" if h["high_priority"] else ""
        tags_display = h["tags_csv"] or "-"
        lines.append(
            f"#{i} sim={h['similarity']:.3f}  "
            f"{h['arxiv_id']} {h['title']} ({h['year']}){hp_tag}"
        )
        lines.append(f"    §{h['section_title']}")
        lines.append(f"    tags = {tags_display}")
        lines.append(f"    -> {h['source_file']}")
        excerpt = h["excerpt"].replace("\n", " ")[:300]
        lines.append(f'    << {excerpt}... >>')
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Point d'entree CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Recherche par similarite dans aegis_methodology_papers "
            "(papers de methodologie de la these AEGIS)."
        ),
        epilog=(
            "Exemples :\n"
            '  python retrieve_methodology_paper.py "hostile reviewer loop"\n'
            "  python retrieve_methodology_paper.py --tag review_loop --top-k 5\n"
            "  python retrieve_methodology_paper.py --arxiv-id 2501.04227 --high-priority\n"
            '  python retrieve_methodology_paper.py --json --year 2025 "cumulative learning"\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Requete en langage naturel",
    )
    parser.add_argument(
        "--query",
        dest="query_flag",
        help="Alternative pour passer la requete (utile en scripting)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Nombre de resultats a retourner (defaut : 5)",
    )
    parser.add_argument(
        "--tag",
        help=(
            "Filtre par tag (ex: autonomy, review_loop, benchmarks). "
            "Post-filtre sur tags_csv."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Filtre par annee de publication (ex: 2024, 2025)",
    )
    parser.add_argument(
        "--arxiv-id",
        help="Filtre par identifiant arXiv exact (ex: 2501.04227)",
    )
    parser.add_argument(
        "--high-priority",
        action="store_true",
        help=(
            "Ne retourne que les chunks high-priority "
            "(sections 'Mecanismes repris dans AEGIS' et 'Citations utilisables')"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Sortie JSON au lieu de markdown",
    )
    args = parser.parse_args()

    query: str = args.query_flag or args.query

    # Verifier qu'il y a au moins un critere de recherche
    has_filter = any([args.tag, args.year, args.arxiv_id, args.high_priority])
    if not query and not has_filter:
        parser.error(
            "Fournissez une requete ou au moins un filtre "
            "(--tag / --year / --arxiv-id / --high-priority)"
        )

    hits = retrieve(
        query=query,
        top_k=args.top_k,
        tag=args.tag,
        year=args.year,
        arxiv_id=args.arxiv_id,
        high_priority_only=args.high_priority,
    )

    if args.json:
        print(
            json.dumps(
                {"query": query, "filters": {
                    "tag": args.tag,
                    "year": args.year,
                    "arxiv_id": args.arxiv_id,
                    "high_priority": args.high_priority,
                }, "hits": hits},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        display_query = query or " ".join(
            filter(None, [
                args.tag and f"tag:{args.tag}",
                args.year and f"year:{args.year}",
                args.arxiv_id and f"arxiv:{args.arxiv_id}",
                args.high_priority and "high-priority",
            ])
        )
        print(format_markdown(hits, display_query))

    sys.exit(0 if hits else 1)


if __name__ == "__main__":
    main()
