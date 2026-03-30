from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path

from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.actions import RegisterEventHandler, SetEnvironmentVariable
from launch.event_handlers import OnShutdown
from launch_ros.actions import Node

from agribot_bringup.launch_profile import GRAPHICS_PROFILE_ENV_VAR
from agribot_bringup.launch_profile import DEFAULT_GZ_IP, DEFAULT_ROS_DISCOVERY_RANGE
from agribot_bringup.launch_profile import DEFAULT_PERFORMANCE_MODE, PERFORMANCE_MODE_ENV_VAR
from agribot_bringup.shutdown_cleanup import LAUNCH_SESSION_ENV_VAR


REPO_ROOT = Path(__file__).resolve().parents[4]
LAUNCH_FILE = (
    REPO_ROOT
    / 'agribot_ws'
    / 'src'
    / 'agribot_bringup'
    / 'launch'
    / 'simulation.launch.py'
)


def _load_launch_module():
    spec = spec_from_file_location('agribot_bringup_simulation_launch', LAUNCH_FILE)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _patch_package_lookup(monkeypatch, module) -> None:
    share_dirs = {
        'agribot_description': REPO_ROOT / 'agribot_ws' / 'src' / 'agribot_description',
        'agribot_navigation': REPO_ROOT / 'agribot_ws' / 'src' / 'agribot_navigation',
        'agribot_iot': REPO_ROOT / 'agribot_ws' / 'src' / 'agribot_iot',
        'agribot_perception': REPO_ROOT / 'agribot_ws' / 'src' / 'agribot_perception',
    }
    monkeypatch.setattr(
        module,
        'get_package_prefix',
        lambda package_name: str(REPO_ROOT / 'install' / package_name),
    )
    monkeypatch.setattr(
        module,
        'get_package_share_directory',
        lambda package_name: str(share_dirs[package_name]),
    )


def _declared_node_name(node: Node) -> str:
    return str(getattr(node, '_Node__node_name', ''))


def _declared_node_executable(node: Node) -> str:
    return str(getattr(node, '_Node__node_executable', ''))


def _has_shutdown_handler(launch_description) -> bool:
    for entity in launch_description.entities:
        if not isinstance(entity, RegisterEventHandler):
            continue
        handler = getattr(entity, '_RegisterEventHandler__event_handler', None)
        if isinstance(handler, OnShutdown):
            return True
    return False


def _has_launch_session_env(launch_description) -> bool:
    for entity in launch_description.entities:
        if not isinstance(entity, SetEnvironmentVariable):
            continue
        name = getattr(entity, '_SetEnvironmentVariable__name', [])
        if name and getattr(name[0], 'text', '') == LAUNCH_SESSION_ENV_VAR:
            return True
    return False


def _launch_env_value(launch_description, target_name: str) -> str | None:
    for entity in launch_description.entities:
        if not isinstance(entity, SetEnvironmentVariable):
            continue
        name = getattr(entity, '_SetEnvironmentVariable__name', [])
        value = getattr(entity, '_SetEnvironmentVariable__value', [])
        if not name or not value:
            continue
        if getattr(name[0], 'text', '') == target_name:
            return getattr(value[0], 'text', '')
    return None


def test_simulation_launch_declares_iot_arguments_and_includes_iot_pipeline(monkeypatch) -> None:
    monkeypatch.delenv(GRAPHICS_PROFILE_ENV_VAR, raising=False)
    monkeypatch.delenv(PERFORMANCE_MODE_ENV_VAR, raising=False)
    monkeypatch.delenv(LAUNCH_SESSION_ENV_VAR, raising=False)
    monkeypatch.setattr('agribot_bringup.launch_profile.os.path.exists', lambda _path: False)
    module = _load_launch_module()
    _patch_package_lookup(monkeypatch, module)

    launch_description = module.generate_launch_description()
    declare_args = [
        entity for entity in launch_description.entities if isinstance(entity, DeclareLaunchArgument)
    ]
    includes = [
        entity for entity in launch_description.entities if isinstance(entity, IncludeLaunchDescription)
    ]
    nodes = [
        entity for entity in launch_description.entities if isinstance(entity, Node)
    ]

    arg_names = {entity.name for entity in declare_args}

    assert {
        'use_iot',
        'use_rviz',
        'use_camera_bridges',
        'runtime_dir',
        'use_perception',
        'use_runtime_support',
        'backend_confirm_url',
        'pose_write_period_sec',
        'semantic_write_period_sec',
        'robot_command_poll_period_sec',
        'mission_command_poll_period_sec',
    }.issubset(arg_names)
    assert len(includes) >= 3
    assert len(nodes) == 3
    node_names = {_declared_node_name(node) for node in nodes}
    executable_names = {_declared_node_executable(node) for node in nodes}
    assert 'mission_bridge_executor' in node_names
    assert 'mission_bridge_executor' in executable_names
    assert _has_shutdown_handler(launch_description) is True
    assert _has_launch_session_env(launch_description) is True
    assert os.environ[LAUNCH_SESSION_ENV_VAR].startswith('agribot-launch-')
    assert _launch_env_value(launch_description, GRAPHICS_PROFILE_ENV_VAR) == 'system'
    assert _launch_env_value(launch_description, PERFORMANCE_MODE_ENV_VAR) == DEFAULT_PERFORMANCE_MODE
    assert (
        _launch_env_value(launch_description, 'ROS_AUTOMATIC_DISCOVERY_RANGE')
        == DEFAULT_ROS_DISCOVERY_RANGE
    )
    assert _launch_env_value(launch_description, 'GZ_IP') == DEFAULT_GZ_IP
