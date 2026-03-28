#!/usr/bin/env bash

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

maybe_source_ros_env() {
    source_ros_setup_files
}

ensure_launch_session_id() {
    if [[ -n "${AGRIBOT_LAUNCH_SESSION_ID:-}" ]]; then
        export AGRIBOT_LAUNCH_SESSION_ID
        return
    fi

    export AGRIBOT_LAUNCH_SESSION_ID="agribot-launch-$(date +%s)-$$"
}

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

cleanup_once() {
    if (( cleanup_done )); then
        return
    fi

    cleanup_done=1
    "${CLEANUP_SCRIPT}" \
        --scope session \
        --session-id "${AGRIBOT_LAUNCH_SESSION_ID:-}" \
        >/dev/null 2>&1 || true
}

forward_signal_and_exit() {
    exit "$1"
}

trap 'forward_signal_and_exit 130' INT
trap 'forward_signal_and_exit 143' TERM
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
