#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# mlauto.sh — single entry point to manage the automation_machine_learning stack
# (Docker: backend FastAPI :8000 + frontend nginx :5173).
#
#   ./mlauto.sh up            # build if needed + start, wait until healthy
#   ./mlauto.sh down          # stop and remove containers
#   ./mlauto.sh restart       # restart both services
#   ./mlauto.sh build         # build images
#   ./mlauto.sh rebuild       # build --no-cache + restart
#   ./mlauto.sh logs [svc]    # follow logs (optionally one service)
#   ./mlauto.sh ps            # container status
#   ./mlauto.sh status        # status + health snapshot
#   ./mlauto.sh health        # probe backend /health + frontend
#   ./mlauto.sh shell [svc]   # open a shell in a service (default: backend)
#   ./mlauto.sh test          # run the backend test-suite inside the container
#   ./mlauto.sh seed          # replay the pipeline on every demo dataset (idempotent)
#   ./mlauto.sh clean         # stop + remove the session volume (DESTRUCTIVE)
#   ./mlauto.sh help
#
# Author: Fabrice Pizzi
# ===========================================================================

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT}"

# --- colours -----------------------------------------------------------------
if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
else
    GREEN=''; YELLOW=''; RED=''; CYAN=''; NC=''
fi
hdr()  { printf "\n${CYAN}== %s ==${NC}\n" "$*"; }
info() { printf "${GREEN}%s${NC}\n" "$*"; }
warn() { printf "${YELLOW}%s${NC}\n" "$*"; }
err()  { printf "${RED}%s${NC}\n" "$*" >&2; }

# --- docker compose (v2 preferred, v1 fallback) ------------------------------
if docker compose version >/dev/null 2>&1; then
    DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    DC=(docker-compose)
else
    err "Docker Compose introuvable. Installez Docker Desktop / le plugin compose."
    exit 1
fi

# Host ports (mirror .env defaults so messages match what's published).
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
if [ -f .env ]; then
    BACKEND_PORT="$(grep -E '^BACKEND_PORT=' .env  | tail -1 | cut -d= -f2 || true)"; BACKEND_PORT="${BACKEND_PORT:-8000}"
    FRONTEND_PORT="$(grep -E '^FRONTEND_PORT=' .env | tail -1 | cut -d= -f2 || true)"; FRONTEND_PORT="${FRONTEND_PORT:-5173}"
fi

_require_daemon() {
    if ! docker info >/dev/null 2>&1; then
        err "Le démon Docker ne répond pas — démarrez Docker Desktop puis réessayez."
        exit 1
    fi
}

_urls() {
    info "Frontend : http://localhost:${FRONTEND_PORT}"
    info "Backend  : http://localhost:${BACKEND_PORT}  (santé : /health)"
}

_wait_healthy() {
    printf "Attente du backend "
    for _ in $(seq 1 30); do
        if curl -fsS "http://localhost:${BACKEND_PORT}/health" >/dev/null 2>&1; then
            printf " ${GREEN}OK${NC}\n"; return 0
        fi
        printf "."; sleep 2
    done
    printf " ${YELLOW}(pas encore prêt — voir './mlauto.sh logs')${NC}\n"
}

cmd_up() {
    _require_daemon
    hdr "Démarrage de la stack (build si nécessaire)"
    "${DC[@]}" up -d --build
    _wait_healthy
    cmd_seed
    _urls
}

cmd_down()    { _require_daemon; hdr "Arrêt"; "${DC[@]}" down; }
cmd_restart() { _require_daemon; hdr "Redémarrage"; "${DC[@]}" restart; _wait_healthy; _urls; }
cmd_build()   { _require_daemon; hdr "Build des images"; "${DC[@]}" build; }

cmd_rebuild() {
    _require_daemon
    hdr "Rebuild complet (--no-cache)"
    "${DC[@]}" build --no-cache
    "${DC[@]}" up -d
    _wait_healthy
    cmd_seed
    _urls
}

cmd_logs() { _require_daemon; "${DC[@]}" logs -f --tail=120 "$@"; }
cmd_ps()   { _require_daemon; "${DC[@]}" ps; }

cmd_status() {
    _require_daemon
    hdr "Conteneurs"
    "${DC[@]}" ps
    hdr "Santé"
    cmd_health || true
}

