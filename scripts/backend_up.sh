#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/agribot_env.sh"

BACKEND_DIR="${REPO_ROOT}/backend"
PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Backend venv not found: ${PYTHON_BIN}" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker command is required but not installed." >&2
    exit 1
fi

docker compose -f "${BACKEND_DIR}/docker-compose.yml" up -d postgres mosquitto pgadmin

if command -v pgrep >/dev/null 2>&1; then
    while read -r pid cmdline; do
        [[ -z "${pid:-}" ]] && continue
        if [[ "${cmdline}" == *"uvicorn main:app"* ]]; then
            kill "${pid}" 2>/dev/null || true
        fi
    done < <(pgrep -af "uvicorn main:app" || true)
fi

if command -v lsof >/dev/null 2>&1; then
    while read -r pid; do
        [[ -z "${pid:-}" ]] && continue
        kill "${pid}" 2>/dev/null || true
    done < <(lsof -t -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN 2>/dev/null | sort -u || true)
fi

cd "${BACKEND_DIR}"
export AGRIBOT_RUNTIME_DIR
export AGRIBOT_BACKEND_RUNTIME_DIR
export AGRIBOT_TREATMENT_DISPATCH_MIN_SUBSCRIBERS="${AGRIBOT_TREATMENT_DISPATCH_MIN_SUBSCRIBERS:-1}"
echo "Using AGRIBOT_RUNTIME_DIR=${AGRIBOT_RUNTIME_DIR}"
echo "Using AGRIBOT_BACKEND_RUNTIME_DIR=${AGRIBOT_BACKEND_RUNTIME_DIR}"
echo "Using AGRIBOT_TREATMENT_DISPATCH_MIN_SUBSCRIBERS=${AGRIBOT_TREATMENT_DISPATCH_MIN_SUBSCRIBERS}"
exec "${PYTHON_BIN}" -m uvicorn main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}"
