"""spawn launch가 수확 팔 브리지와 그래픽 프로필 환경을 함께 내보내는지 검증한다."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import yaml

from launch.actions import SetEnvironmentVariable
from launch.actions import IncludeLaunchDescription
from launch_ros.actions import Node

from agribot_bringup.launch_profile import GRAPHICS_PROFILE_ENV_VAR


REPO_ROOT = Path(__file__).resolve().parents[4]
LAUNCH_FILE = (
    REPO_ROOT
    / 'agribot_ws'
    / 'src'
    / 'agribot_description'
    / 'launch'
    / 'spawn_agribot.launch.py'
)


def _load_launch_module():
    spec = spec_from_file_location('agribot_description_spawn_launch', LAUNCH_FILE)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _patch_package_share_lookup(monkeypatch, module) -> None:
    share_dirs = {
        'agribot_description': REPO_ROOT / 'agribot_ws' / 'src' / 'agribot_description',
        'ros_gz_sim': REPO_ROOT / 'agribot_ws' / 'src' / 'agribot_description',
    }
    monkeypatch.setattr(
        module,
        'get_package_share_directory',
        lambda package_name: str(share_dirs[package_name]),
    )


def _declared_node_name(node: Node) -> str:
    return str(getattr(node, '_Node__node_name', ''))


def _launch_env_map(launch_description) -> dict[str, str]:
    result: dict[str, str] = {}
    for entity in launch_description.entities:
        if not isinstance(entity, SetEnvironmentVariable):
            continue
        name = getattr(entity, '_SetEnvironmentVariable__name', [])
        value = getattr(entity, '_SetEnvironmentVariable__value', [])
        if not name or not value:
            continue
        result[getattr(name[0], 'text', '')] = getattr(value[0], 'text', '')
    return result


def _text_substitution_value(value) -> str:
    if isinstance(value, tuple) and value:
        return getattr(value[0], 'text', '').splitlines()[0]
    return str(value)


def test_spawn_launch_bridges_harvest_arm_command_topic(monkeypatch) -> None:
    module = _load_launch_module()
    _patch_package_share_lookup(monkeypatch, module)
    launch_description = module.generate_launch_description()

    nodes = [entity for entity in launch_description.entities if isinstance(entity, Node)]
    includes = [
        entity for entity in launch_description.entities
        if isinstance(entity, IncludeLaunchDescription)
    ]

    assert includes

    state_bridge = next(node for node in nodes if _declared_node_name(node) == 'ros_gz_state_bridge')
    parameters = getattr(state_bridge, '_Node__parameters', ())
    parameter_map = {
        getattr(next(iter(item.keys()))[0], 'text', ''): _text_substitution_value(
            next(iter(item.values()))
        )
        for item in parameters
        if item
    }
    config_file = Path(parameter_map['config_file'])
    bridges = yaml.safe_load(config_file.read_text(encoding='utf-8'))

    assert any(
        item['ros_topic_name'] == '/agribot/harvest_arm_joint/cmd_pos'
        and item['gz_topic_name'] == '/agribot/harvest_arm_joint/cmd_pos'
        and item['direction'] == 'ROS_TO_GZ'
        for item in bridges
    )


def test_spawn_launch_uses_raw_clock_and_disables_clock_guard(monkeypatch) -> None:
    module = _load_launch_module()
    _patch_package_share_lookup(monkeypatch, module)
    launch_description = module.generate_launch_description()

    nodes = [entity for entity in launch_description.entities if isinstance(entity, Node)]
    state_bridge = next(node for node in nodes if _declared_node_name(node) == 'ros_gz_state_bridge')
    sim_time_guard = next(node for node in nodes if _declared_node_name(node) == 'sim_time_guard')

    remappings = [
        (str(left[0]), str(right[0]))
        for left, right in getattr(state_bridge, '_Node__remappings', [])
    ]
    assert ('/clock', '/clock_raw') not in remappings

    parameters = getattr(sim_time_guard, '_Node__parameters', ())
    parameter_map = {
        getattr(next(iter(item.keys()))[0], 'text', ''): next(iter(item.values()))
        for item in parameters
        if item
    }
    assert parameter_map['guard_clock'] is False


def test_spawn_launch_defaults_to_system_graphics_profile_without_nvidia(monkeypatch) -> None:
    monkeypatch.delenv(GRAPHICS_PROFILE_ENV_VAR, raising=False)
    monkeypatch.setattr('agribot_bringup.launch_profile.os.path.exists', lambda _path: False)

    module = _load_launch_module()
    _patch_package_share_lookup(monkeypatch, module)
    launch_description = module.generate_launch_description()
    env_map = _launch_env_map(launch_description)

    assert env_map[GRAPHICS_PROFILE_ENV_VAR] == 'system'
    assert 'DRI_PRIME' not in env_map
    assert 'GZ_SIM_RENDER_ENGINE' not in env_map


def test_spawn_launch_can_force_nvidia_profile(monkeypatch) -> None:
    monkeypatch.setenv(GRAPHICS_PROFILE_ENV_VAR, 'nvidia')

    module = _load_launch_module()
    _patch_package_share_lookup(monkeypatch, module)
    launch_description = module.generate_launch_description()
    env_map = _launch_env_map(launch_description)

    assert env_map[GRAPHICS_PROFILE_ENV_VAR] == 'nvidia'
    assert env_map['DRI_PRIME'] == '1'
    assert env_map['GBM_BACKEND'] == 'nvidia-drm'
    assert env_map['GZ_SIM_RENDER_ENGINE'] == 'ogre2'
