#!/usr/bin/env bash
# ============================================================
#  process_guard.sh — AEGIS Process Guard Hook
#  Intercepts wild start/stop commands and redirects to
#  aegis.ps1 (Windows) or aegis.sh (Linux/macOS).
#
#  Triggered by: Claude Code PreToolUse on Bash
#  Block pattern: direct uvicorn / npm run dev / kill-port
# ============================================================

INPUT=$(cat)

# Extract the bash command from the JSON payload
CMD=""
if command -v python3 &>/dev/null; then
    CMD=$(python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('command', ''))
except Exception:
    print('')
" <<< "$INPUT" 2>/dev/null)
elif command -v python &>/dev/null; then
    CMD=$(python -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('command', ''))
except Exception:
    print('')
" <<< "$INPUT" 2>/dev/null)
else
    # Fallback: raw grep on JSON
    CMD=$(echo "$INPUT" | grep -oP '"command"\s*:\s*"\K[^"]+' | head -1)
fi

# Detect OS for script name
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || -n "$WINDIR" ]]; then
    AEGIS=".\aegis.ps1"
    RUN_CMD=".\aegis.ps1"
else
    AEGIS="./aegis.sh"
    RUN_CMD="./aegis.sh"
fi

# ── BLOCK: wild backend start ─────────────────────────────────
if echo "$CMD" | grep -qE "uvicorn\s+server:app|python.*-m\s+uvicorn.*server|python.*server\.py\s*$"; then
    cat <<EOF
[AEGIS PROCESS GUARD] Use $AEGIS instead of direct uvicorn.

  $RUN_CMD start backend    # start FastAPI on :8042
  $RUN_CMD restart backend  # kill + restart
  $RUN_CMD health           # check status

Reason: direct uvicorn launches bypass port-conflict detection,
PID tracking, and log routing to logs/backend.log.
EOF
    exit 2
fi

# ── BLOCK: wild frontend start ────────────────────────────────
if echo "$CMD" | grep -qE "npm\s+run\s+dev\b|npm\s+start\b" && ! echo "$CMD" | grep -q "build"; then
    cat <<EOF
[AEGIS PROCESS GUARD] Use $AEGIS instead of direct npm run dev.

  $RUN_CMD start frontend   # start Vite on :5173
  $RUN_CMD restart frontend # kill + restart
  $RUN_CMD health           # check status

Reason: direct npm run dev bypasses port-conflict detection
and log routing to logs/frontend.log.
EOF
    exit 2
fi

# ── WARN: wild port kill (let through but remind) ─────────────
if echo "$CMD" | grep -qE "taskkill.*/(F|f).*/(PID|pid)|kill\s+-9\s+[0-9]"; then
    if echo "$CMD" | grep -qE "804[0-9]|517[0-9]"; then
        cat <<EOF
[AEGIS PROCESS GUARD] Reminder: prefer $AEGIS for port management.
  $RUN_CMD kill-port 8042   # kill backend port
  $RUN_CMD kill-port 5173   # kill frontend port
  $RUN_CMD stop             # stop both gracefully
(Passing through — manual kill allowed for unblocking)
EOF
        # exit 0 = allow pass-through with message
    fi
fi

exit 0
