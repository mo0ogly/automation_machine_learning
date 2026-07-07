#!/usr/bin/env bash
set -euo pipefail
# ===========================================================================
# push_gitlab.sh — mirror the GitHub `main` branch to the internal GitLab
# (machine_learning_generator), MINUS the .claude/ directory.
#
# The internal GitLab must not carry .claude/, while GitHub keeps it tracked.
#
# GitLab `main` is a PROTECTED branch and this token may not push to it (nor
# force-push). So we push to an UNPROTECTED side branch (default: mirror/main)
# and print the URL to open a Merge Request into `main`; a human merges it.
#
# The pushed commit is built with git plumbing so it neither touches your
# working tree nor your index (a throwaway temp index is used):
#   - tree        = GitHub `main`'s tree, with .claude/ stripped out
#   - 1st parent  = current GitLab `main` tip  (so the MR diffs cleanly vs main)
#   - 2nd parent  = GitHub `main`               (links the histories)
# The side branch is force-updated each run (it is a disposable pointer to
# "latest main minus .claude, please merge").
#
# Note: only the *tip* is .claude-free — earlier history mirrored from GitHub
# still holds .claude/ blobs. .claude/ carries only project rules/hooks
# (no secrets), so that is cosmetic.
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

[ -f .gitlab.env ] || { err "Manque .gitlab.env (URL + jeton GitLab). Voir le header du script."; exit 1; }
# shellcheck disable=SC1091
set -a; . ./.gitlab.env; set +a
: "${GITLAB_URL:?GITLAB_URL absent de .gitlab.env}"
: "${GITLAB_TOKEN:?GITLAB_TOKEN absent de .gitlab.env}"
GITLAB_USER="${GITLAB_USER:-oauth2}"
MIRROR_BRANCH="${GITLAB_MIRROR_BRANCH:-mirror/main}"
AUTH_URL="https://${GITLAB_USER}:${GITLAB_TOKEN}@${GITLAB_URL#https://}"
WEB_URL="${GITLAB_URL%.git}"

# Redact the token from anything we print.
_redact() { sed "s/${GITLAB_TOKEN}/***REDACTED***/g"; }

git rev-parse --verify "${SOURCE_BRANCH}" >/dev/null 2>&1 \
    || { err "Branche '${SOURCE_BRANCH}' introuvable."; exit 1; }

info "== Miroir GitLab (main sans .claude) =="

# 1. Current GitLab `main` tip — parent the mirror commit descends from, so the
#    Merge Request shows a clean diff against main.
info "Lecture du tip GitLab ..."
GITLAB_TIP="$(git ls-remote "${AUTH_URL}" refs/heads/main 2>/dev/null | cut -f1)"
[ -n "${GITLAB_TIP}" ] || { err "Impossible de lire refs/heads/main sur GitLab (auth ? branche absente ?)."; exit 1; }

# 2. Target tree = main's tree minus .claude/, in a throwaway index (working
#    tree / real index untouched).
TMP_INDEX="$(mktemp)"
trap 'rm -f "${TMP_INDEX}"' EXIT
GIT_INDEX_FILE="${TMP_INDEX}" git read-tree "${SOURCE_BRANCH}"
GIT_INDEX_FILE="${TMP_INDEX}" git rm -r --cached --quiet --ignore-unmatch .claude
TREE="$(GIT_INDEX_FILE="${TMP_INDEX}" git write-tree)"

# 3. Nothing to do if GitLab main already holds this exact tree.
if [ "${TREE}" = "$(git rev-parse "${GITLAB_TIP}^{tree}")" ]; then
    info "GitLab est déjà à jour (aucun changement à mirrorer)."
    exit 0
fi

removed="$(git ls-tree -r --name-only "${SOURCE_BRANCH}" -- .claude | wc -l)"
info ".claude retiré du miroir : ${removed} fichiers"

# 4. Mirror commit on top of GitLab main, force-pushed to the side branch.
COMMIT="$(git commit-tree "${TREE}" -p "${GITLAB_TIP}" -p "${SOURCE_BRANCH}" \
    -m "chore(gitlab): miroir de main sans .claude")"

info "Push (force) vers ${MIRROR_BRANCH} sur ${GITLAB_URL} ..."
git push --force "${AUTH_URL}" "${COMMIT}:refs/heads/${MIRROR_BRANCH}" 2>&1 | _redact

printf "\n${CYAN}main est protégée : ouvrez une Merge Request pour intégrer le miroir :${NC}\n"
printf "  %s/-/merge_requests/new?merge_request%%5Bsource_branch%%5D=%s\n" \
    "${WEB_URL}" "${MIRROR_BRANCH//\//%2F}"
info "Branche miroir GitLab à jour (${MIRROR_BRANCH})."
