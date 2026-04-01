# 이 런치 파일은 IoT 장치 연동 패키지의 노드와 의존 구성을 한 번에 실행하도록 묶는다.
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


def generate_launch_description():
    # 실행 description을 생성한다.
    package_share = get_package_share_directory('agribot_iot')
    default_params = os.path.join(package_share, 'config', 'fan_controller.yaml')

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time for fan controller node.',
    )
    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='Fan controller parameter file.',
    )

    fan_controller_node = Node(
        package='agribot_iot',
        executable='fan_controller_node',
        name='fan_controller_node',
        output='screen',
        parameters=[
            LaunchConfiguration('params_file'),
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
        ],
    )

    return LaunchDescription([
        use_sim_time_arg,
        params_file_arg,
        fan_controller_node,
    ])
