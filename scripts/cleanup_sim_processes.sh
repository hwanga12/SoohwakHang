#!/usr/bin/env bash

# 이 스크립트는 시뮬레이션 관련 프로세스를 안전하게 정리하기 위해 사용하는 실행용 쉘 스크립트다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/agribot_env.sh"

readonly CLEANUP_GRACE_SECONDS="${CLEANUP_SLEEP_SECONDS:-2}"
readonly CLEANUP_MODULE_PATH="${AGRIBOT_WS}/src/agribot_bringup"

cleanup_scope="user"
session_id="${AGRIBOT_LAUNCH_SESSION_ID:-}"
workspace_path="${AGRIBOT_WS}"

# print_usage 함수가 맡는 단계별 처리를 분리해 스크립트 흐름을 읽기 쉽게 만든다.
print_usage() {
    cat <<'EOF'
Usage: cleanup_sim_processes.sh [--scope user|session] [--session-id <id>] [--workspace-path <path>]

Examples:
  ./scripts/cleanup_sim_processes.sh
  ./scripts/cleanup_sim_processes.sh --scope session --session-id agribot-launch-1234
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --scope)
            cleanup_scope="${2:-}"
            shift 2
            ;;
        --session-id)
            session_id="${2:-}"
            shift 2
            ;;
        --workspace-path)
            workspace_path="${2:-}"
            shift 2
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            print_usage >&2
            exit 2
            ;;
    esac
done

if [[ "${cleanup_scope}" != "user" && "${cleanup_scope}" != "session" ]]; then
    echo "cleanup scope must be 'user' or 'session': ${cleanup_scope}" >&2
    exit 2
fi

if [[ "${cleanup_scope}" == "session" && -z "${session_id}" ]]; then
    exit 0
fi

PYTHONPATH="${CLEANUP_MODULE_PATH}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 -m agribot_bringup.shutdown_cleanup_cli \
        --scope "${cleanup_scope}" \
        --session-id "${session_id}" \
        --workspace-path "${workspace_path}" \
        --grace-period "${CLEANUP_GRACE_SECONDS}"
