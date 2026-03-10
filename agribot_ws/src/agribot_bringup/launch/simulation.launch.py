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
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_packages import get_package_share_directory
import os


def generate_launch_description():
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

    return LaunchDescription([
        spawn_agribot,
        # TODO: Add navigation launch
        # TODO: Add perception launch
        # TODO: Add IoT launch
    ])
