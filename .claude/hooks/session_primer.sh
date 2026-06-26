#!/usr/bin/env bash
# AEGIS SessionStart hook -- primes Claude Code with current bibliography state.
#
# Created 2026-04-09 after the RUN-008 Crescendo duplicate incident, where a
# scoped bibliography verification agent re-verified arXiv:2404.01833 without
# noticing it was already P099 in the AEGIS corpus. Fix: force the orchestrator
# to see the current state (last RUN, recent P-IDs, duplicates) at session start
# so it cannot "forget" what has already been done.
#
# Behaviour: at the start of each Claude Code session, this script prints a
# compact summary that is injected into the session context. The orchestrator
# thus starts primed with:
#   1. The last RUN metadata (from MEMORY_STATE.md)
#   2. The most recent EXECUTION_LOG.jsonl entry
#   3. The last 5 P-IDs added to the corpus (from MANIFEST.md)
#   4. A reminder to run check_corpus_dedup.py before any bibliography action
#
# The script is silent if AEGIS infrastructure is absent (useful for non-poc_medical
# projects that share the same .claude config).
#
# Registered in .claude/settings.local.json under hooks.SessionStart.

set -uo pipefail

# Resolve repo root from this script's location. Works regardless of cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

MEMORY_STATE="$REPO_ROOT/research_archive/_staging/memory/MEMORY_STATE.md"
EXECUTION_LOG="$REPO_ROOT/research_archive/_staging/memory/EXECUTION_LOG.jsonl"
MANIFEST="$REPO_ROOT/research_archive/doc_references/MANIFEST.md"

# Silent exit if this project does not have AEGIS bibliography infrastructure.
# This lets the same settings config coexist with non-AEGIS projects.
[ -f "$MEMORY_STATE" ] || exit 0
[ -f "$EXECUTION_LOG" ] || exit 0

echo ""
echo "=== AEGIS bibliography state primer (SessionStart hook) ==="
echo "Read this BEFORE any bibliography, analysis, or paper-integration work."
echo ""

# -----------------------------------------------------------------------------
# Section 1 -- Last Execution block from MEMORY_STATE.md
# -----------------------------------------------------------------------------
echo "--- MEMORY_STATE.md / Last Execution ---"
# Extract from '## Last Execution' until the next '## ' header (exclusive)
awk '
    /^## Last Execution/ { p=1; print; next }
    p==1 && /^## / { p=0; exit }
    p==1 { print }
' "$MEMORY_STATE" | head -15
echo ""

# -----------------------------------------------------------------------------
# Section 2 -- Most recent EXECUTION_LOG.jsonl entry (raw, single line)
# -----------------------------------------------------------------------------
echo "--- EXECUTION_LOG.jsonl / Most recent RUN ---"
LAST_RUN="$(tail -1 "$EXECUTION_LOG" 2>/dev/null || echo '')"
if [ -n "$LAST_RUN" ]; then
    # Print wrapped to 180 cols, max 8 visual lines, for readability in context
    echo "$LAST_RUN" | fold -s -w 180 | head -8
else
    echo "  (EXECUTION_LOG.jsonl is empty)"
fi
echo ""

# -----------------------------------------------------------------------------
# Section 3 -- Last 5 P-IDs in MANIFEST.md table (short form)
# -----------------------------------------------------------------------------
if [ -f "$MANIFEST" ]; then
    echo "--- MANIFEST.md / Last 5 papers in corpus ---"
    # Grep table rows starting with "| P<digits>", take last 5, trim to 180 cols
    grep -E '^\| P[0-9]+ ' "$MANIFEST" 2>/dev/null | tail -5 | cut -c 1-180
    echo ""
fi

# -----------------------------------------------------------------------------
# Section 4 -- Anti-doublon etape 0 reminder (mandatory rule)
# -----------------------------------------------------------------------------
cat <<'EOF'
--- ANTI-DOUBLON ETAPE 0 (mandatory before any bibliography action) ---
Before verifying, analyzing, downloading, or injecting any paper with an arXiv ID:

  $ python backend/tools/check_corpus_dedup.py <arxiv_id> [<arxiv_id> ...]
    exit 0 = [NEW]       safe to add to corpus
    exit 1 = [DUPLICATE] already present as PXXX -- do NOT re-add
    exit 2 = [ERROR]     MANIFEST missing or needle invalid

Rule source: .claude/rules/doctoral-research.md "ANTI-DOUBLON ETAPE 0"
Bibliography workflow: .claude/skills/bibliography-maintainer/SKILL.md Step 0

EOF

echo "=== End of AEGIS session primer ==="
echo ""

exit 0
