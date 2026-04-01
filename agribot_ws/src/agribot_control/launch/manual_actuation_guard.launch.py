# 이 런치 파일은 상위 제어와 의사결정 패키지의 노드와 의존 구성을 한 번에 실행하도록 묶는다.
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # 실행 description을 생성한다.
    default_config = os.path.join(
        get_package_share_directory('agribot_control'),
        'config',
        'manual_actuation_guard.yaml',
    )

    config_file_arg = DeclareLaunchArgument(
        'config_file',
        default_value=default_config,
        description='Parameter file for manual actuation guard node.',
    )

    guard_node = Node(
        package='agribot_control',
        executable='manual_actuation_guard_node',
        name='manual_actuation_guard_node',
        output='screen',
        parameters=[LaunchConfiguration('config_file')],
    )

    return LaunchDescription([
        config_file_arg,
        guard_node,
    ])
