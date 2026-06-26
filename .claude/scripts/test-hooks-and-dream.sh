#!/usr/bin/env bash
# test-hooks-and-dream.sh — Gate tests for hooks + dream scripts
# Usage: bash .claude/scripts/test-hooks-and-dream.sh
# Description: 30 tests validating frustration-detector, secret-scanner, and dream audit
# Exit 0 = all pass, exit 1 = failures found
set -uo pipefail

PROJECT_ROOT="$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel 2>/dev/null)"
HOOKS_DIR="$PROJECT_ROOT/.claude/hooks"
SCRIPTS_DIR="$PROJECT_ROOT/.claude/scripts"
SKILLS_DIR="$PROJECT_ROOT/.claude/skills"
PASS=0
FAIL=0
WARN=0

report() {
  local status="$1" id="$2" msg="$3"
  if [ "$status" = "PASS" ]; then
    echo "[PASS] $id : $msg"
    PASS=$((PASS + 1))
  elif [ "$status" = "FAIL" ]; then
    echo "[FAIL] $id : $msg"
    FAIL=$((FAIL + 1))
  elif [ "$status" = "WARN" ]; then
    echo "[WARN] $id : $msg"
    WARN=$((WARN + 1))
  fi
}

echo "=== GATE TESTS — Hooks & Dream ==="
echo ""

