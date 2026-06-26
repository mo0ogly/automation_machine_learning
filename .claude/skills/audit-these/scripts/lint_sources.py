"""
V2 — Sourcing Linter
Detecte les affirmations factuelles sans reference inline.

Usage:
    python lint_sources.py                     # Scan toutes les analyses
    python lint_sources.py --file P001.md      # Scan un fichier
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
STAGING = PROJECT_ROOT / "research_archive" / "_staging" / "analyst"
OUTPUT_DIR = PROJECT_ROOT / "research_archive" / "_staging" / "audit-these"

# Patterns for factual claims
CLAIM_PATTERNS = [
    re.compile(r'\d+\.?\d*\s*%'),          # Percentages
    re.compile(r'ASR\s*[=:]\s*\d'),         # ASR values
    re.compile(r'Sep\(M\)\s*[=:]\s*\d'),    # Sep(M) values
    re.compile(r'N\s*[=:]\s*\d'),            # Sample sizes
    re.compile(r'p\s*[<=]\s*0\.\d'),         # p-values
    re.compile(r'SVC\s*[=:]\s*\d'),          # SVC scores
]

# Patterns for assertion words
ASSERTION_WORDS = re.compile(
    r'\b(montre|prouve|demontre|confirme|etablit|revele|indique|suggere|observe|mesure)\b',
    re.IGNORECASE
)

# Pattern for inline references (including bold-wrapped)
REF_PATTERN = re.compile(
    r'\([A-Z][a-z]+.*?,\s*\d{4}.*?\)|'     # (Author, Year, ...)
    r'\*\*[A-Z][a-z]+.*?\(\d{4}.*?\)\*\*|' # **Author (Year, ...)** bold format
    r'\[P\d{3}.*?\]|'                        # [P001, ...]
    r'P\d{3}\s|'                             # P001 inline
    r'\(Section\s+\d|'                        # (Section X
    r'Section\s+\d|'                          # Section X without parens
    r'\(Table\s+\d|'                          # (Table X
    r'Table\s+\d|'                            # Table X without parens
    r'\(Figure\s+\d|'                         # (Figure X
    r'Figure\s+\d|'                           # Figure X without parens
    r'\(Eq\.\s+\d|'                           # (Eq. X
    r'\(p\.\s+\d|'                            # (p. X
    r'arXiv:\d{4}\.\d{4,5}|'                 # arXiv:XXXX.XXXXX
    r'PDF NON DISPONIBLE|'                    # Paywall honesty tag
    r'ABSTRACT SEUL|'                         # Abstract-only tag
    r'SOURCE A VERIFIER|'                     # To-verify tag
    r'source secondaire',                     # Secondary source tag
    re.IGNORECASE
)

# Patterns to SKIP (not factual claims from papers)
SKIP_PATTERNS = re.compile(
    r'^- \*\*G-\d{3}\*\*|'                   # Gap descriptions (G-001, G-002...)
    r'^- \*\*D-\d{3}\*\*|'                   # Discovery descriptions
    r'^- \*\*C\d\b|'                          # Conjecture descriptions
    r'- C\d\s+\(|'                            # Conjecture refs in pertinence section
    r'AEGIS mesure|AEGIS implemente|'         # AEGIS system descriptions
    r'^\d+\.\s+\*\*[A-Z]|'                   # Numbered list items (analysis points)
    r'- \*\*delta-|'                          # Delta layer descriptions
    r'- δ[⁰¹²³]\s|'                          # Delta Unicode descriptions
    r'- \*\*δ[⁰¹²³]|'                        # Bold delta descriptions
    r'Supportee|Affaiblie|Neutre|'            # Conjecture evaluation terms
    r'confirmee|nuancee|contredite|'          # Discovery evaluation terms
    r'non adresse|partiellement|'             # Gap evaluation terms
    r'\[x\]\s+δ|'                             # Checklist delta items
    r'- \*\*Couches delta|'              # Delta layers section header
    r'- \*\*Conjectures|'                # Conjectures section header
    r'- \*\*D[eé]couvertes|'                # Discoveries section header
    r'- \*\*Gaps|'                        # Gaps section header
    r'- \*\*Mapping|'                          # Mapping section header
    r'\?\s*$|'                                # Questions ouvertes (interrogatives) — pas des affirmations
    r'Lien glossaire|'                         # Cross-ref glossaire AEGIS interne — pas un claim de papier
    r'Nature epistemique|'                     # Tag de classification epistemique
    r'^Ou \$|^ou \$|'                          # Definition de notation LaTeX ("Ou $...$ est ...")
    r'^- \$',                                  # Bullet de definition de notation LaTeX ("- $I_t$ : ...")
    re.IGNORECASE
)


def lint_file(file_path: Path) -> list:
    """Lint a single .md file for unsourced claims."""
    content = file_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    issues = []

    in_code_block = False
    for i, line in enumerate(lines):
        # Toggle on fenced code blocks; their interior is a formula/data display
        # introduced by a sourced prose header, not a prose factual claim.
        if line.lstrip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        # Skip headers, empty lines, metadata, tables, quotes
        if line.startswith("#") or line.startswith(">") or line.startswith("|") or not line.strip():
            continue
        # Skip gap/discovery/conjecture descriptions and system descriptions
        if SKIP_PATTERNS.search(line):
            continue

        has_claim = False
        claim_type = None

        # Check for numeric claims
        for pattern in CLAIM_PATTERNS:
            if pattern.search(line):
                has_claim = True
                claim_type = "numeric"
                break

        # Check for assertion words
        if not has_claim and ASSERTION_WORDS.search(line):
            has_claim = True
            claim_type = "assertion"

        if not has_claim:
            continue

        # Check for reference in context (this line + 2 lines before + 2 after)
        context_start = max(0, i - 2)
        context_end = min(len(lines), i + 3)
        context = "\n".join(lines[context_start:context_end])

        has_ref = bool(REF_PATTERN.search(context))

        if not has_ref:
            # Determine confidence level
            if REF_PATTERN.search(line):
                confidence = "HIGH"
            elif any(REF_PATTERN.search(lines[j]) for j in range(context_start, context_end) if j < len(lines)):
                confidence = "MEDIUM"
            else:
                confidence = "NONE"

            if confidence == "NONE":
                issues.append({
                    "file": file_path.name,
                    "line": i + 1,
                    "text": line.strip()[:100],
                    "claim_type": claim_type,
                    "confidence": confidence,
                })

    return issues


def main():
    parser = argparse.ArgumentParser(description="V2 — Sourcing Linter")
    parser.add_argument("--file", type=str, help="Scan specific file")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(STAGING.glob("P*_analysis.md"))

    all_issues = []
    total_claims = 0

    for f in files:
        issues = lint_file(f)
        all_issues.extend(issues)
        # Count total claims for percentage
        content = f.read_text(encoding="utf-8")
        for line in content.split("\n"):
            for p in CLAIM_PATTERNS:
                if p.search(line):
                    total_claims += 1
                    break
            else:
                if ASSERTION_WORDS.search(line):
                    total_claims += 1

    none_count = sum(1 for i in all_issues if i["confidence"] == "NONE")
    pct = (none_count / total_claims * 100) if total_claims > 0 else 0

    sys.stdout.buffer.write(f"Fichiers scannes: {len(files)}\n".encode("utf-8"))
    sys.stdout.buffer.write(f"Claims totales: {total_claims}\n".encode("utf-8"))
    sys.stdout.buffer.write(f"Sans source (NONE): {none_count} ({pct:.1f}%)\n".encode("utf-8"))
    sys.stdout.buffer.write(f"Seuil: < 2% = OK, > 5% = FAIL\n".encode("utf-8"))

    if all_issues:
        output_file = OUTPUT_DIR / f"UNSOURCED_CLAIMS_{datetime.now().strftime('%Y%m%d')}.md"
        lines_out = [f"# Unsourced Claims — {datetime.now().strftime('%Y-%m-%d')}\n",
                     f"Total: {none_count}/{total_claims} ({pct:.1f}%)\n\n",
                     "| Fichier | Ligne | Type | Texte |\n",
                     "|---------|-------|------|-------|\n"]
        for issue in all_issues[:100]:
            lines_out.append(f"| {issue['file']} | {issue['line']} | {issue['claim_type']} | {issue['text'][:60]} |\n")
        output_file.write_text("".join(lines_out), encoding="utf-8")
        sys.stdout.buffer.write(f"Output: {output_file}\n".encode("utf-8"))


if __name__ == "__main__":
    main()
