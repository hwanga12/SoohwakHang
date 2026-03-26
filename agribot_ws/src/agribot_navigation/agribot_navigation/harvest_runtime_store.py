from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path(os.environ.get('AGRIBOT_RUNTIME_DIR', '/tmp/agribot_runtime'))
HARVEST_BASKET_STATE_FILENAME = 'harvest_basket_state.json'
HARVEST_LATEST_EVENT_FILENAME = 'harvest_latest_event.json'
HARVEST_EVENT_DIRNAME = 'harvest_events'
HARVEST_ACTION_STATUS_FILENAME = 'harvest_action_status.json'
HARVEST_ACTION_STATUS_DIRNAME = 'harvest_action_statuses'
HARVEST_FAILURE_ALERT_FILENAME = 'harvest_failure_alert.json'


def runtime_dir_from_env() -> Path:
    runtime_dir = Path(os.environ.get('AGRIBOT_RUNTIME_DIR', str(DEFAULT_RUNTIME_DIR)))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def _sanitize_runtime_identifier(value: str) -> str:
    normalized = ''.join(
        character if character.isalnum() or character in {'-', '_', '.'} else '_'
        for character in str(value).strip()
    )
    return normalized or 'unknown'


def harvest_basket_state_path(runtime_dir: Path | None = None) -> Path:
    return (runtime_dir or runtime_dir_from_env()) / HARVEST_BASKET_STATE_FILENAME


def harvest_latest_event_path(runtime_dir: Path | None = None) -> Path:
    return (runtime_dir or runtime_dir_from_env()) / HARVEST_LATEST_EVENT_FILENAME


def harvest_event_record_path(event_id: str, runtime_dir: Path | None = None) -> Path:
    return (
        (runtime_dir or runtime_dir_from_env())
        / HARVEST_EVENT_DIRNAME
        / f'{_sanitize_runtime_identifier(event_id)}.json'
    )


def harvest_action_status_path(runtime_dir: Path | None = None) -> Path:
    return (runtime_dir or runtime_dir_from_env()) / HARVEST_ACTION_STATUS_FILENAME


def harvest_action_status_record_path(
    mission_id: str,
    runtime_dir: Path | None = None,
) -> Path:
    return (
        (runtime_dir or runtime_dir_from_env())
        / HARVEST_ACTION_STATUS_DIRNAME
        / f'{_sanitize_runtime_identifier(mission_id)}.json'
    )


def harvest_failure_alert_path(runtime_dir: Path | None = None) -> Path:
    return (runtime_dir or runtime_dir_from_env()) / HARVEST_FAILURE_ALERT_FILENAME


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + '.tmp')
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temp_path.replace(path)
