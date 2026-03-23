#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

"${CLEANUP_SCRIPT}" >/dev/null 2>&1 || true

setsid ros2 launch "$@" &
child_pid=$!

set +e
wait "${child_pid}"
launch_exit_code=$?
set -e

exit "${launch_exit_code}"
