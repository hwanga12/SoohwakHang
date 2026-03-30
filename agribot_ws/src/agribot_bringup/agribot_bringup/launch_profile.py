from __future__ import annotations

# 런치 진입점마다 같은 그래픽/네트워크/성능 규칙을 쓰도록 환경 변수를 한곳에서 관리한다.
import os

from launch.actions import SetEnvironmentVariable

from .shutdown_cleanup import LAUNCH_SESSION_ENV_VAR, resolve_launch_session_id


GRAPHICS_PROFILE_ENV_VAR = 'AGRIBOT_GRAPHICS_PROFILE'
# 기본 런치는 호스트 기본 그래픽 경로를 그대로 따라가야 팀원별 드라이버 차이에도
# 같은 명령이 더 안정적으로 동작한다. 외장 GPU 강제는 명시 opt-in 으로만 허용한다.
DEFAULT_GRAPHICS_PROFILE = 'system'
_SUPPORTED_GRAPHICS_PROFILES = frozenset({'auto', 'nvidia', 'system'})
ROS_DISCOVERY_RANGE_ENV_VAR = 'AGRIBOT_ROS_DISCOVERY_RANGE'
DEFAULT_ROS_DISCOVERY_RANGE = 'LOCALHOST'
_SUPPORTED_ROS_DISCOVERY_RANGES = frozenset({'SUBNET', 'LOCALHOST', 'OFF', 'SYSTEM_DEFAULT'})
GZ_IP_ENV_VAR = 'AGRIBOT_GZ_IP'
DEFAULT_GZ_IP = '127.0.0.1'
PERFORMANCE_MODE_ENV_VAR = 'AGRIBOT_PERFORMANCE_MODE'
DEFAULT_PERFORMANCE_MODE = 'balanced'
_SUPPORTED_PERFORMANCE_MODES = frozenset({'balanced', 'full'})
_PERFORMANCE_GROUP_DEFAULTS: dict[str, dict[str, dict[str, str]]] = {
    'simulation': {
        'balanced': {
            'gz_args_prefix': '-r',
            'use_iot': 'false',
            'use_perception': 'false',
            'use_rviz': 'true',
            # 기본 시연 경로는 runtime bridge 노드가 항상 살아 있어야
            # frontend/backed 요청이 ROS 주행 토픽으로 실제 연결된다.
            'use_runtime_support': 'true',
        },
        'full': {
            'gz_args_prefix': '-r',
            'use_iot': 'true',
            'use_perception': 'true',
            'use_rviz': 'true',
            'use_runtime_support': 'true',
        },
    },
    'spawn': {
        'balanced': {
            'cmd_vel_watchdog_publish_rate_hz': '10.0',
            'state_bridge_config_name': 'ros_gz_state_bridge_lite.yaml',
            'use_camera_bridges': 'false',
        },
        'full': {
            'cmd_vel_watchdog_publish_rate_hz': '20.0',
            'state_bridge_config_name': 'ros_gz_state_bridge.yaml',
            'use_camera_bridges': 'true',
        },
    },
    'navigation': {
        'balanced': {
            'use_rviz': 'true',
        },
        'full': {
            'use_rviz': 'true',
        },
    },
    'mapping': {
        'balanced': {
            'use_rviz': 'true',
        },
        'full': {
            'use_rviz': 'true',
        },
    },
    'localization': {
        'balanced': {
            'use_rviz': 'true',
        },
        'full': {
            'use_rviz': 'true',
        },
    },
    'runtime_support': {
        'balanced': {
            'mission_command_poll_period_sec': '0.75',
            'pose_write_period_sec': '1.0',
            'robot_command_poll_period_sec': '0.75',
            'semantic_write_period_sec': '30.0',
        },
        'full': {
            'mission_command_poll_period_sec': '0.25',
            'pose_write_period_sec': '0.5',
            'robot_command_poll_period_sec': '0.25',
            'semantic_write_period_sec': '15.0',
        },
    },
}


def resolve_graphics_profile(profile: str | None = None) -> str:
    value = str(
        profile
        if profile is not None
        else os.environ.get(GRAPHICS_PROFILE_ENV_VAR, DEFAULT_GRAPHICS_PROFILE)
    ).strip().lower()
    if not value:
        return DEFAULT_GRAPHICS_PROFILE
    if value not in _SUPPORTED_GRAPHICS_PROFILES:
        raise ValueError(
            f'Unsupported {GRAPHICS_PROFILE_ENV_VAR}: {value}. '
            f'Expected one of: {sorted(_SUPPORTED_GRAPHICS_PROFILES)}'
        )
    if value == 'auto':
        return 'nvidia' if os.path.exists('/usr/bin/nvidia-smi') else 'system'
    return value


