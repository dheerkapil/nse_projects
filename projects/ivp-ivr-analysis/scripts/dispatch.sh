#!/usr/bin/env bash
#
# Trigger the daily IVP/IVR workflow immediately, bypassing GitHub's
# scheduled-run delay (see docs/external-trigger.md).
#
# Usage:
#   GH_TOKEN=github_pat_xxx bash scripts/dispatch.sh
#
# GH_TOKEN must be a fine-grained PAT with "Actions: Read and write" on this
# repository. Never hard-code the token here.

set -euo pipefail

: "${GH_TOKEN:?set GH_TOKEN to a fine-grained PAT with Actions:write on this repo}"

REPO="dheerkapil/ivp-ivr-analysis"
WORKFLOW="daily_update.yml"

status=$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  "https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches" \
  -d '{"ref":"main"}')

echo "HTTP ${status}"
case "$status" in
  204) echo "✅ Dispatch accepted — check the repo's Actions tab." ;;
  401|403) echo "❌ Token missing or lacks Actions:write permission." ;;
  404) echo "❌ Repo/workflow not found for this token." ;;
  *) echo "❌ Unexpected response." ;;
esac
