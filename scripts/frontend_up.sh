#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/agribot_env.sh"

FRONTEND_DIR="${REPO_ROOT}/frontend"

if command -v lsof >/dev/null 2>&1; then
    while read -r pid; do
        [[ -z "${pid:-}" ]] && continue
        kill "${pid}" 2>/dev/null || true
    done < <(lsof -t -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN 2>/dev/null | sort -u || true)
fi

cd "${FRONTEND_DIR}"
exec npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}" --strictPort
