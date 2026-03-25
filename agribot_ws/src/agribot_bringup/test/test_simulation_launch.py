from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch_ros.actions import Node


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


def test_simulation_launch_declares_iot_arguments_and_includes_iot_pipeline() -> None:
    module = _load_launch_module()

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

    assert len(declare_args) == 2
    assert len(includes) == 2
    assert len(nodes) == 2
