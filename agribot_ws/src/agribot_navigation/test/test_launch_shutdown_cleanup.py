"""navigation 계열 launch가 세션 태그와 종료 cleanup handler를 반드시 등록하는지 검증한다."""

from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path

from launch.actions import RegisterEventHandler, SetEnvironmentVariable
from launch.event_handlers import OnShutdown

from agribot_bringup.shutdown_cleanup import LAUNCH_SESSION_ENV_VAR


REPO_ROOT = Path(__file__).resolve().parents[4]
LAUNCH_FILES = [
    REPO_ROOT / 'agribot_ws' / 'src' / 'agribot_navigation' / 'launch' / 'navigation.launch.py',
    REPO_ROOT / 'agribot_ws' / 'src' / 'agribot_navigation' / 'launch' / 'mapping.launch.py',
    REPO_ROOT / 'agribot_ws' / 'src' / 'agribot_navigation' / 'launch' / 'autonomous_mapping.launch.py',
]


def _load_launch_description(launch_file: Path):
    spec = spec_from_file_location(launch_file.stem.replace('.', '_'), launch_file)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.generate_launch_description()


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


def test_navigation_entry_launches_register_shutdown_cleanup(monkeypatch) -> None:
    for launch_file in LAUNCH_FILES:
        monkeypatch.delenv(LAUNCH_SESSION_ENV_VAR, raising=False)
        launch_description = _load_launch_description(launch_file)
        assert _has_shutdown_handler(launch_description) is True, launch_file.name
        assert _has_launch_session_env(launch_description) is True, launch_file.name
        assert os.environ[LAUNCH_SESSION_ENV_VAR].startswith('agribot-launch-'), launch_file.name
