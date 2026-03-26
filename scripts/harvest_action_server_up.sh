#!/usr/bin/env bash

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

export AGRIBOT_RUNTIME_DIR
echo "Using AGRIBOT_RUNTIME_DIR=${AGRIBOT_RUNTIME_DIR}"
exec ros2 launch agribot_navigation harvest_action_server.launch.py "runtime_dir:=${AGRIBOT_RUNTIME_DIR}"
