#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# push_gitlab.sh — mirror GitHub `main` to the internal GitLab
# (machine_learning_generator), SANITIZED: no Claude/assistant footprint.
#
# On the internal GitLab, the ONLY acceptable "claude" mention is the LLM
# engine one (Claude as a supported model provider, in backend/ai_providers.py).
# Everything else — the .claude/ config dir, the .claude-plugin/ manifest, hook
# references to CLAUDE.md / .claude/skills, the .dockerignore entry, doc-pointer
# comments, and this mirroring tooling itself — must NOT appear on GitLab.
#
# This builds the mirror in a throwaway git worktree (your working tree is never
# touched), strips all of the above, then HARD-GATES on a scan: if any "claude"
# reference other than backend/ai_providers.py survives, it ABORTS rather than
# risk leaking one. So if a new footprint appears later, this fails loudly
# instead of silently mirroring it.
#
# GitLab `main` is protected (push: No one) — this token cannot push to it. So
# the sanitized commit is force-pushed to an UNPROTECTED side branch
# (default: mirror/main) and the Merge Request URL is printed; a human merges
# it into main.
#
# Auth + target come from .gitlab.env (gitignored, never committed):
#   GITLAB_URL=https://gitlab.cossi.internet/sdo/desc/siq/machine_learning_generator.git
#   GITLAB_USER=oauth2
#   GITLAB_TOKEN=glpat-...
#   GITLAB_MIRROR_BRANCH=mirror/main   # optional, this is the default
# ===========================================================================

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
else
    GREEN=''; YELLOW=''; RED=''; CYAN=''; NC=''
fi
info() { printf "${GREEN}%s${NC}\n" "$*"; }
warn() { printf "${YELLOW}%s${NC}\n" "$*"; }
err()  { printf "${RED}%s${NC}\n" "$*" >&2; }

SOURCE_BRANCH="main"
# The single file allowed to keep a Claude mention (the LLM engine / provider).
ENGINE_FILE="backend/ai_providers.py"

[ -f .gitlab.env ] || { err "Manque .gitlab.env (URL + jeton GitLab). Voir le header du script."; exit 1; }
# shellcheck disable=SC1091
set -a; . ./.gitlab.env; set +a
: "${GITLAB_URL:?GITLAB_URL absent de .gitlab.env}"
: "${GITLAB_TOKEN:?GITLAB_TOKEN absent de .gitlab.env}"
GITLAB_USER="${GITLAB_USER:-oauth2}"
MIRROR_BRANCH="${GITLAB_MIRROR_BRANCH:-mirror/main}"
AUTH_URL="https://${GITLAB_USER}:${GITLAB_TOKEN}@${GITLAB_URL#https://}"
WEB_URL="${GITLAB_URL%.git}"
_redact() { sed "s/${GITLAB_TOKEN}/***REDACTED***/g"; }

git rev-parse --verify "${SOURCE_BRANCH}" >/dev/null 2>&1 \
    || { err "Branche '${SOURCE_BRANCH}' introuvable."; exit 1; }

info "== Miroir GitLab sanitizé (empreinte assistant retirée) =="

# --- throwaway worktree from main; your working tree is untouched -------------
WT="$(mktemp -d)"
cleanup() { git worktree remove --force "${WT}" >/dev/null 2>&1 || true; git worktree prune >/dev/null 2>&1 || true; }
trap cleanup EXIT
git worktree add -q --detach "${WT}" "${SOURCE_BRANCH}"

