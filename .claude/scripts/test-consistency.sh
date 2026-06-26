#!/usr/bin/env bash
# test-consistency.sh — Cross-component consistency checks + doc gate
# Usage: bash .claude/scripts/test-consistency.sh
# Description: Validates cross-component consistency (doc, error handling, registration, epilogues)
# Exit 0 = all pass, exit 1 = failures found
set -uo pipefail

PROJECT_ROOT="$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel 2>/dev/null)"
HOOKS_DIR="$PROJECT_ROOT/.claude/hooks"
SCRIPTS_DIR="$PROJECT_ROOT/.claude/scripts"
SKILLS_DIR="$PROJECT_ROOT/.claude/skills"
SETTINGS="$PROJECT_ROOT/.claude/settings.local.json"
PASS=0
FAIL=0

report() {
  local status="$1" id="$2" msg="$3"
  echo "[$status] $id : $msg"
  if [ "$status" = "PASS" ]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); fi
}

echo "=== CONSISTENCY CHECKS — Cross-Component ==="
echo ""

# ============================================
# DOC GATE — every created file is documented
# ============================================
echo "--- Doc Gate ---"

# D-01 : SKILL.md files have description field
for skill_dir in "$SKILLS_DIR"/*/; do
  skill_name=$(basename "$skill_dir")
  skill_file="$skill_dir/SKILL.md"
  [ -f "$skill_file" ] || continue
  if grep -q "^description:" "$skill_file" 2>/dev/null; then
    report PASS "D-01-$skill_name" "SKILL.md has description"
  else
    report FAIL "D-01-$skill_name" "SKILL.md missing description field"
  fi
done

# D-02 : Every hook .cjs has a comment header explaining what it does
for hook in "$HOOKS_DIR"/*.cjs; do
  [ -f "$hook" ] || continue
  hname=$(basename "$hook")
  if head -3 "$hook" | grep -q "//.*hook\|//.*Hook\|//.*detect\|//.*scan"; then
    report PASS "D-02-$hname" "hook has doc header"
  else
    report FAIL "D-02-$hname" "hook missing doc header comment"
  fi
done

# D-03 : Every script .sh/.ps1 has a usage comment
for script in "$SCRIPTS_DIR"/*.sh "$SCRIPTS_DIR"/*.ps1; do
  [ -f "$script" ] || continue
  sname=$(basename "$script")
  if head -5 "$script" | grep -qi "usage\|synopsis\|description"; then
    report PASS "D-03-$sname" "script has usage/description"
  else
    report FAIL "D-03-$sname" "script missing usage/description in header"
  fi
done

echo ""
echo "--- Error Pattern Consistency ---"

# ============================================
# ERROR PATTERNS — all hooks handle errors the same way
# ============================================

# E-01 : All .cjs hooks handle empty stdin gracefully (exit 0)
for hook in "$HOOKS_DIR"/*.cjs; do
  [ -f "$hook" ] || continue
  hname=$(basename "$hook")
  EXIT_CODE=0
  echo '{}' | node "$hook" 2>/dev/null || EXIT_CODE=$?
  if [ "$EXIT_CODE" -eq 0 ]; then
    report PASS "E-01-$hname" "empty stdin = exit 0"
  else
    report FAIL "E-01-$hname" "empty stdin = exit $EXIT_CODE (expected 0)"
  fi
done

# E-02 : All .cjs hooks handle malformed JSON gracefully
for hook in "$HOOKS_DIR"/*.cjs; do
  [ -f "$hook" ] || continue
  hname=$(basename "$hook")
  EXIT_CODE=0
  echo 'BROKEN{{{' | node "$hook" 2>/dev/null || EXIT_CODE=$?
  if [ "$EXIT_CODE" -eq 0 ]; then
    report PASS "E-02-$hname" "malformed JSON = exit 0"
  else
    report FAIL "E-02-$hname" "malformed JSON = exit $EXIT_CODE (expected 0)"
  fi
done

echo ""
echo "--- Hook Registration Consistency ---"

# ============================================
# REGISTRATION — every hook file is registered in settings
# ============================================

# R-01 : Every .cjs in hooks/ is referenced in settings.local.json
for hook in "$HOOKS_DIR"/*.cjs; do
  [ -f "$hook" ] || continue
  hname=$(basename "$hook")
  if grep -q "$hname" "$SETTINGS" 2>/dev/null; then
    report PASS "R-01-$hname" "registered in settings.local.json"
  else
    report FAIL "R-01-$hname" "NOT registered in settings.local.json"
  fi
done

# R-02 : Every .sh in hooks/ is referenced in settings.local.json
for hook in "$HOOKS_DIR"/*.sh; do
  [ -f "$hook" ] || continue
  hname=$(basename "$hook")
  if grep -q "$hname" "$SETTINGS" 2>/dev/null; then
    report PASS "R-02-$hname" "registered in settings.local.json"
  else
    report FAIL "R-02-$hname" "NOT registered in settings.local.json"
  fi
done

# R-03 : settings.local.json references only hooks that exist
REFERENCED=$(grep -oE '[a-z_-]+\.(cjs|sh)' "$SETTINGS" 2>/dev/null | sort -u)
for ref in $REFERENCED; do
  found=0
  [ -f "$HOOKS_DIR/$ref" ] && found=1
  if [ "$found" -eq 1 ]; then
    report PASS "R-03-$ref" "settings reference -> file exists"
  else
    report FAIL "R-03-$ref" "settings references $ref but file missing in hooks/"
  fi
done

echo ""
echo "--- Dream Epilogue Consistency ---"

# ============================================
# EPILOGUE — all major skills have dream audit
# ============================================

MAJOR_SKILLS="research-director fiche-attaque audit-pdca aegis-prompt-forge bibliography-maintainer apex"
for skill in $MAJOR_SKILLS; do
  skill_file="$SKILLS_DIR/$skill/SKILL.md"
  if [ ! -f "$skill_file" ]; then
    report FAIL "EP-$skill" "SKILL.md not found"
    continue
  fi
  # Check dream epilogue exists
  if grep -q "dream" "$skill_file" 2>/dev/null; then
    # Check it says both audit AND consolidate (not just one)
    if grep -q "dream audit" "$skill_file" && grep -q "dream consolidate" "$skill_file"; then
      report PASS "EP-$skill" "dream epilogue complete (audit + consolidate)"
    else
      report FAIL "EP-$skill" "dream epilogue incomplete (needs both audit + consolidate)"
    fi
  else
    report FAIL "EP-$skill" "NO dream epilogue"
  fi
done

echo ""
echo "--- Loading States & Help Buttons (Skill Structure) ---"

# ============================================
# SKILL STRUCTURE — consistent patterns
# ============================================

# S-01 : All skills with user_invocable have argument_hint
for skill_dir in "$SKILLS_DIR"/*/; do
  skill_name=$(basename "$skill_dir")
  skill_file="$skill_dir/SKILL.md"
  [ -f "$skill_file" ] || continue
  if grep -q 'user_invocable.*true' "$skill_file" 2>/dev/null; then
    if grep -q 'argument_hint' "$skill_file" 2>/dev/null; then
      report PASS "S-01-$skill_name" "user_invocable + argument_hint present"
    else
      report FAIL "S-01-$skill_name" "user_invocable but NO argument_hint"
    fi
  fi
