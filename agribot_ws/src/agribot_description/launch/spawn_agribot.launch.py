"""
AgriBot Spawn Launch File
Launches the AgriBot robot model in a Gazebo Harmonic simulation world
with ros_gz_bridge for sensor data and command topics.

Usage:
    ros2 launch agribot_description spawn_agribot.launch.py
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Package paths
    pkg_agribot_description = get_package_share_directory('agribot_description')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')

    # Set Gazebo resource path to find models
    gz_resource_path = SetEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=[
            os.path.join(pkg_agribot_description, 'models'),
            ':',
            os.getenv('GZ_SIM_RESOURCE_PATH', '')
        ]
    )

    # Launch arguments
    world_arg = DeclareLaunchArgument(
        'world',
        default_value=os.path.join(
            pkg_agribot_description, 'worlds', 'farm_world.sdf'
        ),
        description='Path to the Gazebo world file'
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
            # Command Velocity — ROS → GZ (for teleop and Nav2)
            '/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
            # Odometry — GZ → ROS
            '/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry',
        ],
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

    return LaunchDescription([
        gz_resource_path,
        world_arg,
        gz_sim,
        state_bridge,
        camera_info_bridge,
        lidar_bridge,
        camera_image_bridge,
        camera_depth_bridge,
    ])
