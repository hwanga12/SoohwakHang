#!/usr/bin/env bash

# 이 스크립트는 ROS 2 런치 파일을 공통 환경과 정리 규칙에 맞춰 실행하기 위해 사용하는 실행용 쉘 스크립트다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/agribot_env.sh"
readonly CLEANUP_SCRIPT="${SCRIPT_DIR}/cleanup_sim_processes.sh"
readonly SHUTDOWN_WAIT_SECONDS="${SHUTDOWN_WAIT_SECONDS:-2}"

if [[ $# -lt 2 ]]; then
    echo "Usage: $(basename "$0") <package> <launch_file> [launch_args...]" >&2
    exit 2
fi

if ! command -v setsid >/dev/null 2>&1; then
    echo "setsid command is required but not installed." >&2
    exit 1
fi

child_pid=""
cleanup_done=0

# ROS 환경 파일을 필요한 시점에만 불러와 이후 명령이 공통 환경을 공유하게 만든다.
maybe_source_ros_env() {
    source_ros_setup_files
}

# 현재 실행 세션을 식별할 수 있는 ID를 준비해 정리 대상을 안전하게 좁힌다.
ensure_launch_session_id() {
    if [[ -n "${AGRIBOT_LAUNCH_SESSION_ID:-}" ]]; then
        export AGRIBOT_LAUNCH_SESSION_ID
        return
    fi

    export AGRIBOT_LAUNCH_SESSION_ID="agribot-launch-$(date +%s)-$$"
}

# 런치 파일이 runtime_dir 인자를 지원하는지 확인해 불필요한 인자 주입을 피한다.
launch_file_supports_runtime_arg() {
    local package_name="$1"
    local launch_file="$2"
    local launch_path="${AGRIBOT_WS}/src/${package_name}/launch/${launch_file}"

    [[ -f "${launch_path}" ]] || return 1
    if command -v rg >/dev/null 2>&1; then
        rg -q "DeclareLaunchArgument\\([[:space:]\n\r]*['\"]runtime_dir['\"]" "${launch_path}"
        return
    fi

    grep -q "runtime_dir" "${launch_path}"
}

# 지원되는 런치 파일에만 runtime_dir 인자를 덧붙여 런타임 기록 위치를 맞춘다.
append_runtime_arg_if_supported() {
    local package_name="$1"
    local launch_file="$2"
    local arg

    for arg in "$@"; do
        if [[ "${arg}" == runtime_dir:=* ]]; then
            return
        fi
    done

    if launch_file_supports_runtime_arg "${package_name}" "${launch_file}"; then
        set -- "$@" "runtime_dir:=${AGRIBOT_RUNTIME_DIR}"
    fi

    printf '%s\0' "$@"
}

# 종료 시 같은 정리 절차가 여러 번 실행되지 않도록 한 번만 정리한다.
cleanup_once() {
    if (( cleanup_done )); then
        return
    fi

    cleanup_done=1
    "${CLEANUP_SCRIPT}" \
        --scope session \
        --session-id "${AGRIBOT_LAUNCH_SESSION_ID:-}" \
        >/dev/null 2>&1 || true
    # 세션 태그를 놓친 orphan 프로세스가 남더라도,
    # AgriBot 워크스페이스/허용 목록에 해당하는 프로세스만 추가 정리한다.
    "${CLEANUP_SCRIPT}" \
        --scope user \
        --workspace-path "${AGRIBOT_WS}" \
        >/dev/null 2>&1 || true
}

# forward_signal_and_exit 함수가 맡는 단계별 처리를 분리해 스크립트 흐름을 읽기 쉽게 만든다.
forward_signal_and_exit() {
    local exit_code="$1"
    local signal_name="$2"

    if [[ -n "${child_pid}" ]]; then
        # setsid 로 띄운 ros2 launch 세션 전체에만 신호를 전달한다.
        kill -s "${signal_name}" -- "-${child_pid}" >/dev/null 2>&1 || \
            kill -s "${signal_name}" "${child_pid}" >/dev/null 2>&1 || true
        sleep "${SHUTDOWN_WAIT_SECONDS}"
    fi

    cleanup_once
    trap - EXIT
    exit "${exit_code}"
}

trap 'forward_signal_and_exit 130 INT' INT
trap 'forward_signal_and_exit 143 TERM' TERM
trap cleanup_once EXIT

maybe_source_ros_env
export AGRIBOT_RUNTIME_DIR
echo "Using AGRIBOT_RUNTIME_DIR=${AGRIBOT_RUNTIME_DIR}"

"${CLEANUP_SCRIPT}" --scope user >/dev/null 2>&1 || true
ensure_launch_session_id
echo "Using AGRIBOT_LAUNCH_SESSION_ID=${AGRIBOT_LAUNCH_SESSION_ID}"

mapfile -d '' -t launch_args < <(append_runtime_arg_if_supported "$@")

setsid ros2 launch "${launch_args[@]}" &
child_pid=$!

set +e
wait "${child_pid}"
launch_exit_code=$?
set -e

if [[ "${launch_exit_code}" -eq 130 || "${launch_exit_code}" -eq 143 ]]; then
    sleep "${SHUTDOWN_WAIT_SECONDS}"
fi

exit "${launch_exit_code}"
