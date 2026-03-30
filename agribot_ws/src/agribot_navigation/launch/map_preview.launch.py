import os
from pathlib import Path
import sys

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

try:
    from agribot_bringup.launch_profile import (
        build_graphics_environment_actions,
    )
except ModuleNotFoundError:
    bringup_package_root = Path(__file__).resolve().parents[2] / 'agribot_bringup'
    if str(bringup_package_root) not in sys.path:
        sys.path.append(str(bringup_package_root))
    from agribot_bringup.launch_profile import (
        build_graphics_environment_actions,
    )


def generate_launch_description():
    pkg_agribot_navigation = get_package_share_directory('agribot_navigation')
    graphics_env_actions = build_graphics_environment_actions()
    default_map = os.path.join(
        pkg_agribot_navigation,
        'maps',
        'farm_map.yaml',
    )
    default_rviz = os.path.join(
        pkg_agribot_navigation,
        'rviz',
        'mapping.rviz',
    )

    map_arg = DeclareLaunchArgument(
        'map',
        default_value=default_map,
        description='Path to the saved farm map yaml file.',
    )
    rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Launch RViz to inspect the stored map.',
    )
    rviz_config_arg = DeclareLaunchArgument(
        'rviz_config_file',
        default_value=default_rviz,
        description='RViz config used to preview the stored map.',
    )
    sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation time when previewing the stored map.',
    )

    map_server = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        output='screen',
        parameters=[{
            'yaml_filename': LaunchConfiguration('map'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
    )

    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_map_preview',
        output='screen',
        parameters=[{
            'autostart': True,
            'node_names': ['map_server'],
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='map_preview_rviz',
        arguments=['-d', LaunchConfiguration('rviz_config_file')],
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        condition=IfCondition(LaunchConfiguration('use_rviz')),
        output='screen',
    )

    return LaunchDescription([
        *graphics_env_actions,
        map_arg,
        rviz_arg,
        rviz_config_arg,
        sim_time_arg,
        map_server,
        lifecycle_manager,
        rviz,
    ])
