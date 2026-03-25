from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
import os


def _include_launch(package_share: str, launch_file: str, launch_arguments: dict[str, object]):
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(package_share, 'launch', launch_file)),
        launch_arguments={key: value for key, value in launch_arguments.items()}.items(),
    )


def generate_launch_description():
    package_share = get_package_share_directory('agribot_iot')
    control_share = get_package_share_directory('agribot_control')

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
        common_args,
    )
    watering_controller = _include_launch(
        package_share,
        'watering_controller.launch.py',
        common_args,
    )
    curtain_controller = _include_launch(
        package_share,
        'curtain_controller.launch.py',
        common_args,
    )
    fan_controller = _include_launch(
        package_share,
        'fan_controller.launch.py',
        common_args,
    )
    nutrient_controller = _include_launch(
        package_share,
        'nutrient_controller.launch.py',
        common_args,
    )
    sprinkler_controller = _include_launch(
        package_share,
        'sprinkler_controller.launch.py',
        common_args,
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
        environment_sensor,
        watering_controller,
        curtain_controller,
        fan_controller,
        nutrient_controller,
        sprinkler_controller,
        manual_actuation_guard,
        mqtt_bridge,
    ])
