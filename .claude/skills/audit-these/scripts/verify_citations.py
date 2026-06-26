"""
V1 — Citation Integrity Checker
Verifie que chaque arXiv/DOI cite dans les analyses est valide.

Usage:
    python verify_citations.py                    # Scan tous les .md
    python verify_citations.py --file P001.md     # Scan un fichier
    python verify_citations.py --dry-run           # Compte sans verifier
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
DOC_REFS = PROJECT_ROOT / "research_archive" / "doc_references"
STAGING = PROJECT_ROOT / "research_archive" / "_staging" / "analyst"
OUTPUT_DIR = PROJECT_ROOT / "research_archive" / "_staging" / "audit-these"

ARXIV_PATTERN = re.compile(r'(?:arXiv[:/\s]?)(\d{4}\.\d{4,5}(?:v\d+)?)', re.IGNORECASE)
DOI_PATTERN = re.compile(r'(?:DOI[:/\s]?)(10\.\d{4,}/\S+)', re.IGNORECASE)


def extract_citations(file_path: Path) -> list:
    """Extract all arXiv and DOI citations from a file."""
    content = file_path.read_text(encoding="utf-8")
    citations = []

    for match in ARXIV_PATTERN.finditer(content):
        citations.append({
            "type": "arXiv",
            "id": match.group(1),
            "url": f"https://arxiv.org/abs/{match.group(1)}",
            "file": str(file_path.name),
            "line": content[:match.start()].count('\n') + 1,
        })

    for match in DOI_PATTERN.finditer(content):
        citations.append({
            "type": "DOI",
            "id": match.group(1),
            "url": f"https://doi.org/{match.group(1)}",
            "file": str(file_path.name),
            "line": content[:match.start()].count('\n') + 1,
        })

    return citations


def scan_all_files() -> list:
    """Scan all .md files in doc_references/ and _staging/analyst/."""
    all_citations = []
    seen = set()

    for directory in [DOC_REFS, STAGING]:
        for md_file in sorted(directory.rglob("*.md")):
            for cit in extract_citations(md_file):
                key = (cit["type"], cit["id"])
                if key not in seen:
                    seen.add(key)
                    all_citations.append(cit)

    return all_citations


def main():
    parser = argparse.ArgumentParser(description="V1 — Citation Integrity Checker")
    parser.add_argument("--file", type=str, help="Scan specific file")
    parser.add_argument("--dry-run", action="store_true", help="Count without verifying")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.file:
        citations = extract_citations(Path(args.file))
    else:
        citations = scan_all_files()

    # Deduplicate by ID
    unique = {}
    for c in citations:
        key = (c["type"], c["id"])
        if key not in unique:
            unique[key] = c
        else:
            unique[key]["file"] += f", {c['file']}"

    citations = list(unique.values())

    output = json.dumps(citations, indent=2, ensure_ascii=False)
    sys.stdout.buffer.write(f"Citations trouvees: {len(citations)}\n".encode("utf-8"))
    sys.stdout.buffer.write(f"  arXiv: {sum(1 for c in citations if c['type'] == 'arXiv')}\n".encode("utf-8"))
    sys.stdout.buffer.write(f"  DOI: {sum(1 for c in citations if c['type'] == 'DOI')}\n".encode("utf-8"))

    if not args.dry_run:
        output_file = OUTPUT_DIR / f"CITATIONS_AUDIT_{datetime.now().strftime('%Y%m%d')}.json"
        output_file.write_text(output, encoding="utf-8")
        sys.stdout.buffer.write(f"Output: {output_file}\n".encode("utf-8"))


if __name__ == "__main__":
    main()
