"""
AgriBot Spawn Launch File
Launches the AgriBot robot model in a Gazebo Harmonic simulation world.

Usage:
    ros2 launch agribot_description spawn_agribot.launch.py
"""

import os
from ament_index_packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    # Package paths
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')

    # Launch arguments
    world_arg = DeclareLaunchArgument(
        'world',
        default_value=os.path.join(
            pkg_agribot_description, 'worlds', 'farm_world.sdf'
        ),
        description='Path to the Gazebo world file'
    )

    # Gazebo Harmonic simulation
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': LaunchConfiguration('world'),
        }.items(),
    )

    return LaunchDescription([
        world_arg,
        gz_sim,
    ])
