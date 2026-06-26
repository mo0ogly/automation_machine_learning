"""
ChromaDB query helper for the SCIENTIST agent.

Queries the aegis_corpus collection (or any named collection) and returns
results as JSON to stdout, ready for agent consumption.

Usage:
    python query_chromadb.py "FDA protocol tool hijack" --n 5
    python query_chromadb.py "homoglyph" "unicode evasion" --n 3 --doc-type reference
    python query_chromadb.py "fiche attaque" --doc-type fiche_attaque --collection aegis_corpus
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
CHROMA_DB_PATH = PROJECT_ROOT / "backend" / "chroma_db"
DEFAULT_COLLECTION = "aegis_corpus"
BIBLIOGRAPHY_COLLECTION = "aegis_bibliography"


def get_client():
    """Get ChromaDB client — PersistentClient first, HttpClient fallback."""
    try:
        import chromadb
    except ImportError:
        print(json.dumps({"error": "chromadb not installed. Run: pip install chromadb"}))
        sys.exit(1)

    # PersistentClient first (always available locally)
    try:
        return chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    except Exception:
        pass

    # HttpClient fallback
    try:
        return chromadb.HttpClient(host="localhost", port=8000)
    except Exception as e:
        print(json.dumps({"error": f"Cannot connect to ChromaDB: {e}"}))
        sys.exit(1)


def query_collection(queries: list, collection_name: str = DEFAULT_COLLECTION,
                     n_results: int = 5, doc_type_filter: str = None) -> dict:
    """Query ChromaDB collection with multiple queries, merge and dedup results."""
    client = get_client()

    try:
        collection = client.get_collection(collection_name)
    except Exception:
        return {
            "collection": collection_name,
            "error": f"Collection '{collection_name}' not found",
            "available_collections": [c.name for c in client.list_collections()],
            "results": [],
        }

    all_results = []
    seen_ids = set()

    for query in queries:
        try:
            # Build where filter for doc_type if specified
            where_filter = None
            if doc_type_filter:
                where_filter = {"doc_type": doc_type_filter}

            results = collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
                where=where_filter,
            )

            if results and results["ids"] and results["ids"][0]:
                for i, doc_id in enumerate(results["ids"][0]):
                    if doc_id not in seen_ids:
                        seen_ids.add(doc_id)
                        doc_text = results["documents"][0][i] if results["documents"] else ""
                        meta = results["metadatas"][0][i] if results["metadatas"] else {}
                        dist = results["distances"][0][i] if results["distances"] else None

                        all_results.append({
                            "id": doc_id,
                            "document": doc_text[:500] if doc_text else "",
                            "metadata": meta,
                            "distance": round(dist, 4) if dist is not None else None,
                            "query_source": query,
                        })
        except Exception as e:
            all_results.append({
                "id": None,
                "error": str(e),
                "query_source": query,
            })

    # Sort by distance (lower = more relevant)
    all_results.sort(key=lambda r: r.get("distance", 999) if r.get("distance") is not None else 999)

    return {
        "collection": collection_name,
        "query_count": len(queries),
        "total_results": len(all_results),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "results": all_results,
    }


def query_multi_collection(queries: list, n_results: int = 5,
                           doc_type_filter: str = None) -> dict:
    """Query both aegis_corpus AND aegis_bibliography, merge and dedup."""
    collections = [DEFAULT_COLLECTION, BIBLIOGRAPHY_COLLECTION]
    all_results = []
    seen_ids = set()
    errors = []

    for coll_name in collections:
        result = query_collection(queries, coll_name, n_results, doc_type_filter)
        if "error" in result:
            errors.append({"collection": coll_name, "error": result["error"]})
            continue
        for r in result.get("results", []):
            if r.get("id") and r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                r["collection_source"] = coll_name
                all_results.append(r)

    all_results.sort(key=lambda r: r.get("distance", 999) if r.get("distance") is not None else 999)

    return {
        "collections": collections,
        "mode": "multi-collection",
        "query_count": len(queries),
        "total_results": len(all_results),
        "errors": errors if errors else None,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "results": all_results[:n_results * 2],  # Cap at 2x n_results across both
    }


def main():
    parser = argparse.ArgumentParser(description="Query ChromaDB for SCIENTIST agent")
    parser.add_argument("queries", nargs="+", help="Search queries (multiple for broader recall)")
    parser.add_argument("--n", type=int, default=5, help="Number of results per query")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Collection name")
    parser.add_argument("--doc-type", default=None, help="Filter by doc_type metadata")
    parser.add_argument("--multi-collection", action="store_true",
                        help="Query aegis_corpus + aegis_bibliography simultaneously")
    args = parser.parse_args()

    if args.multi_collection:
        result = query_multi_collection(args.queries, args.n, args.doc_type)
    else:
        result = query_collection(args.queries, args.collection, args.n, args.doc_type)
    output = json.dumps(result, indent=2, ensure_ascii=False)
    sys.stdout.buffer.write(output.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
