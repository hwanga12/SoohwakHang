# 이 런치 파일은 자율주행과 경로 계획 패키지의 노드와 의존 구성을 한 번에 실행하도록 묶는다.
import os
from pathlib import Path
import sys

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
    SetLaunchConfiguration,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


try:
    from agribot_bringup.launch_profile import (
        build_launch_session_environment_actions,
        resolve_performance_defaults,
    )
    from agribot_bringup.shutdown_cleanup import (
        build_shutdown_cleanup_handler,
        ensure_launch_session_id_env,
        resolve_launch_session_id,
    )
except ModuleNotFoundError:
    bringup_package_root = Path(__file__).resolve().parents[2] / 'agribot_bringup'
    if str(bringup_package_root) not in sys.path:
        sys.path.append(str(bringup_package_root))
    from agribot_bringup.launch_profile import (
        build_launch_session_environment_actions,
        resolve_performance_defaults,
    )
    from agribot_bringup.shutdown_cleanup import (
        build_shutdown_cleanup_handler,
        ensure_launch_session_id_env,
        resolve_launch_session_id,
    )


_TRUE_VALUES = ('true', '1', 'yes', 'on')


def _bool_expr(name: str) -> PythonExpression:
    # bool expr 정보를 계산해 반환한다.
    return PythonExpression([
        "'",
        LaunchConfiguration(name),
        "'.lower() in ['true', '1', 'yes', 'on']",
    ])


def _all_true_expr(*names: str) -> PythonExpression:
    # all true expr 정보를 계산해 반환한다.
    expression = []
    for index, name in enumerate(names):
        if index:
            expression.append(' and ')
        expression.extend([
            "'",
            LaunchConfiguration(name),
            "'.lower() in ['true', '1', 'yes', 'on']",
        ])
    return PythonExpression(expression)


def _bool_value(context, name: str) -> bool:
    # bool 값 정보를 계산해 반환한다.
    return LaunchConfiguration(name).perform(context).strip().lower() in _TRUE_VALUES


def _configure_mapping_strategy(context, *_args, **_kwargs):
    # configure mapping strategy 정보를 계산해 반환한다.
    strategy = LaunchConfiguration('mapping_strategy').perform(context).strip().lower()
    if strategy not in {'sweep_hybrid', 'patrol_only', 'frontier_only'}:
        raise RuntimeError(
            'mapping_strategy must be one of sweep_hybrid, patrol_only, frontier_only.'
        )

    actions = [LogInfo(msg=f'autonomous_mapping strategy: {strategy}')]
    if strategy == 'sweep_hybrid':
        actions.extend(
            [
                SetLaunchConfiguration('use_patrol', 'true'),
                SetLaunchConfiguration('patrol_autostart', 'true'),
                SetLaunchConfiguration('patrol_completion_action', 'start_frontier_explorer'),
                SetLaunchConfiguration('use_frontier_explorer', 'true'),
                SetLaunchConfiguration('frontier_autostart', 'false'),
                SetLaunchConfiguration('use_boundary_map', 'true'),
            ]
        )
    elif strategy == 'patrol_only':
        actions.extend(
            [
                SetLaunchConfiguration('use_patrol', 'true'),
                SetLaunchConfiguration('patrol_autostart', 'true'),
                SetLaunchConfiguration('patrol_completion_action', 'none'),
                SetLaunchConfiguration('use_frontier_explorer', 'false'),
                SetLaunchConfiguration('frontier_autostart', 'false'),
                SetLaunchConfiguration('use_boundary_map', 'false'),
            ]
        )
    else:
        actions.extend(
            [
                SetLaunchConfiguration('use_patrol', 'false'),
                SetLaunchConfiguration('patrol_autostart', 'false'),
                SetLaunchConfiguration('patrol_completion_action', 'none'),
                SetLaunchConfiguration('use_frontier_explorer', 'true'),
                SetLaunchConfiguration('frontier_autostart', 'true'),
                SetLaunchConfiguration('use_boundary_map', 'true'),
            ]
        )
    return actions


