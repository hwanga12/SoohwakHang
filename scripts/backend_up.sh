#!/usr/bin/env bash

# 이 스크립트는 백엔드 서버를 실행하기 위해 사용하는 실행용 쉘 스크립트다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/agribot_env.sh"

BACKEND_DIR="${REPO_ROOT}/backend"
PYTHON_BIN="${BACKEND_DIR}/.venv/bin/python"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

# 실행에 필요한 바이너리나 가상환경이 준비되지 않았으면 바로 중단해 뒤늦은 실패를 막는다.
if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "Backend venv not found: ${PYTHON_BIN}" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker command is required but not installed." >&2
    exit 1
fi

# 백엔드가 의존하는 외부 서비스부터 먼저 올려 API 실행 시 연결 오류가 나지 않게 한다.
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
# 마지막에는 현재 셸을 실제 서비스 프로세스로 교체해 종료 신호가 곧바로 전달되게 한다.
exec "${PYTHON_BIN}" -m uvicorn main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}"
