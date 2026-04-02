# 이 런치 파일은 상위 제어와 의사결정 패키지의 노드와 의존 구성을 한 번에 실행하도록 묶는다.
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import os


def generate_launch_description():
    # 실행 description을 생성한다.
    package_share = get_package_share_directory('agribot_control')
    default_params = os.path.join(package_share, 'config', 'actuation_request.yaml')

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time for actuation request node.',
    )
    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='Actuation request parameter file.',
    )

    actuation_request_node = Node(
        package='agribot_control',
        executable='actuation_request_node',
        name='actuation_request_node',
        output='screen',
        parameters=[
            LaunchConfiguration('params_file'),
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
        ],
    )

    return LaunchDescription([
        use_sim_time_arg,
        params_file_arg,
        actuation_request_node,
    ])