# -------------------------------------------------------
# T-01 : frustration-detector.cjs — frustration FR detected
# -------------------------------------------------------
OUT=$(echo '{"prompt":"putain ca marche pas"}' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
if echo "$OUT" | grep -q "DROIT AU BUT"; then
  report PASS T-01 "frustration FR triggers direct-fix context"
else
  report FAIL T-01 "frustration FR not detected — got: $OUT"
fi

# -------------------------------------------------------
# T-02 : frustration-detector.cjs — frustration EN detected
# -------------------------------------------------------
OUT=$(echo '{"prompt":"wtf this is broken again"}' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
if echo "$OUT" | grep -q "DROIT AU BUT"; then
  report PASS T-02 "frustration EN triggers direct-fix context"
else
  report FAIL T-02 "frustration EN not detected — got: $OUT"
fi

# -------------------------------------------------------
# T-03 : frustration-detector.cjs — "continue" triggers resume
# -------------------------------------------------------
OUT=$(echo '{"prompt":"continue"}' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
if echo "$OUT" | grep -q "reprennes"; then
  report PASS T-03 "'continue' triggers resume context"
else
  report FAIL T-03 "'continue' not detected — got: $OUT"
fi

# -------------------------------------------------------
# T-04 : frustration-detector.cjs — "finis" triggers resume
# -------------------------------------------------------
OUT=$(echo '{"prompt":"finis"}' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
if echo "$OUT" | grep -q "reprennes"; then
  report PASS T-04 "'finis' triggers resume context"
else
  report FAIL T-04 "'finis' not detected — got: $OUT"
fi

# -------------------------------------------------------
# T-05 : frustration-detector.cjs — normal message = no injection
# -------------------------------------------------------
OUT=$(echo '{"prompt":"ajoute un bouton dans le header"}' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
if [ -z "$OUT" ]; then
  report PASS T-05 "normal message produces no injection"
else
  report FAIL T-05 "normal message should not inject — got: $OUT"
fi

# -------------------------------------------------------
# T-06 : frustration-detector.cjs — empty prompt = no crash
# -------------------------------------------------------
OUT=$(echo '{"prompt":""}' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  report PASS T-06 "empty prompt does not crash (exit 0)"
else
  report FAIL T-06 "empty prompt crashed (exit $EXIT)"
fi

# -------------------------------------------------------
# T-07 : frustration-detector.cjs — malformed JSON = no crash
# -------------------------------------------------------
OUT=$(echo 'not json' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  report PASS T-07 "malformed JSON does not crash"
else
  report WARN T-07 "malformed JSON crashed (exit $EXIT)"
fi

# -------------------------------------------------------
# T-08 : frustration-detector.cjs — "encore casse" (accent) detected
# -------------------------------------------------------
OUT=$(echo '{"prompt":"encore cassé ce truc"}' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
if echo "$OUT" | grep -q "DROIT AU BUT"; then
  report PASS T-08 "'encore casse' (accent) triggers frustration"
else
  report FAIL T-08 "'encore casse' not detected — got: $OUT"
fi

# -------------------------------------------------------
# T-09 : secret-scanner.cjs — non-commit command = passthrough
# -------------------------------------------------------
OUT=$(echo '{"tool_input":{"command":"ls -la"}}' | node "$HOOKS_DIR/secret-scanner.cjs" 2>/dev/null)
EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  report PASS T-09 "non-commit command passes through (exit 0)"
else
  report FAIL T-09 "non-commit command blocked (exit $EXIT)"
fi

# -------------------------------------------------------
# T-10 : secret-scanner.cjs — git commit on clean staged = pass
# -------------------------------------------------------
OUT=$(echo '{"tool_input":{"command":"git commit -m test"}}' | node "$HOOKS_DIR/secret-scanner.cjs" 2>/dev/null)
EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  report PASS T-10 "git commit on clean staged files passes"
else
  report FAIL T-10 "git commit on clean staged was blocked (exit $EXIT)"
fi

# -------------------------------------------------------
# T-11 : secret-scanner.cjs — empty input = no crash
# -------------------------------------------------------
OUT=$(echo '{}' | node "$HOOKS_DIR/secret-scanner.cjs" 2>/dev/null)
EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  report PASS T-11 "empty input does not crash secret-scanner"
else
  report FAIL T-11 "empty input crashed secret-scanner (exit $EXIT)"
fi

# -------------------------------------------------------
# T-12 : dream-audit.sh exists and is executable
# -------------------------------------------------------
if [ -f "$SCRIPTS_DIR/dream-audit.sh" ]; then
  report PASS T-12 "dream-audit.sh exists"
else
  report FAIL T-12 "dream-audit.sh missing"
fi

# -------------------------------------------------------
# T-13 : dream-audit.ps1 exists
# -------------------------------------------------------
if [ -f "$SCRIPTS_DIR/dream-audit.ps1" ]; then
  report PASS T-13 "dream-audit.ps1 exists"
else
  report FAIL T-13 "dream-audit.ps1 missing"
fi

# -------------------------------------------------------
# T-14 : dream-audit.sh — runs on non-existent dir = exit 0 (skip)
# -------------------------------------------------------
OUT=$(bash "$SCRIPTS_DIR/dream-audit.sh" "/tmp/nonexistent_dream_test_dir_$RANDOM" 2>/dev/null)
EXIT=$?
if [ "$EXIT" -eq 0 ]; then
  report PASS T-14 "dream-audit.sh on missing dir = SKIP (exit 0)"
else
  report FAIL T-14 "dream-audit.sh on missing dir = exit $EXIT (expected 0)"
fi

# -------------------------------------------------------
# T-15 : dream skill SKILL.md exists and has correct name
# -------------------------------------------------------
if [ -f "$SKILLS_DIR/dream/SKILL.md" ]; then
  if grep -q "^name: dream" "$SKILLS_DIR/dream/SKILL.md"; then
    report PASS T-15 "dream/SKILL.md exists with name: dream"
  else
    report WARN T-15 "dream/SKILL.md exists but name field mismatch"
  fi
else
  report FAIL T-15 "dream/SKILL.md missing"
fi

# -------------------------------------------------------
# T-16 : settings.local.json — frustration hook registered
# -------------------------------------------------------
SETTINGS="$PROJECT_ROOT/.claude/settings.local.json"
if grep -q "frustration-detector" "$SETTINGS" 2>/dev/null; then
  report PASS T-16 "frustration-detector registered in settings.local.json"
else
  report FAIL T-16 "frustration-detector NOT in settings.local.json"
fi

# -------------------------------------------------------
# T-17 : settings.local.json — secret-scanner hook registered
# -------------------------------------------------------
if grep -q "secret-scanner" "$SETTINGS" 2>/dev/null; then
  report PASS T-17 "secret-scanner registered in settings.local.json"
else
  report FAIL T-17 "secret-scanner NOT in settings.local.json"
fi

# -------------------------------------------------------
# T-18 : settings.local.json — valid JSON
# -------------------------------------------------------
if node -e "JSON.parse(require('fs').readFileSync('$SETTINGS','utf8'))" 2>/dev/null; then
  report PASS T-18 "settings.local.json is valid JSON"
else
  report FAIL T-18 "settings.local.json is NOT valid JSON"
fi

# -------------------------------------------------------
# T-19 : dream epilogue in research-director SKILL.md
# -------------------------------------------------------
if grep -q "dream audit" "$SKILLS_DIR/research-director/SKILL.md" 2>/dev/null; then
  report PASS T-19 "dream epilogue in research-director"
else
  report FAIL T-19 "dream epilogue MISSING in research-director"
fi

# -------------------------------------------------------
# T-20 : dream epilogue in fiche-attaque SKILL.md
# -------------------------------------------------------
if grep -q "dream audit" "$SKILLS_DIR/fiche-attaque/SKILL.md" 2>/dev/null; then
  report PASS T-20 "dream epilogue in fiche-attaque"
else
  report FAIL T-20 "dream epilogue MISSING in fiche-attaque"
fi

# -------------------------------------------------------
# T-21 : dream epilogue in audit-pdca SKILL.md
# -------------------------------------------------------
if grep -q "dream audit" "$SKILLS_DIR/audit-pdca/SKILL.md" 2>/dev/null; then
  report PASS T-21 "dream epilogue in audit-pdca"
else
  report FAIL T-21 "dream epilogue MISSING in audit-pdca"
fi

# -------------------------------------------------------
# T-22 : dream epilogue in aegis-prompt-forge SKILL.md
# -------------------------------------------------------
if grep -q "dream audit" "$SKILLS_DIR/aegis-prompt-forge/SKILL.md" 2>/dev/null; then
  report PASS T-22 "dream epilogue in aegis-prompt-forge"
else
  report FAIL T-22 "dream epilogue MISSING in aegis-prompt-forge"
fi

# -------------------------------------------------------
# T-23 : dream epilogue in bibliography-maintainer SKILL.md
# -------------------------------------------------------
if grep -q "dream audit" "$SKILLS_DIR/bibliography-maintainer/SKILL.md" 2>/dev/null; then
  report PASS T-23 "dream epilogue in bibliography-maintainer"
else
  report FAIL T-23 "dream epilogue MISSING in bibliography-maintainer"
fi

# -------------------------------------------------------
# T-24 : dream epilogue in apex SKILL.md
# -------------------------------------------------------
if grep -q "dream audit" "$SKILLS_DIR/apex/SKILL.md" 2>/dev/null; then
  report PASS T-24 "dream epilogue in apex"
else
  report FAIL T-24 "dream epilogue MISSING in apex"
fi

# -------------------------------------------------------
# T-25 : swarm context sheet in apex SKILL.md
# -------------------------------------------------------
if grep -q "SWARM_CONTEXT" "$SKILLS_DIR/apex/SKILL.md" 2>/dev/null; then
  report PASS T-25 "SWARM_CONTEXT sheet in apex"
else
  report FAIL T-25 "SWARM_CONTEXT sheet MISSING in apex"
fi

# -------------------------------------------------------
# T-26 : bibliography-maintainer has correct name (not aegis-prompt-forge)
# -------------------------------------------------------
BIBLIO_NAME=$(grep -m1 "^name:" "$SKILLS_DIR/bibliography-maintainer/SKILL.md" 2>/dev/null | sed 's/name:\s*//')
if echo "$BIBLIO_NAME" | grep -q "bibliography"; then
  report PASS T-26 "bibliography-maintainer has correct name field"
else
  report FAIL T-26 "bibliography-maintainer has wrong name: $BIBLIO_NAME"
fi

# -------------------------------------------------------
# T-27 : all 6 agents in apex have Swarm Context instruction
# -------------------------------------------------------
COUNT=$(grep -c "Swarm Context:" "$SKILLS_DIR/apex/SKILL.md" 2>/dev/null)
if [ "$COUNT" -ge 6 ]; then
  report PASS T-27 "all 6 agent prompts have Swarm Context instruction ($COUNT found)"
else
  report FAIL T-27 "only $COUNT/6 agent prompts have Swarm Context instruction"
fi

# -------------------------------------------------------
# T-28 : secret-scanner has >= 15 patterns
# -------------------------------------------------------
PATTERN_COUNT=$(grep -c "name:" "$HOOKS_DIR/secret-scanner.cjs" 2>/dev/null)
if [ "$PATTERN_COUNT" -ge 15 ]; then
  report PASS T-28 "secret-scanner has $PATTERN_COUNT patterns (>= 15)"
else
  report FAIL T-28 "secret-scanner has only $PATTERN_COUNT patterns (need >= 15)"
fi

# -------------------------------------------------------
# T-29 : frustration-detector handles "doesn't work"
# -------------------------------------------------------
OUT=$(echo '{"prompt":"it doesnt work at all"}' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
if echo "$OUT" | grep -q "DROIT AU BUT"; then
  report PASS T-29 "'doesnt work' triggers frustration"
else
  report FAIL T-29 "'doesnt work' not detected — got: $OUT"
fi

# -------------------------------------------------------
# T-30 : frustration-detector — "keep going" triggers resume
# -------------------------------------------------------
OUT=$(echo '{"prompt":"keep going"}' | node "$HOOKS_DIR/frustration-detector.cjs" 2>/dev/null)
if echo "$OUT" | grep -q "reprennes"; then
  report PASS T-30 "'keep going' triggers resume context"
else
  report FAIL T-30 "'keep going' not detected — got: $OUT"
fi

# -------------------------------------------------------
# SUMMARY
# -------------------------------------------------------
echo ""
echo "=== SUMMARY ==="
TOTAL=$((PASS + FAIL + WARN))
echo "Total: $TOTAL | PASS: $PASS | FAIL: $FAIL | WARN: $WARN"

if [ "$FAIL" -gt 0 ]; then
  echo "VERDICT: FAIL ($FAIL failures)"
  exit 1
elif [ "$WARN" -gt 0 ]; then
  echo "VERDICT: WARN ($WARN warnings to fix)"
  exit 1
else
  echo "VERDICT: ALL GREEN"
  exit 0
fi