done

# S-02 : No skill has conflicting name vs directory name
for skill_dir in "$SKILLS_DIR"/*/; do
  skill_name=$(basename "$skill_dir")
  skill_file="$skill_dir/SKILL.md"
  [ -f "$skill_file" ] || continue
  declared_name=$(grep -m1 "^name:" "$skill_file" 2>/dev/null | sed 's/^name:\s*//' | tr -d '"' | tr -d "'" | xargs)
  if [ -z "$declared_name" ]; then
    report FAIL "S-02-$skill_name" "no name: field in SKILL.md"
  elif [ "$declared_name" = "$skill_name" ]; then
    report PASS "S-02-$skill_name" "name field matches directory"
  else
    report FAIL "S-02-$skill_name" "name='$declared_name' but dir='$skill_name'"
  fi
done

echo ""
echo "--- Build Preflight ---"

# ============================================
# BUILD — frontend + backend compile gate
# ============================================

# B-01 : Frontend build (npm run build)
FRONTEND_DIR="$PROJECT_ROOT/frontend"
if [ -d "$FRONTEND_DIR" ] && [ -f "$FRONTEND_DIR/package.json" ]; then
  BUILD_OUT=$(cd "$FRONTEND_DIR" && npm run build 2>&1)
  BUILD_EXIT=$?
  if [ "$BUILD_EXIT" -eq 0 ]; then
    report PASS B-01 "frontend npm run build succeeds"
  else
    ERRS=$(echo "$BUILD_OUT" | grep -i "error" | head -3)
    report FAIL B-01 "frontend build failed (exit $BUILD_EXIT) — $ERRS"
  fi
else
  report FAIL B-01 "frontend/ directory or package.json missing"
fi

# B-02 : Backend py_compile (server.py)
SERVER_PY="$PROJECT_ROOT/backend/server.py"
if [ -f "$SERVER_PY" ]; then
  PY_OUT=$(python -m py_compile "$SERVER_PY" 2>&1)
  PY_EXIT=$?
  if [ "$PY_EXIT" -eq 0 ]; then
    report PASS B-02 "backend server.py compiles"
  else
    report FAIL B-02 "backend server.py py_compile failed — $PY_OUT"
  fi
else
  report FAIL B-02 "backend/server.py not found"
fi

# B-03 : Backend py_compile all routes
ROUTES_DIR="$PROJECT_ROOT/backend/routes"
if [ -d "$ROUTES_DIR" ]; then
  ROUTE_FAILS=0
  for pyfile in "$ROUTES_DIR"/*.py; do
    [ -f "$pyfile" ] || continue
    python -m py_compile "$pyfile" 2>/dev/null || ROUTE_FAILS=$((ROUTE_FAILS + 1))
  done
  if [ "$ROUTE_FAILS" -eq 0 ]; then
    report PASS B-03 "all backend/routes/*.py compile"
  else
    report FAIL B-03 "$ROUTE_FAILS route files failed py_compile"
  fi
else
  report FAIL B-03 "backend/routes/ directory missing"
fi

# ============================================
# SUMMARY
# ============================================
echo ""
echo "=== SUMMARY ==="
TOTAL=$((PASS + FAIL))
echo "Total: $TOTAL | PASS: $PASS | FAIL: $FAIL"

if [ "$FAIL" -gt 0 ]; then
  echo "VERDICT: FAIL ($FAIL issues to fix)"
  exit 1
else
  echo "VERDICT: ALL GREEN"
  exit 0
fi
