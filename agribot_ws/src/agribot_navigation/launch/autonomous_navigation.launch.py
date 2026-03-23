import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

def generate_launch_description():
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_agribot_navigation = get_package_share_directory('agribot_navigation')

    gpu_env_actions = []
    if os.path.exists('/usr/bin/nvidia-smi'):
        gpu_env_actions = [
            SetEnvironmentVariable('DRI_PRIME', '1'),
            SetEnvironmentVariable('__NV_PRIME_RENDER_OFFLOAD', '1'),
            SetEnvironmentVariable('__GLX_VENDOR_LIBRARY_NAME', 'nvidia'),
        ]

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
        *gpu_env_actions,
        world_arg,
        map_arg,
        use_sim_time_arg,
        simulation,
        delayed_navigation
    ])
