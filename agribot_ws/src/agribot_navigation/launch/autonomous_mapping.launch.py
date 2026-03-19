import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_agribot_navigation = get_package_share_directory('agribot_navigation')
    pkg_slam_toolbox = get_package_share_directory('slam_toolbox')

    default_world = os.path.join(
        pkg_agribot_description,
        'worlds',
        'farm_world.sdf',
    )
    default_boundary_map = os.path.join(
        pkg_agribot_navigation,
        'maps',
        'greenhouse_exploration_boundary.yaml',
    )
    default_slam_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'slam_mapping.yaml',
    )
    default_nav2_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'nav2_mapping_params.yaml',
    )
    default_frontier_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'frontier_explorer.yaml',
    )
    default_patrol_waypoints = os.path.join(
        pkg_agribot_navigation,
        'config',
        'patrol_waypoints.yaml',
    )
    default_rviz_config = os.path.join(
        pkg_agribot_navigation,
        'rviz',
        'mapping.rviz',
    )
    default_nav_to_pose_bt = os.path.join(
        pkg_agribot_navigation,
        'behavior_trees',
        'navigate_to_pose_w_backout_recovery.xml',
    )
    default_nav_through_poses_bt = os.path.join(
        pkg_agribot_navigation,
        'behavior_trees',
        'navigate_through_poses_w_backout_recovery.xml',
    )

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use the simulation clock for SLAM, Nav2, and RViz.',
    )
    world_arg = DeclareLaunchArgument(
        'world',
        default_value=default_world,
        description='Gazebo world used for autonomous mapping.',
    )
    boundary_map_arg = DeclareLaunchArgument(
        'boundary_map',
        default_value=default_boundary_map,
        description='Optional constraint map used to keep exploration inside a known area.',
    )
    use_boundary_map_arg = DeclareLaunchArgument(
        'use_boundary_map',
        default_value='false',
        description='Enable the optional exploration boundary map.',
    )
    slam_params_arg = DeclareLaunchArgument(
        'slam_params_file',
        default_value=default_slam_params,
        description='SLAM Toolbox parameter file for live mapping.',
    )
    nav2_params_arg = DeclareLaunchArgument(
        'nav2_params_file',
        default_value=default_nav2_params,
        description='Nav2 parameter file used for autonomous mapping.',
    )
    frontier_params_arg = DeclareLaunchArgument(
        'frontier_params_file',
        default_value=default_frontier_params,
        description='Frontier explorer parameter file for generic autonomous mapping.',
    )
    patrol_waypoints_arg = DeclareLaunchArgument(
        'patrol_waypoints_file',
        default_value=default_patrol_waypoints,
        description='Waypoint sequence used to sweep the greenhouse during mapping.',
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
        description='Automatically configure and activate lifecycle nodes.',
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
    use_frontier_explorer_arg = DeclareLaunchArgument(
        'use_frontier_explorer',
        default_value='true',
        description='Launch the generic frontier explorer for map completion.',
    )
    frontier_autostart_arg = DeclareLaunchArgument(
        'frontier_autostart',
        default_value='true',
        description='Start the frontier explorer automatically.',
    )
    frontier_start_delay_arg = DeclareLaunchArgument(
        'frontier_start_delay_sec',
        default_value='5.0',
        description='Delay before the frontier explorer starts after Nav2 activation.',
    )
    use_patrol_arg = DeclareLaunchArgument(
        'use_patrol',
        default_value='false',
        description='Launch the greenhouse-specific waypoint patrol mapper.',
    )
    patrol_autostart_arg = DeclareLaunchArgument(
        'patrol_autostart',
        default_value='false',
        description='Start the mapping patrol automatically.',
    )
    patrol_start_delay_arg = DeclareLaunchArgument(
        'patrol_start_delay_sec',
        default_value='1.0',
        description='Delay before the autonomous mapping patrol starts.',
    )
    nav_start_delay_arg = DeclareLaunchArgument(
        'nav_start_delay_sec',
        default_value='4.0',
        description='Delay before Nav2 lifecycle activation begins.',
    )
    inspect_dwell_arg = DeclareLaunchArgument(
        'inspect_dwell_sec',
        default_value='1.5',
        description='Pause duration at inspection waypoints to densify SLAM scans.',
    )
    stack_start_delay_arg = DeclareLaunchArgument(
        'stack_start_delay_sec',
        default_value='2.0',
        description='Delay before starting SLAM, boundary map, and Nav2 nodes.',
    )
    boundary_lifecycle_delay_arg = DeclareLaunchArgument(
        'boundary_lifecycle_delay_sec',
        default_value='3.0',
        description='Delay before activating the exploration boundary map server.',
    )
    slam_lifecycle_manager_arg = DeclareLaunchArgument(
        'use_slam_lifecycle_manager',
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
        }.items(),
    )

    slam_toolbox = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                pkg_slam_toolbox,
                'launch',
                'online_async_launch.py',
            )
        ),
        launch_arguments={
            'autostart': LaunchConfiguration('autostart'),
            'use_lifecycle_manager': LaunchConfiguration('use_slam_lifecycle_manager'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'slam_params_file': LaunchConfiguration('slam_params_file'),
        }.items(),
    )
    delayed_slam_toolbox = TimerAction(
        period=LaunchConfiguration('stack_start_delay_sec'),
        actions=[slam_toolbox],
    )

    exploration_boundary_map_server = Node(
        package='nav2_map_server',
        executable='map_server',
        name='exploration_boundary_map_server',
        output='screen',
        parameters=[{
            'yaml_filename': LaunchConfiguration('boundary_map'),
            'frame_id': 'odom',
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
        remappings=[
            ('/map', '/exploration_boundary_map'),
            ('/map_metadata', '/exploration_boundary_map_metadata'),
        ],
        condition=IfCondition(LaunchConfiguration('use_boundary_map')),
    )
    delayed_exploration_boundary_map_server = TimerAction(
        period=LaunchConfiguration('stack_start_delay_sec'),
        actions=[exploration_boundary_map_server],
    )

    exploration_boundary_lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_exploration_boundary_map',
        output='screen',
        parameters=[{
            'autostart': LaunchConfiguration('autostart'),
            'node_names': ['exploration_boundary_map_server'],
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
        condition=IfCondition(LaunchConfiguration('use_boundary_map')),
    )
    delayed_exploration_boundary_lifecycle_manager = TimerAction(
        period=LaunchConfiguration('boundary_lifecycle_delay_sec'),
        actions=[exploration_boundary_lifecycle_manager],
    )

    common_nav_parameters = [
        LaunchConfiguration('nav2_params_file'),
        {
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'default_nav_to_pose_bt_xml': default_nav_to_pose_bt,
            'default_nav_through_poses_bt_xml': default_nav_through_poses_bt,
        },
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

    navigation_lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_autonomous_mapping',
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
    delayed_navigation_nodes = TimerAction(
        period=LaunchConfiguration('stack_start_delay_sec'),
        actions=[
            controller_server,
            planner_server,
            smoother_server,
            behavior_server,
            bt_navigator,
            waypoint_follower,
        ],
    )
    delayed_navigation_lifecycle_manager = TimerAction(
        period=LaunchConfiguration('nav_start_delay_sec'),
        actions=[navigation_lifecycle_manager],
    )

    frontier_explorer = Node(
        package='agribot_navigation',
        executable='frontier_explorer',
        name='mapping_frontier_explorer',
        output='screen',
        parameters=[
            LaunchConfiguration('frontier_params_file'),
            {
                'use_sim_time': LaunchConfiguration('use_sim_time'),
                'auto_start': LaunchConfiguration('frontier_autostart'),
                'use_boundary_map': LaunchConfiguration('use_boundary_map'),
                'boundary_map_topic': '/exploration_boundary_map',
            },
        ],
        condition=IfCondition(LaunchConfiguration('use_frontier_explorer')),
    )

    delayed_frontier_explorer = TimerAction(
        period=LaunchConfiguration('frontier_start_delay_sec'),
        actions=[frontier_explorer],
    )

    mapping_patrol_node = Node(
        package='agribot_navigation',
        executable='patrol_node',
        name='mapping_patrol_node',
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'patrol_waypoints_file': LaunchConfiguration('patrol_waypoints_file'),
            'auto_start': LaunchConfiguration('patrol_autostart'),
            'inspect_dwell_sec': LaunchConfiguration('inspect_dwell_sec'),
            'nav_server_wait_sec': 60.0,
            'goal_reject_retry_sec': 1.0,
            'goal_reject_retry_limit': 30,
            'status_topic': 'mapping_patrol/status',
            'start_service': 'mapping_patrol/start',
            'stop_service': 'mapping_patrol/stop',
            'resume_service': 'mapping_patrol/resume',
        }],
        condition=IfCondition(LaunchConfiguration('use_patrol')),
    )

    delayed_mapping_patrol = TimerAction(
        period=LaunchConfiguration('patrol_start_delay_sec'),
        actions=[mapping_patrol_node],
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
        use_sim_time_arg,
        world_arg,
        boundary_map_arg,
        use_boundary_map_arg,
        slam_params_arg,
        nav2_params_arg,
        frontier_params_arg,
        patrol_waypoints_arg,
        use_rviz_arg,
        rviz_config_arg,
        autostart_arg,
        use_respawn_arg,
        log_level_arg,
        use_frontier_explorer_arg,
        frontier_autostart_arg,
        frontier_start_delay_arg,
        use_patrol_arg,
        patrol_autostart_arg,
        patrol_start_delay_arg,
        nav_start_delay_arg,
        inspect_dwell_arg,
        stack_start_delay_arg,
        boundary_lifecycle_delay_arg,
        slam_lifecycle_manager_arg,
        simulation,
        delayed_slam_toolbox,
        delayed_exploration_boundary_map_server,
        delayed_exploration_boundary_lifecycle_manager,
        delayed_navigation_nodes,
        delayed_navigation_lifecycle_manager,
        delayed_frontier_explorer,
        delayed_mapping_patrol,
        rviz,
    ])
