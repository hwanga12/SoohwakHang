#!/usr/bin/env bash

# 이 스크립트는 미션 매니저 노드를 실행하기 위해 사용하는 실행용 쉘 스크립트다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/agribot_env.sh"

ROS_SETUP="/opt/ros/${ROS_DISTRO}/setup.bash"
WS_SETUP="${AGRIBOT_WS}/install/setup.bash"

if [[ ! -f "${ROS_SETUP}" ]]; then
    echo "ROS setup not found: ${ROS_SETUP}" >&2
    exit 1
fi

if [[ ! -f "${WS_SETUP}" ]]; then
    echo "Workspace setup not found: ${WS_SETUP}" >&2
    exit 1
fi

source_ros_setup_files

if command -v pgrep >/dev/null 2>&1; then
    while read -r pid cmdline; do
        [[ -z "${pid:-}" ]] && continue
        if [[ "${cmdline}" == *"ros2 launch agribot_control mission_manager.launch.py"* ]] \
            || [[ "${cmdline}" == *"/agribot_control/lib/agribot_control/mission_manager"* ]]; then
            kill "${pid}" 2>/dev/null || true
        fi
    done < <(pgrep -af 'ros2 launch agribot_control mission_manager.launch.py|/agribot_control/lib/agribot_control/mission_manager' || true)
fi

export AGRIBOT_RUNTIME_DIR
echo "Using AGRIBOT_RUNTIME_DIR=${AGRIBOT_RUNTIME_DIR}"
# 마지막에는 현재 셸을 실제 서비스 프로세스로 교체해 종료 신호가 곧바로 전달되게 한다.
exec ros2 launch agribot_control mission_manager.launch.py "runtime_dir:=${AGRIBOT_RUNTIME_DIR}"
