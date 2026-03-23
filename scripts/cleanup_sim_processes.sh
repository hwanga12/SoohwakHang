#!/usr/bin/env bash

set -euo pipefail

readonly CLEANUP_SLEEP_SECONDS="${CLEANUP_SLEEP_SECONDS:-2}"
readonly PROCESS_PATTERN='ros2 launch .*autonomous_mapping.launch.py|ros2 launch .*mapping.launch.py|ros2 launch .*simulation.launch.py|ros2 launch .*navigation.launch.py|gz sim|gzserver|gzclient|gazebo|ign gazebo|ignition-gazebo|rviz2|slam_toolbox|planner_server|controller_server|smoother_server|behavior_server|bt_navigator|waypoint_follower|lifecycle_manager|map_server|amcl|component_container|component_container_mt|nav2_container|collision_monitor|mapping_collision_monitor|frontier_explorer|mapping_patrol_node|parameter_bridge|ros_gz_state_bridge|ros_gz_lidar_bridge|ros_gz_camera_info_bridge|ros_gz_camera_image_bridge|ros_gz_camera_depth_bridge|image_bridge|robot_state_publisher|ekf_node|mapping_ekf_filter|odom_tf_broadcaster|cmd_vel_watchdog|static_transform_publisher'
readonly ZOMBIE_PARENT_PATTERN='(agribot|gazebo|gz sim|gzserver|gzclient|rviz2|ros2 launch|ros_gz|nav2|slam_toolbox|robot_state_publisher|ekf_node)'

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

kill_matching_processes TERM
sleep "${CLEANUP_SLEEP_SECONDS}"
kill_matching_processes KILL
sleep 1
kill_zombie_parents
