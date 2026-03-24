"""
AgriBot Simulation Launch File
Brings up the complete simulation environment including:
- Gazebo Harmonic world
- Robot model spawn
- ROS-Gazebo bridge
- (Future) Nav2, sensors, IoT

Usage:
    ros2 launch agribot_bringup simulation.launch.py
"""

from launch import LaunchDescription
from launch.actions import TimerAction
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
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
        ),
        launch_arguments={
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
            'use_rviz': 'true',
            'patrol_robot_pose_topic': '/odom',
        }.items()
    )

    delayed_navigation = TimerAction(
        period=5.0,
        actions=[navigation],
    )

    return LaunchDescription([
        *env_vars,
        spawn_agribot,
        delayed_navigation,
        # TODO: Add perception launch
        # TODO: Add IoT launch
    ])