def resolve_performance_mode(mode: str | None = None) -> str:
    value = str(
        mode
        if mode is not None
        else os.environ.get(PERFORMANCE_MODE_ENV_VAR, DEFAULT_PERFORMANCE_MODE)
    ).strip().lower()
    if not value:
        return DEFAULT_PERFORMANCE_MODE
    if value not in _SUPPORTED_PERFORMANCE_MODES:
        raise ValueError(
            f'Unsupported {PERFORMANCE_MODE_ENV_VAR}: {value}. '
            f'Expected one of: {sorted(_SUPPORTED_PERFORMANCE_MODES)}'
        )
    return value


def resolve_performance_defaults(
    group: str,
    mode: str | None = None,
) -> dict[str, str]:
    group_defaults = _PERFORMANCE_GROUP_DEFAULTS.get(group)
    if group_defaults is None:
        raise ValueError(
            f'Unsupported performance defaults group: {group}. '
            f'Expected one of: {sorted(_PERFORMANCE_GROUP_DEFAULTS)}'
        )

    resolved_mode = resolve_performance_mode(mode)
    return dict(group_defaults[resolved_mode])


def build_graphics_environment_actions(
    *,
    profile: str | None = None,
    include_gazebo_renderer: bool = False,
) -> list[SetEnvironmentVariable]:
    resolved_profile = resolve_graphics_profile(profile)
    actions: list[SetEnvironmentVariable] = [
        SetEnvironmentVariable(GRAPHICS_PROFILE_ENV_VAR, resolved_profile),
    ]
    if resolved_profile != 'nvidia':
        return actions

    actions.extend(
        [
            SetEnvironmentVariable('DRI_PRIME', '1'),
            SetEnvironmentVariable('__NV_PRIME_RENDER_OFFLOAD', '1'),
            SetEnvironmentVariable('__GLX_VENDOR_LIBRARY_NAME', 'nvidia'),
        ]
    )
    if include_gazebo_renderer:
        actions.extend(
            [
                SetEnvironmentVariable('__VK_LAYER_NV_optimus', 'NVIDIA_only'),
                SetEnvironmentVariable('GBM_BACKEND', 'nvidia-drm'),
                SetEnvironmentVariable('GZ_SIM_RENDER_ENGINE', 'ogre2'),
            ]
        )
    return actions


def resolve_ros_discovery_range(value: str | None = None) -> str:
    normalized = str(
        value
        if value is not None
        else os.environ.get(ROS_DISCOVERY_RANGE_ENV_VAR, DEFAULT_ROS_DISCOVERY_RANGE)
    ).strip().upper()
    if not normalized:
        return DEFAULT_ROS_DISCOVERY_RANGE
    if normalized not in _SUPPORTED_ROS_DISCOVERY_RANGES:
        raise ValueError(
            f'Unsupported {ROS_DISCOVERY_RANGE_ENV_VAR}: {normalized}. '
            f'Expected one of: {sorted(_SUPPORTED_ROS_DISCOVERY_RANGES)}'
        )
    return normalized


def resolve_gz_ip(value: str | None = None) -> str:
    normalized = str(
        value
        if value is not None
        else os.environ.get(GZ_IP_ENV_VAR, DEFAULT_GZ_IP)
    ).strip()
    return normalized or DEFAULT_GZ_IP


def build_transport_environment_actions(
    *,
    ros_discovery_range: str | None = None,
    gz_ip: str | None = None,
) -> list[SetEnvironmentVariable]:
    return [
        SetEnvironmentVariable(
            'ROS_AUTOMATIC_DISCOVERY_RANGE',
            resolve_ros_discovery_range(ros_discovery_range),
        ),
        SetEnvironmentVariable(
            'GZ_IP',
            resolve_gz_ip(gz_ip),
        ),
    ]


def build_launch_session_environment_actions(
    session_id: str | None = None,
    *,
    profile: str | None = None,
    include_gazebo_renderer: bool = False,
    ros_discovery_range: str | None = None,
    gz_ip: str | None = None,
    performance_mode: str | None = None,
) -> list[SetEnvironmentVariable]:
    resolved_session_id = resolve_launch_session_id(session_id)
    return [
        SetEnvironmentVariable(LAUNCH_SESSION_ENV_VAR, resolved_session_id),
        SetEnvironmentVariable(
            PERFORMANCE_MODE_ENV_VAR,
            resolve_performance_mode(performance_mode),
        ),
        *build_transport_environment_actions(
            ros_discovery_range=ros_discovery_range,
            gz_ip=gz_ip,
        ),
        *build_graphics_environment_actions(
            profile=profile,
            include_gazebo_renderer=include_gazebo_renderer,
        ),
    ]
