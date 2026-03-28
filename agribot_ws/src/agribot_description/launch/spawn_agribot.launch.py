"""
AgriBot Spawn Launch File
Launches the AgriBot robot model in a Gazebo Harmonic simulation world
with ros_gz_bridge for sensor data and command topics.

Usage:
    ros2 launch agribot_description spawn_agribot.launch.py
"""

import os
from pathlib import Path
import sys
import uuid
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


def load_file(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)
    try:
        with open(absolute_file_path, 'r') as file:
            return file.read()
    except EnvironmentError:
        return None


def generate_launch_description():
    # Package paths
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')
    gz_partition = LaunchConfiguration('gz_partition', default='agribot_sim')

    # Set Gazebo resource path to find models
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=[
            os.path.join(pkg_agribot_description, 'models'),
            ':',
            os.getenv('GZ_SIM_RESOURCE_PATH', '')
        ]
    )
    gz_partition_env = SetEnvironmentVariable(
        name='GZ_PARTITION',
        value=gz_partition,
    )
    # Launch arguments
    world_arg = DeclareLaunchArgument(
        'world',
        default_value=os.path.join(
            pkg_agribot_description, 'worlds', 'farm_world.sdf'
        ),
        description='Path to the Gazebo world file'
    )
    gz_args_prefix_arg = DeclareLaunchArgument(
        'gz_args_prefix',
        default_value='-r',
        description=(
            'Arguments passed to gz sim before the world path. '
            'Use "-r -s --headless-rendering" for headless server-only runs.'
        ),
    )
    publish_map_to_odom_tf_arg = DeclareLaunchArgument(
        'publish_map_to_odom_tf',
        default_value='true',
        description=(
            'Publish a temporary static map -> odom transform. '
            'Disable this when SLAM or localization provides map -> odom.'
        ),
    )
    publish_odom_tf_arg = DeclareLaunchArgument(
        'publish_odom_tf',
        default_value='true',
        description=(
            'Publish odom -> base_link from bridged /odom. '
            'Disable this when an EKF or another estimator owns odom -> base_link.'
        ),
    )
    cmd_vel_input_topic_arg = DeclareLaunchArgument(
        'cmd_vel_input_topic',
        default_value='/cmd_vel',
        description='Input command velocity topic consumed by the watchdog.',
    )
    cmd_vel_output_topic_arg = DeclareLaunchArgument(
        'cmd_vel_output_topic',
        default_value='/cmd_vel_safe',
        description='Output command velocity topic published by the watchdog.',
    )
    use_camera_bridges_arg = DeclareLaunchArgument(
        'use_camera_bridges',
        default_value='true',
        description='Launch RGB-D camera bridges. Disable during LiDAR-only mapping to reduce load.',
    )

    graphics_env_actions = build_graphics_environment_actions(
        include_gazebo_renderer=True,
    )

    # Gazebo Harmonic simulation
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            # Start the simulation immediately so bridged sensor topics publish
            # without requiring a manual "play" click in the Gazebo GUI.
            'gz_args': [LaunchConfiguration('gz_args_prefix'), ' ', LaunchConfiguration('world')],
        }.items(),
    )

    # ==================== ros_gz_bridge ====================
    # Bridges Gazebo topics ↔ ROS 2 topics
    # Format: /gz_topic@ros_type[gz_type  (GZ→ROS)
    # Format: /gz_topic@ros_type]gz_type  (ROS→GZ)
    state_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_state_bridge',
        arguments=[
            # Clock — GZ → ROS
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            # IMU — GZ → ROS
            '/agribot/imu@sensor_msgs/msg/Imu[gz.msgs.IMU',
            # Command velocity goes through a watchdog so stale teleop / Nav2
            # commands are turned into an explicit zero-twist stop.
            '/cmd_vel_safe@geometry_msgs/msg/Twist]gz.msgs.Twist',
            # Odometry — GZ → ROS
            '/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            # Joint States — GZ → ROS
            '/world/farm_world/model/agribot/joint_state@sensor_msgs/msg/JointState[gz.msgs.Model',
            # Harvest arm position command — ROS → GZ
            '/agribot/harvest_arm_joint/cmd_pos@std_msgs/msg/Float64]gz.msgs.Double',
        ],
        remappings=[
            ('/clock', '/clock_raw'),
            ('/odom', '/odom_raw'),
            ('/world/farm_world/model/agribot/joint_state', '/joint_states_raw'),
        ],
        output='screen',
    )

    sim_time_guard = Node(
        package='agribot_description',
        executable='sim_time_guard',
        name='sim_time_guard',
        output='screen',
        parameters=[{
            # Guard the bridged simulation time and state streams with wall-time
            # processing so stale samples never roll the ROS clock backwards.
            'use_sim_time': False,
        }],
    )

    cmd_vel_watchdog = Node(
        package='agribot_description',
        executable='cmd_vel_watchdog',
        name='cmd_vel_watchdog',
        parameters=[{
            'use_sim_time': True,
            'input_topic': LaunchConfiguration('cmd_vel_input_topic'),
            'output_topic': LaunchConfiguration('cmd_vel_output_topic'),
        }],
        output='screen',
    )

    camera_info_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_camera_info_bridge',
        arguments=[
            '/agribot/camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
        ],
        condition=IfCondition(LaunchConfiguration('use_camera_bridges')),
        output='screen',
    )

    lidar_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_lidar_bridge',
        arguments=[
            '/agribot/lidar@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
        ],
        remappings=[
            ('/agribot/lidar', '/agribot/lidar_raw'),
        ],
        output='screen',
    )

    # Dedicated image_bridge is more reliable than a monolithic parameter_bridge
    # for large RGB / depth image payloads in this simulation.
    camera_image_bridge = Node(
        package='ros_gz_image',
        executable='image_bridge',
        name='ros_gz_camera_image_bridge',
        arguments=['/agribot/camera/image'],
        condition=IfCondition(LaunchConfiguration('use_camera_bridges')),
        output='screen',
    )

    camera_depth_bridge = Node(
        package='ros_gz_image',
        executable='image_bridge',
        name='ros_gz_camera_depth_bridge',
        arguments=['/agribot/camera/depth_image'],
        condition=IfCondition(LaunchConfiguration('use_camera_bridges')),
        output='screen',
    )

    # Gazebo publishes odometry on /odom, but RViz and tf2 also need the same
    # relation on /tf so the robot body and sensors form one frame tree.
    odom_tf_broadcaster = Node(
        package='agribot_description',
        executable='odom_tf_broadcaster',
        name='odom_tf_broadcaster',
        parameters=[{
            'use_sim_time': True,
            'reset_on_time_jump_sec': 1.0,
        }],
        condition=IfCondition(LaunchConfiguration('publish_odom_tf')),
        output='screen',
    )

    map_to_odom_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='map_to_odom_tf',
        arguments=[
            '--x', '0',
            '--y', '0',
            '--z', '0',
            '--roll', '0',
            '--pitch', '0',
            '--yaw', '0',
            '--frame-id', 'map',
            '--child-frame-id', 'odom',
        ],
        condition=IfCondition(LaunchConfiguration('publish_map_to_odom_tf')),
        parameters=[{'use_sim_time': True}],
        output='screen',
    )

    # Robot State Publisher
    # RViz needs the URDF (on /robot_description topic) to display the robot body.
    urdf_file = os.path.join(pkg_agribot_description, 'urdf', 'agribot.urdf')
    with open(urdf_file, 'r') as infp:
        robot_description_content = infp.read()

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'robot_description': robot_description_content,
        }]
    )

    return LaunchDescription([
        *graphics_env_actions,
        gz_resource_path,
        gz_partition_env,
        world_arg,
        gz_args_prefix_arg,
        publish_map_to_odom_tf_arg,
        publish_odom_tf_arg,
        cmd_vel_input_topic_arg,
        cmd_vel_output_topic_arg,
        use_camera_bridges_arg,
        gz_sim,
        robot_state_publisher,
        cmd_vel_watchdog,
        state_bridge,
        sim_time_guard,
        camera_info_bridge,
        lidar_bridge,
        camera_image_bridge,
        camera_depth_bridge,
        odom_tf_broadcaster,
        map_to_odom_tf,
    ])
