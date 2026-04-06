#!/usr/bin/env bash

# 이 스크립트는 AgriBot 워크스페이스 실행에 필요한 환경 변수를 준비하기 위해 사용하는 실행용 쉘 스크립트다.
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
# 기본 실행은 저장소가 특정 GPU를 강제하지 않고 호스트 세션의 기본 그래픽 경로를 따른다.
export AGRIBOT_GRAPHICS_PROFILE="${AGRIBOT_GRAPHICS_PROFILE:-system}"
export AGRIBOT_PERFORMANCE_MODE="${AGRIBOT_PERFORMANCE_MODE:-balanced}"
export AGRIBOT_ROS_DISCOVERY_RANGE="${AGRIBOT_ROS_DISCOVERY_RANGE:-LOCALHOST}"
export AGRIBOT_GZ_IP="${AGRIBOT_GZ_IP:-127.0.0.1}"
export ROS_AUTOMATIC_DISCOVERY_RANGE="${AGRIBOT_ROS_DISCOVERY_RANGE}"
export GZ_IP="${AGRIBOT_GZ_IP}"
export AGRIBOT_BACKEND_RUNTIME_DIR="${AGRIBOT_BACKEND_RUNTIME_DIR:-${REPO_ROOT}/artifacts/runtime/backend}"
export AGRIBOT_PERCEPTION_PYTHON="${AGRIBOT_PERCEPTION_PYTHON:-${REPO_ROOT}/backend/.venv/bin/python}"
export BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
export BACKEND_PORT="${BACKEND_PORT:-8000}"
export FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
export FRONTEND_PORT="${FRONTEND_PORT:-5173}"
export AGRIBOT_GZ_PARTITION="${AGRIBOT_GZ_PARTITION:-agribot_${USER:-local}_sim}"
export GZ_PARTITION="${GZ_PARTITION:-${AGRIBOT_GZ_PARTITION}}"
export GZ_IP="${GZ_IP:-127.0.0.1}"
export IGN_IP="${IGN_IP:-127.0.0.1}"
# Keep the local ROS graph isolated from other stacks on the same network.
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
# Prefer the Jazzy-era discovery env var and avoid exporting the deprecated one
# unless the caller explicitly set it before sourcing this script.
if [[ -n "${ROS_LOCALHOST_ONLY:-}" ]]; then
    export ROS_LOCALHOST_ONLY
else
    unset ROS_LOCALHOST_ONLY 2>/dev/null || true
fi

# source_file_without_strict_nounset 함수가 맡는 단계별 처리를 분리해 스크립트 흐름을 읽기 쉽게 만든다.
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

# source_ros_setup_files 함수가 맡는 단계별 처리를 분리해 스크립트 흐름을 읽기 쉽게 만든다.
source_ros_setup_files() {
    local ros_setup="/opt/ros/${ROS_DISTRO}/setup.bash"
    local ws_setup="${AGRIBOT_WS}/install/setup.bash"

    source_file_without_strict_nounset "${ros_setup}" || return 1
    source_file_without_strict_nounset "${ws_setup}" || return 1
}

source_ros_setup_files || return 1

unset _AGRIBOT_ENV_DIR
unset _AGRIBOT_REPO_ROOT
