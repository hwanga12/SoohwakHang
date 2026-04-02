from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.substitutions import TextSubstitution


REPO_ROOT = Path(__file__).resolve().parents[4]
LAUNCH_FILE = (
    REPO_ROOT
    / 'agribot_ws'
    / 'src'
    / 'agribot_iot'
    / 'launch'
    / 'iot_status_pipeline.launch.py'
)


def _load_launch_module():
    spec = spec_from_file_location('agribot_iot_status_pipeline_launch', LAUNCH_FILE)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _env_name(entity: SetEnvironmentVariable) -> str:
    substitutions = getattr(entity, '_SetEnvironmentVariable__name', [])
    parts: list[str] = []
    for substitution in substitutions:
        if isinstance(substitution, TextSubstitution):
            parts.append(substitution.text)
    return ''.join(parts)


def test_iot_status_pipeline_launch_includes_all_iot_publishers() -> None:
    module = _load_launch_module()

    launch_description = module.generate_launch_description()
    declare_args = [
        entity for entity in launch_description.entities if isinstance(entity, DeclareLaunchArgument)
    ]
    includes = [
        entity for entity in launch_description.entities if isinstance(entity, IncludeLaunchDescription)
    ]
    env_sets = [
        entity for entity in launch_description.entities if isinstance(entity, SetEnvironmentVariable)
    ]

    assert len(declare_args) == 2
    assert len(includes) == 6
    assert len(env_sets) >= 3
    assert any(_env_name(entity) == 'ROS_DOMAIN_ID' for entity in env_sets)
    assert any(_env_name(entity) == 'ROS_AUTOMATIC_DISCOVERY_RANGE' for entity in env_sets)
