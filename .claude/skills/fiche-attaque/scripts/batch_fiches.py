"""
Batch automation for Fiche d'Attaque generation.

Subcommands:
    list                        Show pending template numbers
    prepare --num 17            Prepare one template (metadata + .md)
    prepare --range 17 30       Prepare range of templates
    prepare --remaining         Prepare all pending templates
    assemble --num 17           Assemble .docx from sections JSON (stdin)
    mark-blocked --num 08       Mark template as blocked in index

This script does NOT call LLM agents. It handles the mechanical parts:
reading sources, assembling .docx, updating index.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# --- Path resolution ---
# scripts(0) -> fiche-attaque(1) -> skills(2) -> .claude(3) -> project-root(4)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
PROMPTS_DIR = PROJECT_ROOT / "backend" / "prompts"
OUTPUT_DIR = PROJECT_ROOT / "research_archive" / "doc_references" / "prompt_analysis"
INDEX_PATH = OUTPUT_DIR / "fiche_index.json"
DIM_CONFIG_PATH = PROMPTS_DIR / "dim_config.json"
BASELINE_PATH = PROMPTS_DIR / "detection_baseline.json"

# Import the docx generator
sys.path.insert(0, str(SCRIPT_DIR))
from generate_fiche_docx import generate_fiche

# --- Sensitive template detection ---
KNOWN_SENSITIVE_IDS = {8, 11}
SAFE_INDICATORS = ["ASR < 5%", "fails", "low effectiveness", "model will refuse", "near-zero"]
CAUTION_KEYWORDS = ["ransomware", "extortion", "malware", "exfiltrate", "steal", "encrypt files"]


def load_index() -> dict:
    if INDEX_PATH.exists():
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return {"last_updated": "", "total_templates": 97, "fiches_completed": 0,
            "fiches_remaining": 97, "fiches": {}}


def save_index(index: dict):
    index["last_updated"] = datetime.now().isoformat(timespec="seconds")
    done = sum(1 for v in index["fiches"].values()
               if isinstance(v, dict) and v.get("status") == "done")
    blocked = sum(1 for v in index["fiches"].values()
                  if isinstance(v, dict) and v.get("status") == "blocked")
    index["fiches_completed"] = done
    index["fiches_blocked"] = blocked
    index["fiches_remaining"] = 97 - done - blocked
    INDEX_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def find_template_files(template_num: int):
    """Find JSON and MD files for a template number."""
    pattern_json = f"{template_num:02d}-*.json"
    pattern_md = f"{template_num:02d}-*.md"
    json_files = list(PROMPTS_DIR.glob(pattern_json))
    md_files = list(PROMPTS_DIR.glob(pattern_md))
    # Filter out config files
    json_files = [f for f in json_files if not f.name.startswith(("dim_", "detection_", "llm_", "models_", "retex_"))]
    json_path = json_files[0] if json_files else None
    md_path = md_files[0] if md_files else None
    return json_path, md_path


def load_safe_metadata(json_path: Path) -> dict:
    """Load JSON metadata, stripping the template field (content filter safety)."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if k != "template"}


def assess_sensitivity(template_num: int, md_content: str) -> str:
    """Classify template sensitivity: safe, caution, or blocked."""
    if template_num in KNOWN_SENSITIVE_IDS:
        return "caution"

    md_lower = md_content.lower() if md_content else ""
    safe_count = sum(1 for ind in SAFE_INDICATORS if ind.lower() in md_lower)
    caution_count = sum(1 for kw in CAUTION_KEYWORDS if kw.lower() in md_lower)

    if safe_count >= 2:
        return "safe"
    if caution_count >= 2 and safe_count < 2:
        return "caution"
    return "safe"


def prepare_template(template_num: int) -> dict:
    """Prepare template data for LLM agent processing."""
    json_path, md_path = find_template_files(template_num)
    if not json_path:
        return {"template_num": template_num, "available": False,
                "error": "JSON file not found"}

    metadata = load_safe_metadata(json_path)
    analysis_md = md_path.read_text(encoding="utf-8") if md_path else ""
    sensitivity = assess_sensitivity(template_num, analysis_md)

    # Load configs
    dim_config = json.loads(DIM_CONFIG_PATH.read_text(encoding="utf-8")) if DIM_CONFIG_PATH.exists() else {}
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) if BASELINE_PATH.exists() else {}

    # Build slug for output filename
    slug = json_path.stem  # e.g., "17-genetic-additional-task"

    return {
        "template_num": template_num,
        "available": True,
        "slug": slug,
        "sensitivity": sensitivity,
        "metadata": metadata,
        "analysis_md": analysis_md,
        "dim_config": dim_config,
        "detection_baseline": baseline,
        "json_path": str(json_path),
        "md_path": str(md_path) if md_path else None,
    }