def generate_launch_description():
    # 실행 description을 생성한다.
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_agribot_navigation = get_package_share_directory('agribot_navigation')
    pkg_slam_toolbox = get_package_share_directory('slam_toolbox')
    mapping_defaults = resolve_performance_defaults('mapping')
    launch_session_id = ensure_launch_session_id_env(resolve_launch_session_id())
    launch_env_actions = build_launch_session_environment_actions(launch_session_id)
    shutdown_cleanup_handler = build_shutdown_cleanup_handler(launch_session_id)

    default_world = os.path.join(
        pkg_agribot_description,
        'worlds',
        'farm_world.sdf',
    )
    default_boundary_map = os.path.join(
        pkg_agribot_navigation,
        'maps',
        'farm_exploration_boundary.yaml',
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
    default_ekf_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'ekf_mapping.yaml',
    )
    default_collision_monitor_params = os.path.join(
        pkg_agribot_navigation,
        'config',
        'collision_monitor_mapping.yaml',
    )
    default_patrol_waypoints = os.path.join(
        pkg_agribot_navigation,
        'config',
        'farm_mapping_patrol_waypoints.yaml',
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
        default_value='true',
        description='Enable the optional exploration boundary map when frontier mode is active.',
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
    ekf_params_arg = DeclareLaunchArgument(
        'ekf_params_file',
        default_value=default_ekf_params,
        description='robot_localization EKF parameter file for mapping sessions.',
    )
    collision_monitor_params_arg = DeclareLaunchArgument(
        'collision_monitor_params_file',
        default_value=default_collision_monitor_params,
        description='Collision monitor parameter file for mapping sessions.',
    )
    patrol_waypoints_arg = DeclareLaunchArgument(
        'patrol_waypoints_file',
        default_value=default_patrol_waypoints,
        description='Waypoint sequence used to sweep the greenhouse during mapping.',
    )
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value=mapping_defaults['use_rviz'],
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
    mapping_strategy_arg = DeclareLaunchArgument(
        'mapping_strategy',
        default_value='sweep_hybrid',
        description='Mapping strategy: sweep_hybrid, patrol_only, or frontier_only.',
    )
    log_level_arg = DeclareLaunchArgument(
        'log_level',
        default_value='info',
        description='Log level for Nav2 nodes.',
    )
    use_frontier_explorer_arg = DeclareLaunchArgument(
        'use_frontier_explorer',
        default_value='false',
        description='Launch the generic frontier explorer for map completion.',
    )
    frontier_autostart_arg = DeclareLaunchArgument(
        'frontier_autostart',
        default_value='true',
        description='Start the frontier explorer automatically.',
    )
    frontier_start_delay_arg = DeclareLaunchArgument(
        'frontier_start_delay_sec',
        default_value='12.0',
        description='Delay before the frontier explorer starts, after SLAM and Nav2 are active.',
    )
    use_patrol_arg = DeclareLaunchArgument(
        'use_patrol',
        default_value='true',
        description='Launch the greenhouse-specific waypoint patrol mapper.',
    )
    patrol_autostart_arg = DeclareLaunchArgument(
        'patrol_autostart',
        default_value='true',
        description='Start the mapping patrol automatically.',
    )
    patrol_completion_action_arg = DeclareLaunchArgument(
        'patrol_completion_action',
        default_value='none',
        description='Optional action to trigger after patrol completion.',
    )
    patrol_start_delay_arg = DeclareLaunchArgument(
        'patrol_start_delay_sec',
        default_value='18.0',
        description='Delay before the autonomous mapping patrol starts, after Nav2 activation.',
    )
    nav_start_delay_arg = DeclareLaunchArgument(
        'nav_start_delay_sec',
        default_value='10.0',
        description='Delay before Nav2 lifecycle activation begins after bootstrap motion.',
    )
    inspect_dwell_arg = DeclareLaunchArgument(
        'inspect_dwell_sec',
        default_value='0.5',
        description='Pause duration at inspection waypoints to densify SLAM scans.',
    )
    stack_start_delay_arg = DeclareLaunchArgument(
        'stack_start_delay_sec',
        default_value='3.0',
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
    configure_mapping_strategy = OpaqueFunction(function=_configure_mapping_strategy)
    frontier_enabled_condition = IfCondition(_bool_expr('use_frontier_explorer'))
    patrol_enabled_condition = IfCondition(_bool_expr('use_patrol'))
    frontier_boundary_condition = IfCondition(
        _all_true_expr('use_frontier_explorer', 'use_boundary_map')
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
            'publish_odom_tf': 'false',
            'cmd_vel_input_topic': '/cmd_vel_checked',
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
            'use_lifecycle_manager': LaunchConfiguration('use_slam_lifecycle_manager'),
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'slam_params_file': LaunchConfiguration('slam_params_file'),
        }.items(),
    )
    delayed_slam_toolbox = TimerAction(
        period=LaunchConfiguration('stack_start_delay_sec'),
        actions=[slam_toolbox],
    )

    collision_monitor = Node(
        package='nav2_collision_monitor',
        executable='collision_monitor',
        name='mapping_collision_monitor',
        output='screen',
        parameters=[
            LaunchConfiguration('collision_monitor_params_file'),
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
        ],
        arguments=['--ros-args', '--log-level', LaunchConfiguration('log_level')],
    )
    delayed_collision_monitor = TimerAction(
        period=LaunchConfiguration('stack_start_delay_sec'),
        actions=[collision_monitor],
    )
    collision_monitor_lifecycle_manager = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_mapping_collision_monitor',
        output='screen',
        parameters=[{
            'autostart': LaunchConfiguration('autostart'),
            'node_names': ['mapping_collision_monitor'],
            'use_sim_time': LaunchConfiguration('use_sim_time'),
        }],
    )
    delayed_collision_monitor_lifecycle_manager = TimerAction(
        period=LaunchConfiguration('stack_start_delay_sec'),
        actions=[collision_monitor_lifecycle_manager],
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
        condition=frontier_boundary_condition,
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
        condition=frontier_boundary_condition,
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
        condition=frontier_enabled_condition,
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
            'max_batch_path_length_m': 6.0,
            'max_lane_segment_length_m': 4.5,
            'already_reached_xy_tolerance_m': 0.45,
            'status_topic': 'mapping_patrol/status',
            'start_service': 'mapping_patrol/start',
            'stop_service': 'mapping_patrol/stop',
            'resume_service': 'mapping_patrol/resume',
            'prefer_lane_heading_on_inspect_waypoints': True,
            'completion_action': LaunchConfiguration('patrol_completion_action'),
            'completion_start_service': 'mapping_explorer/start',
        }],
        condition=patrol_enabled_condition,
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
        *launch_env_actions,
        use_sim_time_arg,
        world_arg,
        boundary_map_arg,
        use_boundary_map_arg,
        slam_params_arg,
        nav2_params_arg,
        frontier_params_arg,
        ekf_params_arg,
        collision_monitor_params_arg,
        patrol_waypoints_arg,
        use_rviz_arg,
        rviz_config_arg,
        autostart_arg,
        use_respawn_arg,
        mapping_strategy_arg,
        log_level_arg,
        use_frontier_explorer_arg,
        frontier_autostart_arg,
        frontier_start_delay_arg,
        use_patrol_arg,
        patrol_autostart_arg,
        patrol_completion_action_arg,
        patrol_start_delay_arg,
        nav_start_delay_arg,
        inspect_dwell_arg,
        stack_start_delay_arg,
        boundary_lifecycle_delay_arg,
        slam_lifecycle_manager_arg,
        shutdown_cleanup_handler,
        configure_mapping_strategy,
        simulation,
        delayed_ekf_filter,
        delayed_slam_toolbox,
        delayed_exploration_boundary_map_server,
        delayed_exploration_boundary_lifecycle_manager,
        delayed_collision_monitor,
        delayed_collision_monitor_lifecycle_manager,
        delayed_navigation_nodes,
        delayed_navigation_lifecycle_manager,
        delayed_frontier_explorer,
        delayed_mapping_patrol,
        rviz,
    ])
