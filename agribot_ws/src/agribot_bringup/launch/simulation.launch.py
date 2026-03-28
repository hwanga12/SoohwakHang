"""
AgriBot Simulation Launch File
Brings up the complete simulation environment including:
- Gazebo Harmonic world
- Robot model spawn
- ROS-Gazebo bridge
- Nav2
- IoT status/result publishing stack

Usage:
    ros2 launch agribot_bringup simulation.launch.py
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_prefix, get_package_share_directory
import os
import sys
from pathlib import Path
import re


try:
    from agribot_bringup.launch_profile import (
        build_launch_session_environment_actions,
        resolve_performance_defaults,
    )
    from agribot_bringup.shutdown_cleanup import (
        build_shutdown_cleanup_handler,
        ensure_launch_session_id_env,
        resolve_launch_session_id,
    )
except ModuleNotFoundError:
    bringup_package_root = Path(__file__).resolve().parents[1]
    if str(bringup_package_root) not in sys.path:
        sys.path.append(str(bringup_package_root))
    from agribot_bringup.launch_profile import (
        build_launch_session_environment_actions,
        resolve_performance_defaults,
    )
    from agribot_bringup.shutdown_cleanup import (
        build_shutdown_cleanup_handler,
        ensure_launch_session_id_env,
        resolve_launch_session_id,
    )


def generate_launch_description():
    runtime_dir = LaunchConfiguration('runtime_dir')
    simulation_defaults = resolve_performance_defaults('simulation')
    spawn_defaults = resolve_performance_defaults('spawn')
    runtime_support_defaults = resolve_performance_defaults('runtime_support')
    launch_session_id = ensure_launch_session_id_env(resolve_launch_session_id())
    gz_partition = f'agribot_sim_{_sanitize_gz_partition_suffix(launch_session_id)}'
    gz_args_prefix = LaunchConfiguration('gz_args_prefix')
    use_rviz = LaunchConfiguration('use_rviz')
    agribot_interfaces_site_packages = os.path.join(
        get_package_prefix('agribot_interfaces'),
        'lib',
        f'python{sys.version_info.major}.{sys.version_info.minor}',
        'site-packages',
    )
    
    # Environment variables
    env_vars = [
        *build_launch_session_environment_actions(launch_session_id),
        SetEnvironmentVariable('GZ_PARTITION', gz_partition),
        SetEnvironmentVariable('AGRIBOT_RUNTIME_DIR', runtime_dir),
        # Ensure agribot_interfaces python bindings are found
        SetEnvironmentVariable(
            'PYTHONPATH', 
            agribot_interfaces_site_packages +
            ':' + os.environ.get('PYTHONPATH', '')
        ),
    ]
    shutdown_cleanup_handler = build_shutdown_cleanup_handler(launch_session_id)

    # Include the robot spawn launch file
    spawn_agribot = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('agribot_description'),
                'launch',
                'spawn_agribot.launch.py'
            )
        ),
        launch_arguments={
            'gz_args_prefix': gz_args_prefix,
            'gz_partition': gz_partition,
            'use_camera_bridges': LaunchConfiguration('use_camera_bridges'),
            'cmd_vel_watchdog_publish_rate_hz': LaunchConfiguration(
                'cmd_vel_watchdog_publish_rate_hz'
            ),
            # simulation 시연에서는 고정 identity map -> odom 이 더 안정적으로
            # 유지되어 Nav2가 TF 시간 외삽 오류 없이 접근 주행을 시작한다.
            'publish_map_to_odom_tf': 'true',
        }.items(),
    )

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('agribot_navigation'),
                'launch',
                'navigation.launch.py'
            )
        ),
        launch_arguments={
            'use_sim_time': 'true',
            'use_rviz': use_rviz,
            'patrol_robot_pose_topic': '/odom',
            'gz_partition': gz_partition,
            'use_startup_map_tf_broadcaster': 'false',
        }.items()
    )
    gz_args_prefix_arg = DeclareLaunchArgument(
        'gz_args_prefix',
        default_value=simulation_defaults['gz_args_prefix'],
        description='Arguments passed to gz sim before the world path.',
    )
    use_iot_arg = DeclareLaunchArgument(
        'use_iot',
        default_value=simulation_defaults['use_iot'],
        description='Launch the IoT status/result publishing stack.',
    )
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value=simulation_defaults['use_rviz'],
        description='Launch RViz alongside Nav2.',
    )
    use_camera_bridges_arg = DeclareLaunchArgument(
        'use_camera_bridges',
        default_value=spawn_defaults['use_camera_bridges'],
        description='Launch Gazebo RGB-D camera bridges.',
    )
    cmd_vel_watchdog_publish_rate_arg = DeclareLaunchArgument(
        'cmd_vel_watchdog_publish_rate_hz',
        default_value=spawn_defaults['cmd_vel_watchdog_publish_rate_hz'],
        description='Publish rate for the cmd_vel watchdog forwarder.',
    )
    runtime_dir_arg = DeclareLaunchArgument(
        'runtime_dir',
        default_value=EnvironmentVariable('AGRIBOT_RUNTIME_DIR', default_value='/tmp/agribot_runtime'),
        description='Shared runtime directory for backend file bridge and ROS executors.',
    )
    use_perception_arg = DeclareLaunchArgument(
        'use_perception',
        default_value=simulation_defaults['use_perception'],
        description='Launch the thin inference pipeline that forwards snapshots to the backend.',
    )
    use_runtime_support_arg = DeclareLaunchArgument(
        'use_runtime_support',
        default_value=simulation_defaults['use_runtime_support'],
        description='Launch runtime snapshot and file-bridge helper executors.',
    )
    pose_write_period_arg = DeclareLaunchArgument(
        'pose_write_period_sec',
        default_value=runtime_support_defaults['pose_write_period_sec'],
        description='Pose snapshot write period for runtime_snapshot_exporter.',
    )
    semantic_write_period_arg = DeclareLaunchArgument(
        'semantic_write_period_sec',
        default_value=runtime_support_defaults['semantic_write_period_sec'],
        description='Semantic snapshot write period for runtime_snapshot_exporter.',
    )
    robot_command_poll_period_arg = DeclareLaunchArgument(
        'robot_command_poll_period_sec',
        default_value=runtime_support_defaults['robot_command_poll_period_sec'],
        description='File poll period for robot_manual_command_executor.',
    )
    mission_command_poll_period_arg = DeclareLaunchArgument(
        'mission_command_poll_period_sec',
        default_value=runtime_support_defaults['mission_command_poll_period_sec'],
        description='File poll period for mission_bridge_executor.',
    )
    backend_confirm_url_arg = DeclareLaunchArgument(
        'backend_confirm_url',
        default_value='http://127.0.0.1:8000/api/v1/inference/confirm',
        description='FastAPI endpoint used by thin inference for backend confirmation.',
    )
    mqtt_force_log_only_arg = DeclareLaunchArgument(
        'mqtt_force_log_only',
        default_value='false',
        description='Force the MQTT bridge into log-only mode.',
    )
    iot_status_pipeline = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('agribot_iot'),
                'launch',
                'iot_status_pipeline.launch.py'
            )
        ),
        launch_arguments={
            'use_sim_time': 'true',
            'force_log_only': LaunchConfiguration('mqtt_force_log_only'),
        }.items(),
        condition=IfCondition(LaunchConfiguration('use_iot')),
    )
    perception = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('agribot_perception'),
                'launch',
                'perception.launch.py'
            )
        ),
        launch_arguments={
            'use_sim_time': 'true',
            'backend_confirm_url': LaunchConfiguration('backend_confirm_url'),
        }.items(),
        condition=IfCondition(LaunchConfiguration('use_perception')),
    )

    delayed_navigation = TimerAction(
        # GUI 세션에서는 Gazebo와 bridge가 안정화되기 전에 Nav2가 먼저 뜨면
        # 초기 costmap/TF 타임아웃으로 첫 명령이 묻히는 경우가 있다.
        period=10.0,
        actions=[navigation],
    )
    unpause_world = TimerAction(
        # gz sim -r 이어도 GUI 붙는 시점에 world가 paused 상태로 남는 경우가 있어
        # 실제 주행 시작 전 한 번 더 run 상태를 강제한다.
        period=3.0,
        actions=[
            ExecuteProcess(
                cmd=[
                    'bash',
                    '-lc',
                    (
                        f"export GZ_PARTITION='{gz_partition}'; "
                        "gz service -s /world/farm_world/control "
                        "--reqtype gz.msgs.WorldControl "
                        "--reptype gz.msgs.Boolean "
                        "--timeout 3000 "
                        "--req 'pause: false' >/dev/null 2>&1 || true"
                    ),
                ],
                shell=False,
            ),
        ],
    )
    unpause_world_retry = TimerAction(
        period=8.0,
        actions=[
            ExecuteProcess(
                cmd=[
                    'bash',
                    '-lc',
                    (
                        f"export GZ_PARTITION='{gz_partition}'; "
                        "gz service -s /world/farm_world/control "
                        "--reqtype gz.msgs.WorldControl "
                        "--reptype gz.msgs.Boolean "
                        "--timeout 3000 "
                        "--req 'pause: false' >/dev/null 2>&1 || true"
                    ),
                ],
                shell=False,
            ),
        ],
    )

    runtime_snapshot_exporter = Node(
        package='agribot_bringup',
        executable='runtime_snapshot_exporter',
        name='runtime_snapshot_exporter',
        output='log',
        parameters=[{
            'use_sim_time': True,
            'map_id': 'farm_map',
            'pose_write_period_sec': LaunchConfiguration('pose_write_period_sec'),
            'semantic_write_period_sec': LaunchConfiguration('semantic_write_period_sec'),
        }],
        condition=IfCondition(LaunchConfiguration('use_runtime_support')),
    )
    robot_manual_command_executor = Node(
        package='agribot_bringup',
        executable='robot_manual_command_executor',
        name='robot_manual_command_executor',
        output='log',
        parameters=[{
            'use_sim_time': True,
            'map_id': 'farm_map',
            'command_poll_period_sec': LaunchConfiguration('robot_command_poll_period_sec'),
        }],
        condition=IfCondition(LaunchConfiguration('use_runtime_support')),
    )
    mission_bridge_executor = Node(
        package='agribot_bringup',
        executable='mission_bridge_executor',
        name='mission_bridge_executor',
        output='log',
        parameters=[{
            'use_sim_time': True,
            'robot_id': 'AGR-02',
            'command_poll_period_sec': LaunchConfiguration('mission_command_poll_period_sec'),
        }],
        condition=IfCondition(LaunchConfiguration('use_runtime_support')),
    )

    return LaunchDescription([
        gz_args_prefix_arg,
        use_iot_arg,
        use_rviz_arg,
        use_camera_bridges_arg,
        cmd_vel_watchdog_publish_rate_arg,
        runtime_dir_arg,
        use_perception_arg,
        use_runtime_support_arg,
        pose_write_period_arg,
        semantic_write_period_arg,
        robot_command_poll_period_arg,
        mission_command_poll_period_arg,
        backend_confirm_url_arg,
        mqtt_force_log_only_arg,
        *env_vars,
        shutdown_cleanup_handler,
        spawn_agribot,
        runtime_snapshot_exporter,
        robot_manual_command_executor,
        mission_bridge_executor,
        unpause_world,
        unpause_world_retry,
        delayed_navigation,
        iot_status_pipeline,
        perception,
    ])


def _sanitize_gz_partition_suffix(raw_value: str) -> str:
    normalized = re.sub(r'[^A-Za-z0-9_]+', '_', raw_value).strip('_')
    return normalized or 'session'
