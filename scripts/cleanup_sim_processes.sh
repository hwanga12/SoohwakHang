#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/agribot_env.sh" ]]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/agribot_env.sh"
fi

readonly CLEANUP_SLEEP_SECONDS="${CLEANUP_SLEEP_SECONDS:-2}"
readonly PROCESS_PATTERN='ros2 launch .*autonomous_mapping.launch.py|ros2 launch .*mapping.launch.py|ros2 launch .*simulation.launch.py|ros2 launch .*navigation.launch.py|ros2 launch .*mission_manager.launch.py|ros2 launch .*harvest_action_server.launch.py|ros2 launch .*manual_actuation_guard.launch.py|ros2 launch .*iot_status_pipeline.launch.py|gz sim|gzserver|gzclient|gazebo|ign gazebo|ignition-gazebo|rviz2|slam_toolbox|planner_server|controller_server|smoother_server|behavior_server|bt_navigator|waypoint_follower|lifecycle_manager|map_server|amcl|component_container|component_container_mt|nav2_container|collision_monitor|mapping_collision_monitor|frontier_explorer|mapping_patrol_node|parameter_bridge|ros_gz_state_bridge|ros_gz_lidar_bridge|ros_gz_camera_info_bridge|ros_gz_camera_image_bridge|ros_gz_camera_depth_bridge|image_bridge|robot_state_publisher|ekf_node|mapping_ekf_filter|odom_tf_broadcaster|sim_time_guard|runtime_snapshot_exporter|robot_manual_command_executor|mission_bridge_executor|thin_inference_node|startup_map_tf_broadcaster|patrol_node|harvest_route_node|mission_manager|harvest_action_server|manual_actuation_guard_node|environment_sensor_node|watering_controller_node|curtain_controller_node|fan_controller_node|nutrient_controller_node|sprinkler_controller_node|mqtt_bridge_node|cmd_vel_watchdog|static_transform_publisher'
readonly ZOMBIE_PARENT_PATTERN='(agribot|gazebo|gz sim|gzserver|gzclient|rviz2|ros2 launch|ros_gz|nav2|slam_toolbox|robot_state_publisher|ekf_node|sim_time_guard|mission_manager|harvest_action_server|agribot_iot)'
readonly SIM_TIME_GUARD_LOCK="${AGRIBOT_SIM_TIME_GUARD_LOCK:-/tmp/agribot_sim_time_guard.lock}"
readonly RUNTIME_DIR="${AGRIBOT_RUNTIME_DIR:-/tmp/agribot_runtime}"

kill_matching_processes() {
    local signal_name="$1"
    pkill "-${signal_name}" -f "${PROCESS_PATTERN}" 2>/dev/null || true
}

kill_zombie_parents() {
    ps -eo ppid=,stat=,cmd= \
        | awk -v pattern="${ZOMBIE_PARENT_PATTERN}" '
            $2 ~ /^Z/ && $0 ~ pattern { print $1 }
        ' \
        | sort -u \
        | xargs -r kill -KILL 2>/dev/null || true
}

reset_ros_graph_cache() {
    if command -v ros2 >/dev/null 2>&1; then
        ros2 daemon stop >/dev/null 2>&1 || true
    fi
}

clear_runtime_files() {
    mkdir -p "${RUNTIME_DIR}"
    rm -f "${RUNTIME_DIR}"/*.json
}

kill_matching_processes TERM
sleep "${CLEANUP_SLEEP_SECONDS}"
kill_matching_processes KILL
sleep 1
kill_zombie_parents
rm -f "${SIM_TIME_GUARD_LOCK}"
clear_runtime_files
reset_ros_graph_cache