cmd_health() {
    local b="DOWN" f="DOWN"
    curl -fsS "http://localhost:${BACKEND_PORT}/health"        >/dev/null 2>&1 && b="UP"
    curl -fsS "http://localhost:${FRONTEND_PORT}/"             >/dev/null 2>&1 && f="UP"
    printf "  backend  (:%s) : %s\n" "${BACKEND_PORT}"  "$([ "$b" = UP ] && info UP || warn DOWN)"
    printf "  frontend (:%s) : %s\n" "${FRONTEND_PORT}" "$([ "$f" = UP ] && info UP || warn DOWN)"
    [ "$b" = UP ]
}

cmd_shell() {
    _require_daemon
    local svc="${1:-backend}"
    hdr "Shell dans '${svc}' (exit pour sortir)"
    "${DC[@]}" exec "${svc}" sh
}

cmd_test() {
    _require_daemon
    hdr "Tests backend (dans le conteneur)"
    "${DC[@]}" exec -T backend python -m pytest tests/ -q
}

cmd_seed() {
    _require_daemon
    hdr "Modèles exemples (rejeu du pipeline sur les datasets démo — idempotent)"
    "${DC[@]}" exec -T backend python seed_examples.py
}

cmd_clean() {
    _require_daemon
    warn "Ceci arrête la stack ET supprime le volume des sessions (sessions.db perdues)."
    read -rp "Confirmer ? [y/N] " ans
    case "${ans}" in
        y|Y|o|O) "${DC[@]}" down -v --remove-orphans; info "Volume supprimé." ;;
        *) info "Annulé." ;;
    esac
}

cmd_help() { sed -n '4,22p' "${ROOT}/mlauto.sh" | sed 's/^# \{0,1\}//'; }

# --- menu interactif ---------------------------------------------------------
_opt()   { printf "  ${GREEN}%2s)${NC} %s\n" "$1" "$2"; }
_pause() { echo; read -rp "  Entree pour continuer..." _; }

show_menu() {
    while true; do
        hdr "mlauto — automation_machine_learning"
        _opt 1  "Up            (build si necessaire + demarrage)"
        _opt 2  "Down          (arret)"
        _opt 3  "Restart"
        _opt 4  "Build"
        _opt 5  "Rebuild       (--no-cache)"
        _opt 6  "Logs"
        _opt 7  "ps            (etat des conteneurs)"
        _opt 8  "Status        (conteneurs + sante)"
        _opt 9  "Health"
        _opt 10 "Shell         (backend)"
        _opt 11 "Test          (suite backend)"
        _opt 12 "Seed          (modeles exemples — rejeu du pipeline, idempotent)"
        _opt 13 "Clean         (DESTRUCTIF — supprime le volume sessions)"
        echo
        _opt 0 "Quitter"
        echo -n "  Choix : "
        local c; read -r c
        case "${c}" in
            1)  cmd_up;      _pause ;;
            2)  cmd_down;    _pause ;;
            3)  cmd_restart; _pause ;;
            4)  cmd_build;   _pause ;;
            5)  cmd_rebuild; _pause ;;
            6)  cmd_logs;    _pause ;;
            7)  cmd_ps;      _pause ;;
            8)  cmd_status;  _pause ;;
            9)  cmd_health;  _pause ;;
            10) cmd_shell;   _pause ;;
            11) cmd_test;    _pause ;;
            12) cmd_seed;    _pause ;;
            13) cmd_clean;   _pause ;;
            0|q|Q) return ;;
            *) warn "choix invalide"; _pause ;;
        esac
    done
}

cmd="${1:-menu}"; shift || true
case "${cmd}" in
    menu)         show_menu ;;
    up|start)     cmd_up ;;
    down|stop)    cmd_down ;;
    restart)      cmd_restart ;;
    build)        cmd_build ;;
    rebuild)      cmd_rebuild ;;
    logs)         cmd_logs "$@" ;;
    ps)           cmd_ps ;;
    status)       cmd_status ;;
    health)       cmd_health ;;
    shell)        cmd_shell "$@" ;;
    test)         cmd_test ;;
    seed)         cmd_seed ;;
    clean)        cmd_clean ;;
    -h|--help|help) cmd_help ;;
    *) err "commande inconnue : ${cmd}"; echo "  voir : ./mlauto.sh help"; exit 1 ;;
esac