# --- sanitize: strip the AI-assistant / agent / CI-hook scaffolding ----------
# The GitLab mirror must look like a plain app repo. Remove, wholesale, every
# scaffolding dir tied to the AI-assisted workflow, plus this mirroring tooling.
(
    cd "${WT}"
    rm -rf .claude .claude-plugin .agents .husky .github scripts/push_gitlab.sh
    # .dockerignore: drop entries for the removed scaffolding dirs
    [ -f .dockerignore ] && sed -i '/^\.github$/d; /^\.githooks$/d; /^\.claude$/d; /^\.agents$/d; s|# VCS / agent tooling|# VCS / build tooling|' .dockerignore
    # llm_agent.py: drop the comment pointing at .claude/rules
    [ -f backend/llm_agent.py ] && sed -i '/# voir \.claude\/rules\/prompt-governance\.md\./d' backend/llm_agent.py
    # mlauto.sh: remove the whole push-gitlab command (references .claude)
    if [ -f mlauto.sh ]; then
        sed -i '/# *\.\/mlauto\.sh push-gitlab/d' mlauto.sh
        sed -i '/^cmd_push_gitlab() {/,/^}/d' mlauto.sh
        sed -i '/_opt 14 "Push GitLab/d' mlauto.sh
        sed -i '/14) cmd_push_gitlab;/d' mlauto.sh
        sed -i '/push-gitlab)  cmd_push_gitlab ;;/d' mlauto.sh
        sed -i 's/_opt 15 "Clean/_opt 14 "Clean/; s/15) cmd_clean;/14) cmd_clean;/' mlauto.sh
        # make the help printer range-independent (header lost a line)
        sed -i "s|cmd_help() { sed -n '4,2[0-9]p' \"\${ROOT}/mlauto.sh\" | sed 's/^# \\\\{0,1\\\\}//'; }|cmd_help() { awk 'NR>=4 \&\& /^# ===/{exit} NR>=4{sub(/^# ?/,\"\");print}' \"\${ROOT}/mlauto.sh\"; }|" mlauto.sh
    fi
)

# --- HARD GATE: abort rather than risk leaking any footprint -----------------
# (a) no scaffolding directory survived; (b) no "claude" mention except the
# LLM-engine file. If a new footprint appears upstream, this fails loudly
# instead of silently mirroring it.
scaffolding="$(find "${WT}" -path "${WT}/.git" -prune -o \
    \( -name '.claude*' -o -name '.agents' -o -name '.husky' -o -name '.github' \) -print 2>/dev/null || true)"
if [ -n "${scaffolding}" ]; then
    err "ABANDON — dossier d'échafaudage résiduel :"
    printf '%s\n' "${scaffolding}" | sed "s#^${WT}/##" >&2
    err "Étends la sanitization (rm -rf) avant de mirrorer."
    exit 1
fi
leftover="$(grep -rilE 'claude' "${WT}" --exclude-dir=.git 2>/dev/null \
    | sed "s#^${WT}/##" | grep -vxF "${ENGINE_FILE}" || true)"
if [ -n "${leftover}" ]; then
    err "ABANDON — référence 'claude' résiduelle hors ${ENGINE_FILE} :"
    printf '%s\n' "${leftover}" >&2
    err "Étends la sanitization avant de mirrorer."
    exit 1
fi
info "Garde-fou OK : aucun échafaudage ; seul ${ENGINE_FILE} garde une mention Claude (moteur LLM)."

# --- commit the sanitized tree, parented on the current GitLab main tip -------
GITLAB_TIP="$(git ls-remote "${AUTH_URL}" refs/heads/main 2>/dev/null | cut -f1)"
[ -n "${GITLAB_TIP}" ] || { err "Impossible de lire refs/heads/main sur GitLab."; exit 1; }

TREE="$(git -C "${WT}" write-tree 2>/dev/null || { git -C "${WT}" add -A; git -C "${WT}" write-tree; })"

if [ "${TREE}" = "$(git rev-parse "${GITLAB_TIP}^{tree}")" ]; then
    info "GitLab est déjà à jour (aucun changement à mirrorer)."
    exit 0
fi

COMMIT="$(git -c user.name="Fabrice Pizzi" -c user.email="fabricepizzi@gmail.com" \
    commit-tree "${TREE}" -p "${GITLAB_TIP}" -m "chore: mise à jour depuis l'amont")"

info "Push (force) vers ${MIRROR_BRANCH} sur ${GITLAB_URL} ..."
git push --force "${AUTH_URL}" "${COMMIT}:refs/heads/${MIRROR_BRANCH}" 2>&1 | _redact

printf "\n${CYAN}main est protégée : ouvrez une Merge Request pour intégrer le miroir :${NC}\n"
printf "  %s/-/merge_requests/new?merge_request%%5Bsource_branch%%5D=%s\n" \
    "${WEB_URL}" "${MIRROR_BRANCH//\//%2F}"
info "Branche miroir GitLab à jour (${MIRROR_BRANCH})."
