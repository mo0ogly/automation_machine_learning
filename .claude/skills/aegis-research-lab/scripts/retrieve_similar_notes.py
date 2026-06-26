#!/usr/bin/env python3
"""Recherche par similarité dans aegis_research_notes (Phase DISCOVER).

Inspiré d'agentRxiv : avant de lancer une expérimentation, on interroge
les sessions passées pour savoir si un résultat pertinent existe déjà.
Permet l'apprentissage cumulatif entre sessions.

Embeddings : chromadb.DefaultEmbeddingFunction() — all-MiniLM-L6-v2 local.
Aucune clé API, aucun token consommé.

Usage:
    python retrieve_similar_notes.py "prompt injection sur vision-language"
    python retrieve_similar_notes.py --query "ASR baseline defense" --top-k 5
    python retrieve_similar_notes.py --conjecture C3 --top-k 10
    python retrieve_similar_notes.py --gap G-037
    python retrieve_similar_notes.py --json "hypothesis drift detection"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows cp1252 fallback : forcer UTF-8 sur stdout/stderr si possible
# (évite UnicodeEncodeError sur les caractères comme → ou «)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).parent.parent.parent.parent.parent
CHROMA_DIR = ROOT / "backend" / "chroma_db"
COLLECTION_NAME = "aegis_research_notes"


def _get_collection():
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    emb_fn = embedding_functions.DefaultEmbeddingFunction()

    try:
        return client.get_collection(name=COLLECTION_NAME, embedding_function=emb_fn)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: collection '{COLLECTION_NAME}' not found. "
              f"Run ingest_research_note.py --all first. ({e})",
              file=sys.stderr)
        sys.exit(2)


def retrieve(
    query: str,
    top_k: int = 5,
    conjecture: str | None = None,
    gap: str | None = None,
    session: str | None = None,
    high_priority_only: bool = False,
) -> list[dict]:
    """Retourne les top-K chunks similaires au query, avec filtres optionnels."""
    collection = _get_collection()

    # ChromaDB where filter (AND logique)
    where: dict = {}
    if conjecture:
        where["conjectures_csv"] = {"$contains": conjecture}
    if gap:
        where["gaps_csv"] = {"$contains": gap}
    if session:
        where["session_id"] = session
    if high_priority_only:
        where["high_priority"] = True

    # Nettoyer : $contains n'est pas supporté par metadata where,
    # on le gère en post-filtre côté client
    safe_where = {k: v for k, v in where.items() if not isinstance(v, dict)}
    chroma_where = None
    if safe_where:
        chroma_where = safe_where if len(safe_where) == 1 else {"$and": [{k: v} for k, v in safe_where.items()]}

    # Si query vide + au moins un filtre → utiliser get() (sans similarité),
    # sinon query() avec similarité sémantique.
    if not query and where:
        get_kwargs = {"limit": top_k * 3, "include": ["documents", "metadatas"]}
        if chroma_where:
            get_kwargs["where"] = chroma_where
        raw = collection.get(**get_kwargs)
        ids = raw.get("ids", []) or []
        docs = raw.get("documents", []) or []
        metas = raw.get("metadatas", []) or []
        dists = [0.0] * len(ids)  # pas de distance en mode get
    else:
        query_kwargs = {
            "query_texts": [query] if query else [""],
            "n_results": top_k,
        }
        if chroma_where:
            query_kwargs["where"] = chroma_where
        results = collection.query(**query_kwargs)
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

    # Reformater
    hits = []

    for i, cid in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        dist = dists[i] if i < len(dists) else 1.0
        similarity = round(1.0 - dist, 4)  # cosine distance → similarity
        # Post-filtre $contains
        if conjecture and conjecture not in (meta.get("conjectures_csv") or ""):
            continue
        if gap and gap not in (meta.get("gaps_csv") or ""):
            continue
        hits.append({
            "chunk_id": cid,
            "similarity": similarity,
            "session_id": meta.get("session_id"),
            "date": meta.get("date"),
            "section": f"§{meta.get('section_num', '?')} {meta.get('section_title', '')}".strip(),
            "high_priority": meta.get("high_priority", False),
            "conjectures": (meta.get("conjectures_csv") or "").split(",") if meta.get("conjectures_csv") else [],
            "gaps": (meta.get("gaps_csv") or "").split(",") if meta.get("gaps_csv") else [],
            "source_file": meta.get("source_file"),
            "excerpt": (docs[i] if i < len(docs) else "")[:500],
        })

    return hits


def format_markdown(hits: list[dict], query: str) -> str:
    lines = []
    lines.append(f"== Recherche : \"{query}\" ==")
    lines.append(f"({len(hits)} résultats)\n")

    if not hits:
        lines.append("(aucun résultat — la collection est peut-être vide ou les filtres sont trop stricts)")
        return "\n".join(lines)

    for i, h in enumerate(hits, 1):
        hp_tag = " [HIGH PRIORITY]" if h["high_priority"] else ""
        conj = ",".join(h["conjectures"]) or "-"
        gaps = ",".join(h["gaps"][:3]) or "-"
        lines.append(f"#{i} sim={h['similarity']:.3f}  {h['session_id']} ({h['date']}){hp_tag}")
        lines.append(f"    {h['section']}")
        lines.append(f"    conj={conj}  gaps={gaps}")
        lines.append(f"    → {h['source_file']}")
        excerpt = h["excerpt"].replace("\n", " ")[:300]
        lines.append(f"    « {excerpt}... »")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve similar research notes from ChromaDB by semantic similarity."
    )
    parser.add_argument("query", nargs="?", default="",
                        help="Natural language query")
    parser.add_argument("--query", dest="query_flag",
                        help="Alternative way to pass the query")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Number of results (default 5)")
    parser.add_argument("--conjecture", help="Filter by conjecture (e.g. C3)")
    parser.add_argument("--gap", help="Filter by gap ID (e.g. G-037)")
    parser.add_argument("--session", help="Filter by session ID")
    parser.add_argument("--high-priority", action="store_true",
                        help="Return only §5/§8/§10 chunks")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    query = args.query_flag or args.query
    if not query and not (args.conjecture or args.gap or args.session):
        parser.error("Provide a query string or at least one of --conjecture/--gap/--session")

    hits = retrieve(
        query=query,
        top_k=args.top_k,
        conjecture=args.conjecture,
        gap=args.gap,
        session=args.session,
        high_priority_only=args.high_priority,
    )

    if args.json:
        print(json.dumps({"query": query, "hits": hits}, indent=2, ensure_ascii=False))
    else:
        print(format_markdown(hits, query or f"{args.conjecture or ''} {args.gap or ''}".strip()))

    sys.exit(0 if hits else 1)


if __name__ == "__main__":
    main()
