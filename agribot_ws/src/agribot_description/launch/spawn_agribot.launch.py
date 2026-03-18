"""
AgriBot Spawn Launch File
Launches the AgriBot robot model in a Gazebo Harmonic simulation world
with ros_gz_bridge for sensor data and command topics.

Usage:
    ros2 launch agribot_description spawn_agribot.launch.py
"""

import os
import uuid
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Package paths
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')
    gz_partition = f"agribot_{os.getenv('USER', 'ssafy')}_{uuid.uuid4().hex[:8]}"

    gpu_env_actions = []
    if os.path.exists('/usr/bin/nvidia-smi'):
        gpu_env_actions = [
            SetEnvironmentVariable('DRI_PRIME', '1'),
            SetEnvironmentVariable('__NV_PRIME_RENDER_OFFLOAD', '1'),
            SetEnvironmentVariable('__GLX_VENDOR_LIBRARY_NAME', 'nvidia'),
        ]

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
    publish_map_to_odom_tf_arg = DeclareLaunchArgument(
        'publish_map_to_odom_tf',
        default_value='true',
        description=(
            'Publish a temporary static map -> odom transform. '
            'Disable this when SLAM or localization provides map -> odom.'
        ),
    )

    # Gazebo Harmonic simulation
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            # Start the simulation immediately so bridged sensor topics publish
            # without requiring a manual "play" click in the Gazebo GUI.
            'gz_args': ['-r ', LaunchConfiguration('world')],
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
        ],
        output='screen',
    )

    cmd_vel_watchdog = Node(
        package='agribot_description',
        executable='cmd_vel_watchdog',
        name='cmd_vel_watchdog',
        output='screen',
    )

    camera_info_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_camera_info_bridge',
        arguments=[
            '/agribot/camera/camera_info@sensor_msgs/msg/CameraInfo[gz.msgs.CameraInfo',
        ],
        output='screen',
    )

    lidar_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='ros_gz_lidar_bridge',
        arguments=[
            '/agribot/lidar/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
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
        output='screen',
    )

    camera_depth_bridge = Node(
        package='ros_gz_image',
        executable='image_bridge',
        name='ros_gz_camera_depth_bridge',
        arguments=['/agribot/camera/depth_image'],
        output='screen',
    )

    # Gazebo publishes odometry on /odom, but RViz and tf2 also need the same
    # relation on /tf so the robot body and sensors form one frame tree.
    odom_tf_broadcaster = Node(
        package='agribot_description',
        executable='odom_tf_broadcaster',
        name='odom_tf_broadcaster',
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
        output='screen',
    )

    base_to_camera_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_link_to_camera_link_tf',
        arguments=[
            '--x', '0.2',
            '--y', '0',
            '--z', '0.1',
            '--roll', '0',
            '--pitch', '0',
            '--yaw', '0',
            '--frame-id', 'base_link',
            '--child-frame-id', 'camera_link',
        ],
        output='screen',
    )

    base_to_lidar_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_link_to_lidar_link_tf',
        arguments=[
            '--x', '0',
            '--y', '0',
            '--z', '0.15',
            '--roll', '0',
            '--pitch', '0',
            '--yaw', '0',
            '--frame-id', 'base_link',
            '--child-frame-id', 'lidar_link',
        ],
        output='screen',
    )

    base_to_imu_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_link_to_imu_link_tf',
        arguments=[
            '--x', '0',
            '--y', '0',
            '--z', '0.05',
            '--roll', '0',
            '--pitch', '0',
            '--yaw', '0',
            '--frame-id', 'base_link',
            '--child-frame-id', 'imu_link',
        ],
        output='screen',
    )

    return LaunchDescription([
        *gpu_env_actions,
        gz_resource_path,
        gz_partition_env,
        world_arg,
        publish_map_to_odom_tf_arg,
        gz_sim,
        cmd_vel_watchdog,
        state_bridge,
        camera_info_bridge,
        lidar_bridge,
        camera_image_bridge,
        camera_depth_bridge,
        odom_tf_broadcaster,
        map_to_odom_tf,
        base_to_camera_tf,
        base_to_lidar_tf,
        base_to_imu_tf,
    ])
