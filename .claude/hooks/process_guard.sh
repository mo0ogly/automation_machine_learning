#!/usr/bin/env bash
# ============================================================
#  process_guard.sh — machine_learning Process Guard Hook
#
#  Enforces the fixed-port rule (.claude/rules/dev-environment.md):
#    frontend = 5173, backend = 8000.
#  It does NOT block the canonical launches — it only blocks a dev
#  server started on a DIFFERENT (random) port, which is the
#  documented duplicate-instance failure mode (autoPort spawning on
#  50950, 51961, ...). A launch with no explicit port, or on the
#  canonical port, passes through.
#
#  Triggered by: Claude Code PreToolUse on Bash.
# ============================================================

INPUT=$(cat)

# Extract the bash command from the JSON payload.
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
    CMD=$(echo "$INPUT" | grep -oP '"command"\s*:\s*"\K[^"]+' | head -1)
fi

FRONT_PORT=5173
BACK_PORT=8000

# Explicit port requested on the command line (--port 1234 or --port=1234), if any.
REQ_PORT=$(echo "$CMD" | grep -oE -- '--port[=[:space:]]+[0-9]+' | grep -oE '[0-9]+' | head -1)

# Is this a frontend dev-server launch? (npm run dev / npm start / a direct vite
# invocation) — but NOT build / preview / vitest, which are not long-lived servers.
is_frontend_launch() {
    echo "$CMD" | grep -qE '(npm[[:space:]]+run[[:space:]]+dev|npm[[:space:]]+start|vite/bin/vite\.js|[/.]bin/vite([[:space:]]|$)|(^|[[:space:]])vite([[:space:]]|$))' \
      && ! echo "$CMD" | grep -qE 'vite[[:space:]]+(build|preview)|vitest|run[[:space:]]+build'
}

# Is this a backend (uvicorn) launch?
is_backend_launch() {
    echo "$CMD" | grep -qE 'uvicorn[[:space:]]+[A-Za-z_]+:app|-m[[:space:]]+uvicorn'
}

# ── BLOCK: frontend on a non-canonical port ───────────────────
if is_frontend_launch && [ -n "$REQ_PORT" ] && [ "$REQ_PORT" != "$FRONT_PORT" ]; then
    cat <<EOF
[PROCESS GUARD] Le frontend doit tourner sur le port $FRONT_PORT (port fixe — voir
.claude/rules/dev-environment.md), pas sur $REQ_PORT.

  Depuis frontend/ :  npm run dev            # Vite sur :$FRONT_PORT
  ou strict          :  vite --port $FRONT_PORT --strictPort

Raison : un port aleatoire cree un serveur en double ; l'utilisateur regarde alors
un autre serveur et croit que « ca ne marche pas ». Reutiliser le :$FRONT_PORT existant.
EOF
    exit 2
fi

# ── BLOCK: backend on a non-canonical port ────────────────────
if is_backend_launch && [ -n "$REQ_PORT" ] && [ "$REQ_PORT" != "$BACK_PORT" ]; then
    cat <<EOF
[PROCESS GUARD] Le backend doit tourner sur le port $BACK_PORT (port fixe — voir
.claude/rules/dev-environment.md), pas sur $REQ_PORT. Le frontend appelle le backend
en dur sur http://localhost:$BACK_PORT.

  Depuis backend/ :  python -m uvicorn app:app --host 127.0.0.1 --port $BACK_PORT
EOF
    exit 2
fi

# ── WARN: killing a canonical port (allowed, but reminded) ────
if echo "$CMD" | grep -qE 'taskkill.*/(F|f).*/(PID|pid)|kill[[:space:]]+-9[[:space:]]+[0-9]'; then
    if echo "$CMD" | grep -qE '(^|[^0-9])(5173|8000)([^0-9]|$)'; then
        echo "[PROCESS GUARD] Rappel : le :5173 (front) et le :8000 (back) sont les serveurs de reference. (passage autorise)"
    fi
fi

exit 0
