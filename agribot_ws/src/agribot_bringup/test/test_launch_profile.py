# 이 테스트는 통합 실행과 런치 조율 패키지의 launch profile 동작을 검증한다.
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
    # action 지도 정보를 계산해 반환한다.
    result: dict[str, str] = {}
    for action in actions:
        name = getattr(action, '_SetEnvironmentVariable__name', [])
        value = getattr(action, '_SetEnvironmentVariable__value', [])
        if not name or not value:
            continue
        result[getattr(name[0], 'text', '')] = getattr(value[0], 'text', '')
    return result


def test_resolve_graphics_profile_defaults_to_system_without_nvidia(monkeypatch) -> None:
    # resolve graphics 프로필 defaults TO system without nvidia 동작과 회귀 여부를 검증한다.
    monkeypatch.delenv(GRAPHICS_PROFILE_ENV_VAR, raising=False)
    monkeypatch.setattr('agribot_bringup.launch_profile.os.path.exists', lambda _path: False)

    assert resolve_graphics_profile() == 'system'


def test_resolve_graphics_profile_defaults_to_system_even_when_nvidia_exists(monkeypatch) -> None:
    # resolve graphics 프로필 defaults TO system even when nvidia exists 동작과 회귀 여부를 검증한다.
    monkeypatch.delenv(GRAPHICS_PROFILE_ENV_VAR, raising=False)
    monkeypatch.setattr('agribot_bringup.launch_profile.os.path.exists', lambda _path: True)

    assert resolve_graphics_profile() == 'system'


def test_resolve_graphics_profile_auto_uses_nvidia_when_available(monkeypatch) -> None:
    # resolve graphics 프로필 auto uses nvidia when 사용 가능 상태 동작과 회귀 여부를 검증한다.
    monkeypatch.setattr('agribot_bringup.launch_profile.os.path.exists', lambda _path: True)

    assert resolve_graphics_profile('auto') == 'nvidia'


def test_resolve_graphics_profile_auto_falls_back_to_system_without_nvidia(monkeypatch) -> None:
    # resolve graphics 프로필 auto falls back TO system without nvidia 동작과 회귀 여부를 검증한다.
    monkeypatch.setattr('agribot_bringup.launch_profile.os.path.exists', lambda _path: False)

    assert resolve_graphics_profile('auto') == 'system'


def test_resolve_graphics_profile_empty_value_falls_back_to_default() -> None:
    # resolve graphics 프로필 empty value falls back TO default 동작과 회귀 여부를 검증한다.
    assert resolve_graphics_profile() == 'system'
    assert resolve_graphics_profile('') == 'system'


def test_build_graphics_environment_actions_for_nvidia_profile() -> None:
    # build graphics environment actions FOR nvidia 프로필 동작과 회귀 여부를 검증한다.
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
    # build launch session environment actions include session AND 프로필 동작과 회귀 여부를 검증한다.
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
    # resolve graphics 프로필 rejects unknown 프로필 동작과 회귀 여부를 검증한다.
    with pytest.raises(ValueError):
        resolve_graphics_profile('hybrid')


def test_build_transport_environment_actions_support_local_only_defaults() -> None:
    # build transport environment actions support local only defaults 동작과 회귀 여부를 검증한다.
    action_map = _action_map(build_transport_environment_actions())

    assert action_map['ROS_AUTOMATIC_DISCOVERY_RANGE'] == DEFAULT_ROS_DISCOVERY_RANGE
    assert action_map['GZ_IP'] == DEFAULT_GZ_IP


def test_resolve_ros_discovery_range_rejects_unknown_value() -> None:
    # resolve ROS discovery range rejects unknown value 동작과 회귀 여부를 검증한다.
    with pytest.raises(ValueError):
        resolve_ros_discovery_range('campus')


def test_resolve_gz_ip_falls_back_to_loopback() -> None:
    # resolve GZ IP falls back TO loopback 동작과 회귀 여부를 검증한다.
    assert resolve_gz_ip('') == DEFAULT_GZ_IP


def test_resolve_performance_mode_defaults_to_balanced(monkeypatch) -> None:
    # resolve performance 모드 defaults TO balanced 동작과 회귀 여부를 검증한다.
    monkeypatch.delenv(PERFORMANCE_MODE_ENV_VAR, raising=False)

    assert resolve_performance_mode() == DEFAULT_PERFORMANCE_MODE


def test_resolve_performance_defaults_for_balanced_profile() -> None:
    # resolve performance defaults FOR balanced 프로필 동작과 회귀 여부를 검증한다.
    defaults = resolve_performance_defaults('simulation', 'balanced')

    assert defaults['gz_args_prefix'] == '-r'
    assert defaults['use_rviz'] == 'true'
    assert defaults['use_runtime_support'] == 'true'
