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


def generate_launch_description():
    gz_partition = 'agribot_sim'
    runtime_dir = LaunchConfiguration('runtime_dir')
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
        SetEnvironmentVariable('GZ_PARTITION', gz_partition),
        SetEnvironmentVariable('AGRIBOT_RUNTIME_DIR', runtime_dir),
        # Ensure agribot_interfaces python bindings are found
        SetEnvironmentVariable(
            'PYTHONPATH', 
            agribot_interfaces_site_packages +
            ':' + os.environ.get('PYTHONPATH', '')
        ),
    ]

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
            # AMCL / startup_map_tf_broadcaster own map -> odom during
            # static-map localization. Keeping the spawn-time identity TF here
            # forces the saved map to stay aligned with raw odom.
            'publish_map_to_odom_tf': 'false',
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
        }.items()
    )
    gz_args_prefix_arg = DeclareLaunchArgument(
        'gz_args_prefix',
        default_value='-r',
        description='Arguments passed to gz sim before the world path.',
    )
    use_iot_arg = DeclareLaunchArgument(
        'use_iot',
        default_value='true',
        description='Launch the IoT status/result publishing stack.',
    )
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Launch RViz alongside Nav2.',
    )
    runtime_dir_arg = DeclareLaunchArgument(
        'runtime_dir',
        default_value=EnvironmentVariable('AGRIBOT_RUNTIME_DIR', default_value='/tmp/agribot_runtime'),
        description='Shared runtime directory for backend file bridge and ROS executors.',
    )
    use_perception_arg = DeclareLaunchArgument(
        'use_perception',
        default_value='true',
        description='Launch the thin inference pipeline that forwards snapshots to the backend.',
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
        period=5.0,
        actions=[navigation],
    )

    runtime_snapshot_exporter = Node(
        package='agribot_bringup',
        executable='runtime_snapshot_exporter',
        name='runtime_snapshot_exporter',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'map_id': 'farm_map',
        }],
    )
    robot_manual_command_executor = Node(
        package='agribot_bringup',
        executable='robot_manual_command_executor',
        name='robot_manual_command_executor',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'map_id': 'farm_map',
        }],
    )
    mission_bridge_executor = Node(
        package='agribot_bringup',
        executable='mission_bridge_executor',
        name='mission_bridge_executor',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'robot_id': 'AGR-02',
        }],
    )

    return LaunchDescription([
        gz_args_prefix_arg,
        use_iot_arg,
        use_rviz_arg,
        runtime_dir_arg,
        use_perception_arg,
        backend_confirm_url_arg,
        mqtt_force_log_only_arg,
        *env_vars,
        spawn_agribot,
        runtime_snapshot_exporter,
        robot_manual_command_executor,
        mission_bridge_executor,
        delayed_navigation,
        iot_status_pipeline,
        perception,
    ])
