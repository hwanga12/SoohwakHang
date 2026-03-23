import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable, TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


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
    pkg_slam_toolbox = get_package_share_directory('slam_toolbox')

    default_world = os.path.join(
        pkg_agribot_description,
        'worlds',
        'farm_world.sdf',
    )
    default_slam_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'slam_mapping.yaml',
    )
    default_ekf_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'ekf_mapping.yaml',
    )
    default_rviz_config = os.path.join(
        pkg_agribot_navigation,
        'rviz',
        'mapping.rviz',
    )

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use the simulation clock for mapping and RViz.',
    )
    world_arg = DeclareLaunchArgument(
        'world',
        default_value=default_world,
        description='Gazebo world used for the mapping session.',
    )
    slam_params_arg = DeclareLaunchArgument(
        'slam_params_file',
        default_value=default_slam_params,
        description='SLAM Toolbox parameter file for greenhouse mapping.',
    )
    ekf_params_arg = DeclareLaunchArgument(
        'ekf_params_file',
        default_value=default_ekf_params,
        description='robot_localization EKF parameter file for manual mapping.',
    )
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Launch RViz with the mapping workspace.',
    )
    rviz_config_arg = DeclareLaunchArgument(
        'rviz_config_file',
        default_value=default_rviz_config,
        description='RViz configuration for mapping sessions.',
    )
    autostart_arg = DeclareLaunchArgument(
        'autostart',
        default_value='true',
        description='Automatically configure and activate slam_toolbox.',
    )
    stack_start_delay_arg = DeclareLaunchArgument(
        'stack_start_delay_sec',
        default_value='2.5',
        description='Delay before starting EKF and SLAM so sim time and /odom settle first.',
    )
    lifecycle_manager_arg = DeclareLaunchArgument(
        'use_lifecycle_manager',
        default_value='false',
        description='Enable slam_toolbox lifecycle manager integration.',
    )

    simulation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                pkg_agribot_description,
                'launch',
                'spawn_agribot.launch.py',
            )
        ),
        launch_arguments={
            'world': LaunchConfiguration('world'),
            'publish_map_to_odom_tf': 'false',
            'publish_odom_tf': 'true',
            'use_camera_bridges': 'false',
        }.items(),
    )

    ekf_filter = Node(
        package='robot_localization',
        executable='ekf_node',
        name='mapping_ekf_filter',
        output='screen',
        parameters=[
            LaunchConfiguration('ekf_params_file'),
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
        ],
    )
    delayed_ekf_filter = TimerAction(
        period=0.5,
        actions=[ekf_filter],
    )

    slam_toolbox = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                pkg_slam_toolbox,
                'launch',
                'online_sync_launch.py',
            )
        ),
        launch_arguments={
            'autostart': LaunchConfiguration('autostart'),
            'use_lifecycle_manager': LaunchConfiguration('use_lifecycle_manager'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'slam_params_file': LaunchConfiguration('slam_params_file'),
        }.items(),
    )
    delayed_slam_toolbox = TimerAction(
        period=LaunchConfiguration('stack_start_delay_sec'),
        actions=[slam_toolbox],
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='mapping_rviz',
        arguments=['-d', LaunchConfiguration('rviz_config_file')],
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        condition=IfCondition(LaunchConfiguration('use_rviz')),
        output='screen',
    )

    return LaunchDescription([
        *gpu_env_actions,
        use_sim_time_arg,
        world_arg,
        slam_params_arg,
        ekf_params_arg,
        use_rviz_arg,
        rviz_config_arg,
        autostart_arg,
        stack_start_delay_arg,
        lifecycle_manager_arg,
        simulation,
        delayed_ekf_filter,
        delayed_slam_toolbox,
        rviz,
    ])
