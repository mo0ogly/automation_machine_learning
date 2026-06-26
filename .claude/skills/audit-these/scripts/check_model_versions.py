"""
V5b — Model Version Checker
Detecte les references a des modeles LLM obsoletes dans les analyses.

Usage:
    python check_model_versions.py                  # Scan toutes les analyses
    python check_model_versions.py --file P029.md   # Scan un fichier
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

# Models obsoletes ou renommes (avril 2026)
OBSOLETE_MODELS = {
    # OpenAI
    "GPT-4o": "Renomme/remplace par GPT-4.1 (janvier 2026)",
    "GPT-4o-mini": "Renomme/remplace par GPT-4.1-mini (janvier 2026)",
    "GPT-4-turbo": "Remplace par GPT-4.1 (janvier 2026)",
    "GPT-4-0613": "Deprecie (juin 2024), remplace par GPT-4-turbo puis GPT-4.1",
    "GPT-3.5-turbo": "Deprecie progressivement, remplace par GPT-4.1-nano",
    "text-davinci-003": "Deprecie (janvier 2024)",
    # Anthropic
    "Claude-3-haiku": "Remplace par Claude 4 Haiku (2026)",
    "Claude-3-opus": "Remplace par Claude Opus 4.6 (2026)",
    "Claude-3-sonnet": "Remplace par Claude 4 Sonnet (2026)",
    "Claude-3.5-sonnet": "Remplace par Claude 4 Sonnet (2026)",
    # Google
    "Gemini-1.0": "Deprecie, remplace par Gemini 2.x (2025)",
    "Gemini-1.5": "Remplace par Gemini 2.5 (2026)",
    "PaLM-2": "Deprecie, remplace par Gemini (2024)",
    # Meta
    "LLaMA-2": "Remplace par LLaMA 3.x (2024-2025)",
    "Llama-2-7B": "Remplace par Llama 3.2 3B (2025)",
    "Llama-2-13B": "Remplace par Llama 3.1 8B (2025)",
    "Llama-2-70B": "Remplace par Llama 3.3 70B (2025)",
    # Mistral
    "Mistral-7B-v0.1": "Remplace par Mistral-7B-v0.3 (2025)",
}

# Models actuels (avril 2026) — pour reference
CURRENT_MODELS = [
    "GPT-4.1", "GPT-4.1-mini", "GPT-4.1-nano", "GPT-5",
    "Claude 4 Haiku", "Claude 4 Sonnet", "Claude Opus 4.6", "Claude 4.5 Sonnet",
    "Gemini 2.5 Pro", "Gemini 2.5 Flash", "Gemini 2.0",
    "Llama 3.2", "Llama 3.3", "Llama 4",
    "Mistral Large", "Mistral Medium", "Mistral Small",
    "Qwen 3", "Qwen 2.5",
    "DeepSeek R1", "DeepSeek V3",
]


def check_file(file_path: Path) -> list:
    """Check a file for obsolete model references."""
    content = file_path.read_text(encoding="utf-8")
    issues = []

    for model, reason in OBSOLETE_MODELS.items():
        pattern = re.compile(re.escape(model), re.IGNORECASE)
        for match in pattern.finditer(content):
            line_num = content[:match.start()].count('\n') + 1
            # Get surrounding context
            line = content.split('\n')[line_num - 1].strip()
            issues.append({
                "file": file_path.name,
                "line": line_num,
                "model": model,
                "reason": reason,
                "context": line[:80],
            })

    return issues


def main():
    parser = argparse.ArgumentParser(description="V5b — Model Version Checker")
    parser.add_argument("--file", type=str, help="Scan specific file")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(STAGING.glob("P*_analysis.md"))

    all_issues = []
    for f in files:
        issues = check_file(f)
        all_issues.extend(issues)

    sys.stdout.buffer.write(f"Fichiers scannes: {len(files)}\n".encode("utf-8"))
    sys.stdout.buffer.write(f"References a des modeles obsoletes: {len(all_issues)}\n".encode("utf-8"))

    if all_issues:
        # Group by model
        by_model = {}
        for issue in all_issues:
            by_model.setdefault(issue["model"], []).append(issue)

        for model, issues in sorted(by_model.items(), key=lambda x: len(x[1]), reverse=True):
            sys.stdout.buffer.write(f"  {model}: {len(issues)} references — {issues[0]['reason']}\n".encode("utf-8"))

        output_file = OUTPUT_DIR / f"MODEL_VERSIONS_AUDIT_{datetime.now().strftime('%Y%m%d')}.md"
        lines_out = [
            f"# Model Versions Audit — {datetime.now().strftime('%Y-%m-%d')}\n\n",
            f"Total references obsoletes: {len(all_issues)}\n\n",
            "| Fichier | Ligne | Modele | Raison | Contexte |\n",
            "|---------|-------|--------|--------|----------|\n",
        ]
        for issue in all_issues:
            lines_out.append(
                f"| {issue['file']} | {issue['line']} | {issue['model']} | {issue['reason']} | {issue['context'][:50]} |\n"
            )
        output_file.write_text("".join(lines_out), encoding="utf-8")
        sys.stdout.buffer.write(f"Output: {output_file}\n".encode("utf-8"))
    else:
        sys.stdout.buffer.write(b"Aucun modele obsolete detecte.\n")


if __name__ == "__main__":
    main()
