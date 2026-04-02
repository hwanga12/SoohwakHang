# 이 런치 파일은 인지와 추론 패키지의 노드와 의존 구성을 한 번에 실행하도록 묶는다.
from __future__ import annotations

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
import os


def generate_launch_description() -> LaunchDescription:
    # 실행 description을 생성한다.
    config_file = os.path.join(
        get_package_share_directory('agribot_perception'),
        'config',
        'thin_inference.yaml',
    )
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use Gazebo /clock when running inside simulation.',
    )
    image_topic_arg = DeclareLaunchArgument(
        'image_topic',
        default_value='/agribot/camera/image',
        description='RGB image topic produced by the Gazebo camera bridge.',
    )
    backend_confirm_url_arg = DeclareLaunchArgument(
        'backend_confirm_url',
        default_value='http://127.0.0.1:8000/api/v1/inference/confirm',
        description='FastAPI endpoint that runs the backend confirmation pass.',
    )
    python_executable_arg = DeclareLaunchArgument(
        'python_executable',
        default_value=EnvironmentVariable(
            'AGRIBOT_PERCEPTION_PYTHON',
            default_value='python3',
        ),
        description='Python interpreter used to launch the thin inference node.',
    )

    thin_inference = ExecuteProcess(
        cmd=[
            LaunchConfiguration('python_executable'),
            '-m',
            'agribot_perception.thin_inference_node',
            '--ros-args',
            '--params-file',
            config_file,
            '-p',
            ['use_sim_time:=', LaunchConfiguration('use_sim_time')],
            '-p',
            ['image_topic:=', LaunchConfiguration('image_topic')],
            '-p',
            ['backend_confirm_url:=', LaunchConfiguration('backend_confirm_url')],
        ],
        name='thin_inference_node',
        output='screen',
    )

    return LaunchDescription([
        use_sim_time_arg,
        image_topic_arg,
        backend_confirm_url_arg,
        python_executable_arg,
        thin_inference,
    ])
