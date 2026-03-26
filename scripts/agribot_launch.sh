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

cleanup_process_group() {
    if [[ -z "${child_pid}" ]]; then
        return
    fi

    if kill -0 "${child_pid}" 2>/dev/null; then
        kill -TERM "-${child_pid}" 2>/dev/null || kill -TERM "${child_pid}" 2>/dev/null || true
        sleep "${SHUTDOWN_WAIT_SECONDS}"
        kill -KILL "-${child_pid}" 2>/dev/null || kill -KILL "${child_pid}" 2>/dev/null || true
    fi
}

cleanup_once() {
    if (( cleanup_done )); then
        return
    fi

    cleanup_done=1
    cleanup_process_group
    "${CLEANUP_SCRIPT}" >/dev/null 2>&1 || true
}

forward_signal_and_exit() {
    local signal_name="$1"
    local exit_code="$2"

    if [[ -n "${child_pid}" ]]; then
        kill "-${signal_name}" "-${child_pid}" 2>/dev/null || kill "-${signal_name}" "${child_pid}" 2>/dev/null || true
    fi

    exit "${exit_code}"
}

trap 'forward_signal_and_exit INT 130' INT
trap 'forward_signal_and_exit TERM 143' TERM
trap cleanup_once EXIT

maybe_source_ros_env
export AGRIBOT_RUNTIME_DIR
echo "Using AGRIBOT_RUNTIME_DIR=${AGRIBOT_RUNTIME_DIR}"

"${CLEANUP_SCRIPT}" >/dev/null 2>&1 || true

mapfile -d '' -t launch_args < <(append_runtime_arg_if_supported "$@")

setsid ros2 launch "${launch_args[@]}" &
child_pid=$!

set +e
wait "${child_pid}"
launch_exit_code=$?
set -e

exit "${launch_exit_code}"
