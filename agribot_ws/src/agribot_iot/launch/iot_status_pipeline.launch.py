# 이 런치 파일은 IoT 장치 연동 패키지의 노드와 의존 구성을 한 번에 실행하도록 묶는다.
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
import os


def _include_launch(package_share: str, launch_file: str, launch_arguments: dict[str, object]):
    # include 실행 정보를 계산해 반환한다.
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(package_share, 'launch', launch_file)),
        launch_arguments={key: value for key, value in launch_arguments.items()}.items(),
    )


def generate_launch_description():
    # 실행 description을 생성한다.
    package_share = get_package_share_directory('agribot_iot')
    control_share = get_package_share_directory('agribot_control')
    config_dir = os.path.join(package_share, 'config')

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time for the IoT status pipeline.',
    )
    force_log_only_arg = DeclareLaunchArgument(
        'force_log_only',
        default_value='false',
        description='Force the MQTT bridge into log-only mode.',
    )

    common_args = {
        'use_sim_time': LaunchConfiguration('use_sim_time'),
    }

    environment_sensor = _include_launch(
        package_share,
        'environment_sensor.launch.py',
        {
            **common_args,
            'params_file': os.path.join(config_dir, 'environment_sensor.yaml'),
        },
    )
    watering_controller = _include_launch(
        package_share,
        'watering_controller.launch.py',
        {
            **common_args,
            'params_file': os.path.join(config_dir, 'watering_controller.yaml'),
        },
    )
    nutrient_controller = _include_launch(
        package_share,
        'nutrient_controller.launch.py',
        {
            **common_args,
            'params_file': os.path.join(config_dir, 'nutrient_controller.yaml'),
        },
    )
    sprinkler_controller = _include_launch(
        package_share,
        'sprinkler_controller.launch.py',
        {
            **common_args,
            'params_file': os.path.join(config_dir, 'sprinkler_controller.yaml'),
        },
    )
    manual_actuation_guard = _include_launch(
        control_share,
        'manual_actuation_guard.launch.py',
        {},
    )
    mqtt_bridge = _include_launch(
        package_share,
        'mqtt_bridge.launch.py',
        {
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'force_log_only': LaunchConfiguration('force_log_only'),
        },
    )

    return LaunchDescription([
        use_sim_time_arg,
        force_log_only_arg,
        # Keep standalone IoT launches on the same local ROS graph as the backend
        # even when the user launches this file without sourcing agribot_env.sh.
        SetEnvironmentVariable(
            'ROS_DOMAIN_ID',
            EnvironmentVariable('ROS_DOMAIN_ID', default_value='42'),
        ),
        SetEnvironmentVariable(
            'ROS_AUTOMATIC_DISCOVERY_RANGE',
            EnvironmentVariable('AGRIBOT_ROS_DISCOVERY_RANGE', default_value='LOCALHOST'),
        ),
        SetEnvironmentVariable(
            'GZ_PARTITION',
            EnvironmentVariable('GZ_PARTITION', default_value='agribot_sim'),
        ),
        environment_sensor,
        watering_controller,
        nutrient_controller,
        sprinkler_controller,
        manual_actuation_guard,
        mqtt_bridge,
    ])
