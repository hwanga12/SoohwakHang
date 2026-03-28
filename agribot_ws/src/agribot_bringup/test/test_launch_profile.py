"""런치 프로필 기본값과 환경 변수 조합이 기대대로 풀리는지 검증한다."""

from launch.actions import SetEnvironmentVariable
import pytest

from agribot_bringup.launch_profile import (
    DEFAULT_GZ_IP,
    DEFAULT_PERFORMANCE_MODE,
    DEFAULT_ROS_DISCOVERY_RANGE,
    GRAPHICS_PROFILE_ENV_VAR,
    PERFORMANCE_MODE_ENV_VAR,
    build_graphics_environment_actions,
    build_launch_session_environment_actions,
    build_transport_environment_actions,
    resolve_gz_ip,
    resolve_graphics_profile,
    resolve_performance_defaults,
    resolve_performance_mode,
    resolve_ros_discovery_range,
)


def _action_map(actions: list[SetEnvironmentVariable]) -> dict[str, str]:
    result: dict[str, str] = {}
    for action in actions:
        name = getattr(action, '_SetEnvironmentVariable__name', [])
        value = getattr(action, '_SetEnvironmentVariable__value', [])
        if not name or not value:
            continue
        result[getattr(name[0], 'text', '')] = getattr(value[0], 'text', '')
    return result


def test_resolve_graphics_profile_defaults_to_system_without_nvidia(monkeypatch) -> None:
    monkeypatch.delenv(GRAPHICS_PROFILE_ENV_VAR, raising=False)
    monkeypatch.setattr('agribot_bringup.launch_profile.os.path.exists', lambda _path: False)

    assert resolve_graphics_profile() == 'system'


def test_resolve_graphics_profile_defaults_to_nvidia_when_available(monkeypatch) -> None:
    monkeypatch.delenv(GRAPHICS_PROFILE_ENV_VAR, raising=False)
    monkeypatch.setattr('agribot_bringup.launch_profile.os.path.exists', lambda _path: True)

    assert resolve_graphics_profile() == 'nvidia'


def test_build_graphics_environment_actions_for_nvidia_profile() -> None:
    action_map = _action_map(
        build_graphics_environment_actions(
            profile='nvidia',
            include_gazebo_renderer=True,
        )
    )

    assert action_map[GRAPHICS_PROFILE_ENV_VAR] == 'nvidia'
    assert action_map['DRI_PRIME'] == '1'
    assert action_map['__NV_PRIME_RENDER_OFFLOAD'] == '1'
    assert action_map['__GLX_VENDOR_LIBRARY_NAME'] == 'nvidia'
    assert action_map['GBM_BACKEND'] == 'nvidia-drm'
    assert action_map['GZ_SIM_RENDER_ENGINE'] == 'ogre2'


def test_build_launch_session_environment_actions_include_session_and_profile() -> None:
    action_map = _action_map(
        build_launch_session_environment_actions(
            session_id='session-137-launch-profile',
            profile='system',
            performance_mode='full',
        )
    )

    assert action_map['AGRIBOT_LAUNCH_SESSION_ID'] == 'session-137-launch-profile'
    assert action_map[PERFORMANCE_MODE_ENV_VAR] == 'full'
    assert action_map['ROS_AUTOMATIC_DISCOVERY_RANGE'] == DEFAULT_ROS_DISCOVERY_RANGE
    assert action_map['GZ_IP'] == DEFAULT_GZ_IP
    assert action_map[GRAPHICS_PROFILE_ENV_VAR] == 'system'
    assert 'DRI_PRIME' not in action_map


def test_resolve_graphics_profile_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError):
        resolve_graphics_profile('hybrid')


def test_build_transport_environment_actions_support_local_only_defaults() -> None:
    action_map = _action_map(build_transport_environment_actions())

    assert action_map['ROS_AUTOMATIC_DISCOVERY_RANGE'] == DEFAULT_ROS_DISCOVERY_RANGE
    assert action_map['GZ_IP'] == DEFAULT_GZ_IP


def test_resolve_ros_discovery_range_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        resolve_ros_discovery_range('campus')


def test_resolve_gz_ip_falls_back_to_loopback() -> None:
    assert resolve_gz_ip('') == DEFAULT_GZ_IP


def test_resolve_performance_mode_defaults_to_balanced(monkeypatch) -> None:
    monkeypatch.delenv(PERFORMANCE_MODE_ENV_VAR, raising=False)

    assert resolve_performance_mode() == DEFAULT_PERFORMANCE_MODE


def test_resolve_performance_defaults_for_balanced_profile() -> None:
    defaults = resolve_performance_defaults('simulation', 'balanced')

    assert defaults['gz_args_prefix'] == '-r'
    assert defaults['use_rviz'] == 'true'
    assert defaults['use_runtime_support'] == 'false'
