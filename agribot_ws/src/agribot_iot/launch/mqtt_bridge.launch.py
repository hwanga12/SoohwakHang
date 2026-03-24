from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


def generate_launch_description():
    package_share = get_package_share_directory('agribot_iot')
    default_params = os.path.join(package_share, 'config', 'mqtt_bridge.yaml')

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time for MQTT bridge node.',
    )
    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='MQTT bridge parameter file.',
    )

    mqtt_bridge_node = Node(
        package='agribot_iot',
        executable='mqtt_bridge_node',
        name='mqtt_bridge_node',
        output='screen',
        parameters=[
            LaunchConfiguration('params_file'),
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
        ],
    )

    return LaunchDescription([
        use_sim_time_arg,
        params_file_arg,
        mqtt_bridge_node,
    ])
