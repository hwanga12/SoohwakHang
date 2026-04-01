# 이 런치 파일은 자율주행과 경로 계획 패키지의 노드와 의존 구성을 한 번에 실행하도록 묶는다.
import os
from pathlib import Path
import sys

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
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
    # 실행 description을 생성한다.
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_agribot_navigation = get_package_share_directory('agribot_navigation')
    graphics_env_actions = build_graphics_environment_actions()
    default_gz_partition = (
        os.getenv('AGRIBOT_GZ_PARTITION')
        or os.getenv('GZ_PARTITION')
        or 'agribot_sim_local'
    )

    default_world = os.path.join(
        pkg_agribot_description,
        'worlds',
        'farm_world.sdf',
    )
    default_map = os.path.join(
        pkg_agribot_navigation,
        'maps',
        'farm_map.yaml',
    )
    default_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'amcl.yaml',
    )
    default_rviz_config = os.path.join(
        pkg_agribot_navigation,
        'rviz',
        'mapping.rviz',
    )

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use the simulation clock for Gazebo, AMCL, and RViz.',
    )
    world_arg = DeclareLaunchArgument(
        'world',
        default_value=default_world,
        description='Gazebo world used for localization.',
    )
    map_arg = DeclareLaunchArgument(
        'map',
        default_value=default_map,
        description='Path to the saved occupancy grid map yaml file.',
    )
    params_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='AMCL parameter file for static-map localization.',
    )
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Launch RViz with the localization workspace.',
    )
    rviz_config_arg = DeclareLaunchArgument(
        'rviz_config_file',
        default_value=default_rviz_config,
        description='RViz configuration for localization sessions.',
    )
    autostart_arg = DeclareLaunchArgument(
        'autostart',
        default_value='true',
        description='Automatically configure and activate map_server and amcl.',
    )
    use_startup_map_tf_broadcaster_arg = DeclareLaunchArgument(
        'use_startup_map_tf_broadcaster',
        default_value='true',
        description='Launch the temporary startup map -> odom broadcaster before localization stabilizes.',
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

    amcl = Node(
        package='nav2_amcl',
        executable='amcl',
        name='amcl',
        output='screen',
        parameters=[
            LaunchConfiguration('params_file'),
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
        ],
    )

    gz_partition_arg = DeclareLaunchArgument(
        'gz_partition',
        default_value=default_gz_partition,
        description='Gazebo partition name.'
    )

    gz_partition_env = SetEnvironmentVariable(
        name='GZ_PARTITION',
        value=LaunchConfiguration('gz_partition'),
    )

    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_localization',
        output='screen',
        parameters=[{
            'autostart': LaunchConfiguration('autostart'),
            'node_names': ['map_server', 'amcl'],
            # Nav2 bond heartbeats are unreliable in this sim stack because the
            # Gazebo clock can pause/jump while nodes remain healthy. Disable
            # bond-based kill/restart loops and rely on explicit service
            # failures instead.
            'bond_timeout': 0.0,
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
    )

    startup_map_tf_broadcaster = Node(
        package='agribot_navigation',
        executable='startup_map_tf_broadcaster',
        name='startup_map_tf_broadcaster',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        condition=IfCondition(LaunchConfiguration('use_startup_map_tf_broadcaster')),
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='localization_rviz',
        arguments=['-d', LaunchConfiguration('rviz_config_file')],
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        condition=IfCondition(LaunchConfiguration('use_rviz')),
        output='screen',
    )

    return LaunchDescription([
        *graphics_env_actions,
        gz_partition_arg,
        gz_partition_env,
        use_sim_time_arg,
        world_arg,
        map_arg,
        params_arg,
        use_rviz_arg,
        rviz_config_arg,
        autostart_arg,
        use_startup_map_tf_broadcaster_arg,
        startup_map_tf_broadcaster,
        map_server,
        amcl,
        lifecycle_manager,
        rviz,
    ])
