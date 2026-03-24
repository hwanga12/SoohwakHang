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
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    gz_partition = 'agribot_sim'
    
    # Environment variables
    env_vars = [
        SetEnvironmentVariable('GZ_PARTITION', gz_partition),
        # Ensure agribot_interfaces python bindings are found
        SetEnvironmentVariable(
            'PYTHONPATH', 
            os.path.join(os.getcwd(), 'install/agribot_interfaces/lib/python3.12/site-packages') + 
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
        )
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
            'use_rviz': 'true'
        }.items()
    )
    use_iot_arg = DeclareLaunchArgument(
        'use_iot',
        default_value='true',
        description='Launch the IoT status/result publishing stack.',
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

    return LaunchDescription([
        *env_vars,
        use_iot_arg,
        mqtt_force_log_only_arg,
        spawn_agribot,
        navigation,
        iot_status_pipeline,
        # TODO: Add perception launch
    ])
