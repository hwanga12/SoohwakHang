#!/usr/bin/env bash

# 이 스크립트는 프론트엔드 개발 서버를 실행하기 위해 사용하는 실행용 쉘 스크립트다.
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
# 마지막에는 현재 셸을 실제 서비스 프로세스로 교체해 종료 신호가 곧바로 전달되게 한다.
exec npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}" --strictPort
