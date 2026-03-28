"""spawn launch가 수확 팔 브리지, GUI 설정, 그래픽 프로필을 함께 내보내는지 검증한다."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

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


def _iter_text_parts(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [getattr(item, 'text', str(item)) for item in value]
    return [str(value)]


def _parameter_map(node: Node) -> dict[str, object]:
    raw_parameters = getattr(node, '_Node__parameters', ())
    parameter_map: dict[str, object] = {}
    for item in raw_parameters:
        if not item:
            continue
        key_substitutions = next(iter(item.keys()))
        key = getattr(key_substitutions[0], 'text', '')
        parameter_map[key] = next(iter(item.values()))
    return parameter_map


def _launch_configuration_name(value) -> str | None:
    substitutions = getattr(value, 'variable_name', None)
    if not substitutions:
        return None
    first = substitutions[0]
    return getattr(first, 'text', None)


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
    arguments = [str(argument) for argument in getattr(state_bridge, '_Node__arguments', ())]

    assert '/agribot/harvest_arm_joint/cmd_pos@std_msgs/msg/Float64]gz.msgs.Double' in arguments


def test_spawn_launch_uses_raw_clock_and_disables_clock_guard(monkeypatch) -> None:
    module = _load_launch_module()
    _patch_package_share_lookup(monkeypatch, module)
    launch_description = module.generate_launch_description()

    nodes = [entity for entity in launch_description.entities if isinstance(entity, Node)]
    state_bridge = next(node for node in nodes if _declared_node_name(node) == 'ros_gz_state_bridge')
    sim_time_guard = next(node for node in nodes if _declared_node_name(node) == 'sim_time_guard')

    remappings = [
        (
            getattr(left[0], 'text', str(left[0])),
            getattr(right[0], 'text', str(right[0])),
        )
        for left, right in getattr(state_bridge, '_Node__remappings', [])
    ]
    assert ('/clock', '/clock_raw') in remappings

    parameter_map = _parameter_map(sim_time_guard)
    assert parameter_map['use_sim_time'] is False


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


def test_spawn_launch_passes_repo_gui_config_to_gz_sim(monkeypatch) -> None:
    module = _load_launch_module()
    _patch_package_share_lookup(monkeypatch, module)
    launch_description = module.generate_launch_description()

    declare_args = [
        entity for entity in launch_description.entities
        if getattr(entity, 'name', None) == 'gui_config'
    ]
    includes = [
        entity for entity in launch_description.entities
        if isinstance(entity, IncludeLaunchDescription)
    ]
    gz_sim_include = includes[0]
    launch_arguments = dict(getattr(gz_sim_include, '_IncludeLaunchDescription__launch_arguments'))
    gz_args_parts = _iter_text_parts(launch_arguments['gz_args'])

    gui_config_path = (
        REPO_ROOT
        / 'agribot_ws'
        / 'src'
        / 'agribot_description'
        / 'config'
        / 'frontend_aligned_gui.config'
    )

    assert declare_args
    assert gui_config_path.exists()
    assert '--gui-config' in ''.join(gz_args_parts)
    assert any(_launch_configuration_name(part) == 'gui_config' for part in launch_arguments['gz_args'])
