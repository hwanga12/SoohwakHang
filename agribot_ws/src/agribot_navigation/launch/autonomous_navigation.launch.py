import os
from pathlib import Path
import sys
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

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
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_agribot_navigation = get_package_share_directory('agribot_navigation')

    graphics_env_actions = build_graphics_environment_actions()

    default_world = os.path.join(pkg_agribot_description, 'worlds', 'farm_world.sdf')
    default_map = os.path.join(pkg_agribot_navigation, 'maps', 'farm_map.yaml')

    world_arg = DeclareLaunchArgument('world', default_value=default_world)
    map_arg = DeclareLaunchArgument('map', default_value=default_map)
    use_sim_time_arg = DeclareLaunchArgument('use_sim_time', default_value='true')

    simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_agribot_description, 'launch', 'spawn_agribot.launch.py')
        ),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'publish_map_to_odom_tf': 'false'
        }.items()
    )

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_agribot_navigation, 'launch', 'navigation.launch.py')
        ),
        launch_arguments={
            'map': LaunchConfiguration('map'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'nav2_params_file': os.path.join(pkg_agribot_navigation, 'config', 'nav2_mapping_params.yaml')
        }.items()
    )
    
    delayed_navigation = TimerAction(
        period=5.0,
        actions=[navigation]
    )

    return LaunchDescription([
        *graphics_env_actions,
        world_arg,
        map_arg,
        use_sim_time_arg,
        simulation,
        delayed_navigation
    ])
