from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node
import os


def generate_launch_description():
    package_share = get_package_share_directory('agribot_navigation')
    default_params = os.path.join(package_share, 'config', 'harvest_action_server.yaml')

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation time for the harvest action server.',
    )
    params_file_arg = DeclareLaunchArgument(
        'params_file',
        default_value=default_params,
        description='Harvest action server parameter file.',
    )
    runtime_dir_arg = DeclareLaunchArgument(
        'runtime_dir',
        default_value=EnvironmentVariable('AGRIBOT_RUNTIME_DIR', default_value='/tmp/agribot_runtime'),
        description='Shared runtime directory for harvest runtime artifacts.',
    )
    runtime_dir_env = SetEnvironmentVariable(
        'AGRIBOT_RUNTIME_DIR',
        LaunchConfiguration('runtime_dir'),
    )

    harvest_action_server = Node(
        package='agribot_navigation',
        executable='harvest_action_server',
        name='harvest_action_server',
        output='screen',
        parameters=[
            LaunchConfiguration('params_file'),
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
        ],
    )

    return LaunchDescription([
        use_sim_time_arg,
        params_file_arg,
        runtime_dir_arg,
        runtime_dir_env,
        harvest_action_server,
    ])
