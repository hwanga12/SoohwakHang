import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_agribot_navigation = get_package_share_directory('agribot_navigation')

    default_world = os.path.join(
        pkg_agribot_description,
        'worlds',
        'farm_world.sdf',
    )
    default_map = os.path.join(
        pkg_agribot_navigation,
        'maps',
        'greenhouse_map.yaml',
    )
    default_localization_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'amcl.yaml',
    )
    default_nav2_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'nav2_params.yaml',
    )
    default_patrol_waypoints = os.path.join(
        pkg_agribot_navigation,
        'config',
        'patrol_waypoints.yaml',
    )
    default_crop_instances = os.path.join(
        pkg_agribot_description,
        'config',
        'crop_instances.yaml',
    )
    default_rviz_config = os.path.join(
        pkg_agribot_navigation,
        'rviz',
        'mapping.rviz',
    )

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use the simulation clock for Nav2 and RViz.',
    )
    world_arg = DeclareLaunchArgument(
        'world',
        default_value=default_world,
        description='Gazebo world used for autonomous navigation.',
    )
    map_arg = DeclareLaunchArgument(
        'map',
        default_value=default_map,
        description='Path to the saved occupancy grid map yaml file.',
    )
    localization_params_arg = DeclareLaunchArgument(
        'localization_params_file',
        default_value=default_localization_params,
        description='AMCL parameter file used by localization.launch.py.',
    )
    nav2_params_arg = DeclareLaunchArgument(
        'nav2_params_file',
        default_value=default_nav2_params,
        description='Nav2 planner/controller/costmap parameter file.',
    )
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Launch RViz with the navigation workspace.',
    )
    rviz_config_arg = DeclareLaunchArgument(
        'rviz_config_file',
        default_value=default_rviz_config,
        description='RViz configuration for navigation sessions.',
    )
    autostart_arg = DeclareLaunchArgument(
        'autostart',
        default_value='true',
        description='Automatically configure and activate Nav2 lifecycle nodes.',
    )
    use_respawn_arg = DeclareLaunchArgument(
        'use_respawn',
        default_value='false',
        description='Respawn Nav2 nodes if they crash.',
    )
    log_level_arg = DeclareLaunchArgument(
        'log_level',
        default_value='info',
        description='Log level for Nav2 nodes.',
    )
    use_patrol_arg = DeclareLaunchArgument(
        'use_patrol',
        default_value='true',
        description='Launch the patrol control node alongside Nav2.',
    )
    patrol_waypoints_arg = DeclareLaunchArgument(
        'patrol_waypoints_file',
        default_value=default_patrol_waypoints,
        description='Path to patrol waypoint metadata used by patrol_node.',
    )
    patrol_autostart_arg = DeclareLaunchArgument(
        'patrol_autostart',
        default_value='false',
        description='Start the patrol automatically after the stack launches.',
    )
    use_harvest_route_arg = DeclareLaunchArgument(
        'use_harvest_route',
        default_value='true',
        description='Launch the harvest approach/return coordinator node.',
    )
    crop_instances_arg = DeclareLaunchArgument(
        'crop_instances_file',
        default_value=default_crop_instances,
        description='Path to crop_instances.yaml used for harvest target metadata.',
    )
    harvest_return_mode_arg = DeclareLaunchArgument(
        'harvest_return_mode',
        default_value='',
        description='Optional override for harvest return mode: empty, resume_patrol, or home.',
    )

    localization = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                pkg_agribot_navigation,
                'launch',
                'localization.launch.py',
            )
        ),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'world': LaunchConfiguration('world'),
            'map': LaunchConfiguration('map'),
            'params_file': LaunchConfiguration('localization_params_file'),
            'use_rviz': 'false',
            'rviz_config_file': LaunchConfiguration('rviz_config_file'),
            'autostart': LaunchConfiguration('autostart'),
        }.items(),
    )

    common_nav_parameters = [
        LaunchConfiguration('nav2_params_file'),
        {'use_sim_time': LaunchConfiguration('use_sim_time')},
    ]

    controller_server = Node(
        package='nav2_controller',
        executable='controller_server',
        name='controller_server',
        output='screen',
        respawn=LaunchConfiguration('use_respawn'),
        respawn_delay=2.0,
        parameters=common_nav_parameters,
        arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
    )

    planner_server = Node(
        package='nav2_planner',
        executable='planner_server',
        name='planner_server',
        output='screen',
        respawn=LaunchConfiguration('use_respawn'),
        respawn_delay=2.0,
        parameters=common_nav_parameters,
        arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
    )

    smoother_server = Node(
        package='nav2_smoother',
        executable='smoother_server',
        name='smoother_server',
        output='screen',
        respawn=LaunchConfiguration('use_respawn'),
        respawn_delay=2.0,
        parameters=common_nav_parameters,
        arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
    )

    behavior_server = Node(
        package='nav2_behaviors',
        executable='behavior_server',
        name='behavior_server',
        output='screen',
        respawn=LaunchConfiguration('use_respawn'),
        respawn_delay=2.0,
        parameters=common_nav_parameters,
        arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
    )

    bt_navigator = Node(
        package='nav2_bt_navigator',
        executable='bt_navigator',
        name='bt_navigator',
        output='screen',
        respawn=LaunchConfiguration('use_respawn'),
        respawn_delay=2.0,
        parameters=common_nav_parameters,
        arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
    )

    waypoint_follower = Node(
        package='nav2_waypoint_follower',
        executable='waypoint_follower',
        name='waypoint_follower',
        output='screen',
        respawn=LaunchConfiguration('use_respawn'),
        respawn_delay=2.0,
        parameters=common_nav_parameters,
        arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
    )

    lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_navigation',
        output='screen',
        parameters=[{
            'autostart': LaunchConfiguration('autostart'),
            'node_names': [
                'controller_server',
                'planner_server',
                'smoother_server',
                'behavior_server',
                'bt_navigator',
                'waypoint_follower',
            ],
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='navigation_rviz',
        arguments=['-d', LaunchConfiguration('rviz_config_file')],
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        condition=IfCondition(LaunchConfiguration('use_rviz')),
        output='screen',
    )

    patrol_node = Node(
        package='agribot_navigation',
        executable='patrol_node',
        name='patrol_node',
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'patrol_waypoints_file': LaunchConfiguration('patrol_waypoints_file'),
            'auto_start': LaunchConfiguration('patrol_autostart'),
        }],
        condition=IfCondition(LaunchConfiguration('use_patrol')),
    )

    harvest_route_node = Node(
        package='agribot_navigation',
        executable='harvest_route_node',
        name='harvest_route_node',
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'patrol_waypoints_file': LaunchConfiguration('patrol_waypoints_file'),
            'crop_instances_file': LaunchConfiguration('crop_instances_file'),
            'return_mode_override': LaunchConfiguration('harvest_return_mode'),
        }],
        condition=IfCondition(LaunchConfiguration('use_harvest_route')),
    )

    return LaunchDescription([
        use_sim_time_arg,
        world_arg,
        map_arg,
        localization_params_arg,
        nav2_params_arg,
        use_rviz_arg,
        rviz_config_arg,
        autostart_arg,
        use_respawn_arg,
        log_level_arg,
        use_patrol_arg,
        patrol_waypoints_arg,
        patrol_autostart_arg,
        use_harvest_route_arg,
        crop_instances_arg,
        harvest_return_mode_arg,
        localization,
        controller_server,
        planner_server,
        smoother_server,
        behavior_server,
        bt_navigator,
        waypoint_follower,
        lifecycle_manager,
        patrol_node,
        harvest_route_node,
        rviz,
    ])
