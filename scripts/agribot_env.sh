#!/usr/bin/env bash

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    echo "This script must be sourced: source scripts/agribot_env.sh" >&2
    exit 1
fi

_AGRIBOT_ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_AGRIBOT_REPO_ROOT="$(cd "${_AGRIBOT_ENV_DIR}/.." && pwd)"

export REPO_ROOT="${REPO_ROOT:-${_AGRIBOT_REPO_ROOT}}"
export AGRIBOT_WS="${AGRIBOT_WS:-${REPO_ROOT}/agribot_ws}"
export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
export AGRIBOT_RUNTIME_DIR="${AGRIBOT_RUNTIME_DIR:-/tmp/agribot_runtime}"
export AGRIBOT_BACKEND_RUNTIME_DIR="${AGRIBOT_BACKEND_RUNTIME_DIR:-${REPO_ROOT}/artifacts/runtime/backend}"
export AGRIBOT_PERCEPTION_PYTHON="${AGRIBOT_PERCEPTION_PYTHON:-${REPO_ROOT}/backend/.venv/bin/python}"
export BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
export FRONTEND_PORT="${FRONTEND_PORT:-5173}"

source_file_without_strict_nounset() {
    local target_file="$1"
    local restore_errexit=0
    local restore_nounset=0
    local rc=0

    if [[ ! -f "${target_file}" ]]; then
        echo "Required setup file not found: ${target_file}" >&2
        return 1
    fi

    case "$-" in
        *e*) restore_errexit=1 ;;
    esac
    case "$-" in
        *u*) restore_nounset=1 ;;
    esac

    (( restore_errexit )) && set +e
    (( restore_nounset )) && set +u

    # shellcheck disable=SC1090
    source "${target_file}"
    rc=$?

    (( restore_nounset )) && set -u
    (( restore_errexit )) && set -e

    return "${rc}"
}

source_ros_setup_files() {
    local ros_setup="/opt/ros/${ROS_DISTRO}/setup.bash"
    local ws_setup="${AGRIBOT_WS}/install/setup.bash"

    source_file_without_strict_nounset "${ros_setup}" || return 1
    source_file_without_strict_nounset "${ws_setup}" || return 1
}

unset _AGRIBOT_ENV_DIR
unset _AGRIBOT_REPO_ROOT
