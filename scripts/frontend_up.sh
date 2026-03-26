#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/agribot_env.sh"

FRONTEND_DIR="${REPO_ROOT}/frontend"

cd "${FRONTEND_DIR}"
exec npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}"