def assemble_fiche(template_num: int, metadata: dict, sections: dict,
                   slug: str = None) -> str:
    """Assemble .docx from sections dict, update index."""
    if not slug:
        json_path, _ = find_template_files(template_num)
        slug = json_path.stem if json_path else f"{template_num:02d}-unknown"

    output_name = "fiche_attaque_" + slug.replace("-", "_") + ".docx"
    output_path = OUTPUT_DIR / output_name

    try:
        generate_fiche(metadata, sections, str(output_path))
    except Exception as e:
        err_msg = str(e).lower()
        if any(kw in err_msg for kw in ("content", "filter", "policy", "blocked")):
            # Content filter — mark as blocked
            index = load_index()
            num_str = str(template_num)
            index["fiches"][num_str] = {
                "status": "blocked",
                "reason": "content_filter",
                "last_attempt": datetime.now().strftime("%Y-%m-%d"),
                "error": str(e)[:200],
            }
            save_index(index)
            return f"BLOCKED: template {template_num} — {e}"
        raise

    # Update index
    index = load_index()
    num_str = str(template_num)
    index["fiches"][num_str] = {
        "status": "done",
        "file": output_name,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "name": metadata.get("name", "Unknown"),
        "target_delta": metadata.get("target_delta", "-"),
        "conjecture": metadata.get("conjecture", "-") or "-",
        "svc_score": sections.get("_svc_score", "-"),
        "asr": sections.get("_asr", "-"),
        "sep_m_valid": sections.get("_sep_m_valid", False),
        "notes": "Generated by batch_fiches.py (3 agents: SCIENTIST+MATH+CYBER-LIBRARIAN)",
    }
    save_index(index)

    # HOOK: Signal au SCIENTIST + audit qualite
    _post_assemble_hooks(template_num, output_name)

    return f"OK: {output_path}"


def _post_assemble_hooks(template_num: int, output_name: str):
    """Hooks automatiques post-assemblage : signal SCIENTIST + audit."""
    # 1. Signal SCIENTIST pour production de note
    signal_dir = PROJECT_ROOT / "research_archive" / "_staging" / "scientist"
    signal_dir.mkdir(parents=True, exist_ok=True)
    signal_file = signal_dir / "PENDING_SCIENTIST_REVIEW.md"
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(signal_file, "a", encoding="utf-8") as f:
        f.write(f"- [{timestamp}] Fiche #{template_num} ({output_name}) assemblee — NOTE SCIENTIST REQUISE\n")

    # 2. Signal audit qualite (lint_sources)
    audit_signal = PROJECT_ROOT / "research_archive" / "_staging" / "audit-these"
    audit_signal.mkdir(parents=True, exist_ok=True)
    audit_file = audit_signal / "PENDING_AUDIT.md"
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(f"- [{timestamp}] Fiche #{template_num} — AUDIT V2 (lint_sources) REQUIS avant validation\n")


def get_remaining() -> list:
    """Return sorted list of pending template numbers."""
    index = load_index()
    pending = []
    for key, val in index["fiches"].items():
        if key == "C1":
            continue
        status = val.get("status", "pending") if isinstance(val, dict) else val
        if status == "pending" or (isinstance(val, dict) and val.get("status") == "pending"):
            try:
                pending.append(int(key))
            except ValueError:
                pass
    return sorted(pending)


def mark_blocked(template_num: int, reason: str):
    """Mark a template as blocked in the index."""
    index = load_index()
    num_str = str(template_num)
    existing = index["fiches"].get(num_str, {})
    if isinstance(existing, dict):
        existing["status"] = "blocked"
        existing["reason"] = reason
        existing["last_attempt"] = datetime.now().strftime("%Y-%m-%d")
    else:
        index["fiches"][num_str] = {
            "status": "blocked",
            "reason": reason,
            "last_attempt": datetime.now().strftime("%Y-%m-%d"),
        }
    save_index(index)
    print(f"BLOCKED: template {template_num} — {reason}")


# --- CLI ---
def main():
    parser = argparse.ArgumentParser(description="Batch automation for Fiche d'Attaque")
    sub = parser.add_subparsers(dest="command")

    # list
    sub.add_parser("list", help="Show pending template numbers")

    # prepare
    p_prep = sub.add_parser("prepare", help="Prepare template data for LLM agents")
    p_prep.add_argument("--num", type=int, help="Single template number")
    p_prep.add_argument("--range", nargs=2, type=int, metavar=("START", "END"))
    p_prep.add_argument("--remaining", action="store_true")

    # assemble
    p_asm = sub.add_parser("assemble", help="Assemble .docx from sections JSON (stdin)")
    p_asm.add_argument("--num", type=int, required=True)
    p_asm.add_argument("--slug", type=str, default=None)

    # mark-blocked
    p_block = sub.add_parser("mark-blocked", help="Mark template as blocked")
    p_block.add_argument("--num", type=int, required=True)
    p_block.add_argument("--reason", type=str, default="content_filter")

    args = parser.parse_args()

    if args.command == "list":
        remaining = get_remaining()
        print(f"Pending: {len(remaining)} templates")
        print(" ".join(str(n) for n in remaining))

    elif args.command == "prepare":
        nums = []
        if args.num:
            nums = [args.num]
        elif args.range:
            nums = list(range(args.range[0], args.range[1] + 1))
        elif args.remaining:
            nums = get_remaining()
        else:
            parser.error("Specify --num, --range, or --remaining")

        results = []
        for n in nums:
            results.append(prepare_template(n))
        output = json.dumps(results, indent=2, ensure_ascii=False)
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.write(b"\n")

    elif args.command == "assemble":
        # Read sections JSON from stdin
        sections_json = sys.stdin.read()
        data = json.loads(sections_json)
        metadata = data.get("metadata", {})
        sections = data.get("sections", {})
        result = assemble_fiche(args.num, metadata, sections, args.slug)
        print(result)

    elif args.command == "mark-blocked":
        mark_blocked(args.num, args.reason)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
