#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# push_gitlab.sh — mirror the GitHub `main` branch to the internal GitLab
# (machine_learning_generator), MINUS the .claude/ directory.
#
# The internal GitLab must not carry .claude/, while GitHub keeps it tracked.
# Rather than maintain a hand-rebased divergent branch, this rebuilds a
# throwaway mirror branch from `main` on every run:
#   1. branch off the current `main`
#   2. untrack ALL of .claude/ (git rm -r --cached — files stay on disk)
#   3. make sure .claude/ is gitignored on that branch
#   4. one commit, force-push it to GitLab `main`
# Rebuilding from scratch each time is robust: it strips whatever .claude/
# files exist now, not just the ones that existed when a static branch was cut.
#
# Note: this strips .claude/ from the *tip* (what you see browsing the repo).
# Past commits mirrored from GitHub still contain .claude/ blobs in history;
# .claude/ holds only project rules/hooks (no secrets), so that is cosmetic.
#
# Auth + target come from .gitlab.env (gitignored, never committed):
#   GITLAB_URL=https://gitlab.cossi.internet/sdo/desc/siq/machine_learning_generator.git
#   GITLAB_USER=oauth2
#   GITLAB_TOKEN=glpat-...
# ===========================================================================

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
else
    GREEN=''; YELLOW=''; RED=''; NC=''
fi
info() { printf "${GREEN}%s${NC}\n" "$*"; }
warn() { printf "${YELLOW}%s${NC}\n" "$*"; }
err()  { printf "${RED}%s${NC}\n" "$*" >&2; }

MIRROR_BRANCH="_gitlab_mirror"
SOURCE_BRANCH="main"

[ -f .gitlab.env ] || { err "Manque .gitlab.env (URL + jeton GitLab). Voir le header du script."; exit 1; }
# shellcheck disable=SC1091
set -a; . ./.gitlab.env; set +a
: "${GITLAB_URL:?GITLAB_URL absent de .gitlab.env}"
: "${GITLAB_TOKEN:?GITLAB_TOKEN absent de .gitlab.env}"
GITLAB_USER="${GITLAB_USER:-oauth2}"

# Redact the token from anything we print.
_redact() { sed "s/${GITLAB_TOKEN}/***REDACTED***/g"; }

# Refuse to run on a dirty tree — we switch branches, which would clobber it.
if [ -n "$(git status --porcelain)" ]; then
    err "Arbre de travail non propre. Committez / stashez avant de mirrorer vers GitLab."
    exit 1
fi

git rev-parse --verify "${SOURCE_BRANCH}" >/dev/null 2>&1 \
    || { err "Branche '${SOURCE_BRANCH}' introuvable."; exit 1; }

START_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
cleanup() {
    git checkout -q "${START_BRANCH}" 2>/dev/null || true
    git branch -D "${MIRROR_BRANCH}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

info "== Miroir GitLab (main sans .claude) =="

# 1-2. Fresh mirror branch from main, drop .claude/ from the index (kept on disk).
git branch -f "${MIRROR_BRANCH}" "${SOURCE_BRANCH}"
git checkout -q "${MIRROR_BRANCH}"
git rm -r --cached --quiet .claude >/dev/null 2>&1 || true

# 3. Ensure .claude/ is ignored on this branch (so it is never re-added).
grep -qxF '.claude/' .gitignore 2>/dev/null \
    || printf '\n# ─── Exclu du miroir GitLab interne ───────────────────────\n.claude/\n' >> .gitignore
git add .gitignore

# 4. Single exclusion commit + force-push to GitLab main.
git commit -q -m "chore(gitlab): exclut .claude du miroir GitLab interne"
removed="$(git -C "${ROOT}" diff --name-only "${SOURCE_BRANCH}" "${MIRROR_BRANCH}" -- .claude | wc -l)"
info ".claude retire du miroir : ${removed} fichiers"

info "Push vers ${GITLAB_URL} (force) ..."
git push --force \
    "https://${GITLAB_USER}:${GITLAB_TOKEN}@${GITLAB_URL#https://}" \
    "${MIRROR_BRANCH}:main" 2>&1 | _redact

info "Miroir GitLab a jour."
