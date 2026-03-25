from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_RUNTIME_DIR = Path(os.environ.get("AGRIBOT_RUNTIME_DIR", "/tmp/agribot_runtime"))
MANUAL_COMMAND_FILENAME = "robot_manual_command.json"
MANUAL_COMMAND_STATUS_FILENAME = "robot_manual_command_status.json"
CONTROL_STATE_FILENAME = "robot_control_state.json"
MISSION_REQUEST_FILENAME = "robot_mission_request.json"
MISSION_STATUS_FILENAME = "robot_mission_status.json"
MISSION_STATUS_DIRNAME = "mission_statuses"
HARVEST_BASKET_STATE_FILENAME = "harvest_basket_state.json"
HARVEST_LATEST_EVENT_FILENAME = "harvest_latest_event.json"
HARVEST_EVENT_DIRNAME = "harvest_events"
HARVEST_ACTION_STATUS_FILENAME = "harvest_action_status.json"
HARVEST_ACTION_STATUS_DIRNAME = "harvest_action_statuses"
HARVEST_FAILURE_ALERT_FILENAME = "harvest_failure_alert.json"
DEFAULT_COMMAND_STATUS = "idle"
DEFAULT_MISSION_STATUS = "idle"
DEFAULT_CONTROL_MODE = "normal"
DEFAULT_ACTIVE_ACTIVITY = "idle"
KNOWN_COMMAND_STATUSES = {
    "idle",
    "pending",
    "running",
    "succeeded",
    "failed",
    "canceled",
}
KNOWN_MISSION_STATUSES = {
    "idle",
    "pending",
    "running",
    "succeeded",
    "failed",
    "canceled",
}
KNOWN_CONTROL_MODES = {
    "normal",
    "paused",
    "emergency_stop",
}
KNOWN_ACTIVE_ACTIVITIES = {
    "idle",
    "manual_navigation",
    "patrol",
}
KNOWN_RESUME_CONTEXT_TYPES = {
    "manual_navigation",
    "patrol",
}


class RobotRuntimeStateError(ValueError):
    pass


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def runtime_dir_from_env() -> Path:
    runtime_dir = Path(os.environ.get("AGRIBOT_RUNTIME_DIR", str(DEFAULT_RUNTIME_DIR)))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def command_file_path() -> Path:
    return runtime_dir_from_env() / MANUAL_COMMAND_FILENAME


def command_status_file_path() -> Path:
    return runtime_dir_from_env() / MANUAL_COMMAND_STATUS_FILENAME


def control_state_file_path() -> Path:
    return runtime_dir_from_env() / CONTROL_STATE_FILENAME


def mission_request_file_path() -> Path:
    return runtime_dir_from_env() / MISSION_REQUEST_FILENAME


def mission_status_file_path() -> Path:
    return runtime_dir_from_env() / MISSION_STATUS_FILENAME


def _sanitize_runtime_identifier(value: str) -> str:
    normalized = "".join(
        character if character.isalnum() or character in {"-", "_", "."} else "_"
        for character in str(value).strip()
    )
    return normalized or "unknown-mission"


def mission_status_record_file_path(mission_id: str) -> Path:
    return (
        runtime_dir_from_env()
        / MISSION_STATUS_DIRNAME
        / f"{_sanitize_runtime_identifier(mission_id)}.json"
    )


def harvest_basket_state_file_path() -> Path:
    return runtime_dir_from_env() / HARVEST_BASKET_STATE_FILENAME


def harvest_latest_event_file_path() -> Path:
    return runtime_dir_from_env() / HARVEST_LATEST_EVENT_FILENAME


def harvest_event_record_file_path(event_id: str) -> Path:
    return (
        runtime_dir_from_env()
        / HARVEST_EVENT_DIRNAME
        / f"{_sanitize_runtime_identifier(event_id)}.json"
    )


def harvest_action_status_file_path() -> Path:
    return runtime_dir_from_env() / HARVEST_ACTION_STATUS_FILENAME


def harvest_action_status_record_file_path(mission_id: str) -> Path:
    return (
        runtime_dir_from_env()
        / HARVEST_ACTION_STATUS_DIRNAME
        / f"{_sanitize_runtime_identifier(mission_id)}.json"
    )


def harvest_failure_alert_file_path() -> Path:
    return runtime_dir_from_env() / HARVEST_FAILURE_ALERT_FILENAME


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RobotRuntimeStateError(f"{path.name} 최상위 payload는 JSON object여야 합니다.")
    return payload


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def _normalize_optional_string(value: Any) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _normalize_resume_context(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    context_type = str(value.get("context_type", "")).strip().lower()
    if context_type not in KNOWN_RESUME_CONTEXT_TYPES:
        return None

    return {
        "context_type": context_type,
        "captured_at": _normalize_optional_string(value.get("captured_at")),
        "command_id": _normalize_optional_string(value.get("command_id")),
        "command_type": _normalize_optional_string(value.get("command_type")),
        "target_pose": value.get("target_pose") if isinstance(value.get("target_pose"), dict) else None,
        "home_waypoint_id": _normalize_optional_string(value.get("home_waypoint_id")),
        "patrol_snapshot": (
            value.get("patrol_snapshot")
            if isinstance(value.get("patrol_snapshot"), dict)
            else None
        ),
    }


def _default_control_message(mode: str, *, available: bool) -> str:
    if not available:
        return "아직 executor가 기록한 control state 파일이 없습니다."
    if mode == "emergency_stop":
        return "비상 정지가 활성화되었습니다."
    if mode == "paused":
        return "일시정지가 활성화되었습니다."
    return "정상 제어 상태입니다."


def build_control_state_payload(
    payload: dict[str, Any] | None = None,
    *,
    available: bool,
    message: str | None = None,
) -> dict[str, Any]:
    raw_payload = payload or {}
    mode = str(raw_payload.get("mode", DEFAULT_CONTROL_MODE)).strip().lower()
    if mode not in KNOWN_CONTROL_MODES:
        mode = DEFAULT_CONTROL_MODE

    active_activity = str(raw_payload.get("active_activity", DEFAULT_ACTIVE_ACTIVITY)).strip().lower()
    if active_activity not in KNOWN_ACTIVE_ACTIVITIES:
        active_activity = DEFAULT_ACTIVE_ACTIVITY

    resume_context = _normalize_resume_context(raw_payload.get("resume_context"))
    updated_at = _normalize_optional_string(raw_payload.get("updated_at")) or iso_now()
    normalized_message = (
        _normalize_optional_string(message)
        or _normalize_optional_string(raw_payload.get("message"))
        or _default_control_message(mode, available=available)
    )

    if not available:
        mode = DEFAULT_CONTROL_MODE
        active_activity = DEFAULT_ACTIVE_ACTIVITY
        resume_context = None

    return {
        "source": "runtime_file",
        "available": available,
        "mode": mode,
        "is_latched": bool(raw_payload.get("is_latched", mode != DEFAULT_CONTROL_MODE))
        if available
        else False,
        "active_activity": active_activity,
        "blocking_reason": (
            _normalize_optional_string(raw_payload.get("blocking_reason"))
            if available
            else None
        ),
        "message": normalized_message,
        "resume_available": (
            bool(raw_payload.get("resume_available", resume_context is not None))
            if available
            else False
        ),
        "resume_context": resume_context,
        "updated_at": updated_at,
    }


def build_unavailable_control_state_payload(message: str | None = None) -> dict[str, Any]:
    return build_control_state_payload(available=False, message=message)


def read_control_state_payload() -> dict[str, Any]:
    path = control_state_file_path()
    if not path.exists():
        return build_unavailable_control_state_payload()

    try:
        payload = read_json_object(path)
    except (OSError, json.JSONDecodeError, RobotRuntimeStateError) as exc:
        raise RobotRuntimeStateError(
            f"{CONTROL_STATE_FILENAME} 을 읽지 못했습니다: {exc}"
        ) from exc

    return build_control_state_payload(payload, available=True)


def build_command_status_payload(
    payload: dict[str, Any] | None = None,
    *,
    available: bool,
    message: str | None = None,
) -> dict[str, Any]:
    raw_payload = payload or {}
    status = str(raw_payload.get("status", DEFAULT_COMMAND_STATUS)).strip().lower()
    if status not in KNOWN_COMMAND_STATUSES:
        status = DEFAULT_COMMAND_STATUS

    normalized_message = (
        _normalize_optional_string(message)
        or _normalize_optional_string(raw_payload.get("message"))
        or (
            "아직 executor가 기록한 command status 파일이 없습니다."
            if not available
            else "명령 상태 정보가 준비되지 않았습니다."
        )
    )

    return {
        "source": "runtime_file",
        "available": available,
        "command_id": _normalize_optional_string(raw_payload.get("command_id")),
        "requested_command_type": _normalize_optional_string(raw_payload.get("requested_command_type")),
        "command_type": _normalize_optional_string(raw_payload.get("command_type")),
        "robot_id": _normalize_optional_string(raw_payload.get("robot_id")),
        "requested_by": _normalize_optional_string(raw_payload.get("requested_by")),
        "map_id": _normalize_optional_string(raw_payload.get("map_id")),
        "frame_id": _normalize_optional_string(raw_payload.get("frame_id")),
        "status": status,
        "message": normalized_message,
        "error": _normalize_optional_string(raw_payload.get("error")),
        "result": _normalize_optional_string(raw_payload.get("result")),
        "target_pose": raw_payload.get("target_pose") if isinstance(raw_payload.get("target_pose"), dict) else None,
        "target_zone_id": _normalize_optional_string(raw_payload.get("target_zone_id")),
        "home_waypoint_id": _normalize_optional_string(raw_payload.get("home_waypoint_id")),
        "preempt_current_navigation": bool(raw_payload.get("preempt_current_navigation", False)),
        "received_at": _normalize_optional_string(raw_payload.get("received_at")),
        "started_at": _normalize_optional_string(raw_payload.get("started_at")),
        "completed_at": _normalize_optional_string(raw_payload.get("completed_at")),
        "updated_at": _normalize_optional_string(raw_payload.get("updated_at")) or iso_now(),
    }


def build_idle_command_status_payload(
    message: str | None = None,
    *,
    control_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    default_message = message
    if default_message is None and control_state is not None and control_state.get("is_latched"):
        default_message = str(control_state.get("message") or "").strip() or None
    return build_command_status_payload(
        {"status": DEFAULT_COMMAND_STATUS},
        available=False,
        message=default_message,
    )


def build_mission_status_payload(
    payload: dict[str, Any] | None = None,
    *,
    available: bool,
    message: str | None = None,
) -> dict[str, Any]:
    raw_payload = payload or {}
    status = str(raw_payload.get("status", DEFAULT_MISSION_STATUS)).strip().lower()
    if status not in KNOWN_MISSION_STATUSES:
        status = DEFAULT_MISSION_STATUS

    normalized_message = (
        _normalize_optional_string(message)
        or _normalize_optional_string(raw_payload.get("message"))
        or (
            "아직 mission bridge가 기록한 status 파일이 없습니다."
            if not available
            else "미션 상태 정보가 준비되지 않았습니다."
        )
    )

    zone_ids = raw_payload.get("zone_ids")
    normalized_zone_ids = (
        [str(zone_id).strip() for zone_id in zone_ids if str(zone_id).strip()]
        if isinstance(zone_ids, list)
        else None
    )

    return {
        "source": "runtime_file",
        "available": available,
        "mission_id": _normalize_optional_string(raw_payload.get("mission_id")),
        "command_id": _normalize_optional_string(raw_payload.get("command_id")),
        "mission_type": _normalize_optional_string(raw_payload.get("mission_type")),
        "state": _normalize_optional_string(raw_payload.get("state")),
        "current_phase": _normalize_optional_string(raw_payload.get("current_phase")),
        "progress_pct": raw_payload.get("progress_pct")
        if isinstance(raw_payload.get("progress_pct"), (int, float))
        else None,
        "retry_count": raw_payload.get("retry_count")
        if isinstance(raw_payload.get("retry_count"), int)
        else None,
        "detail_message": _normalize_optional_string(raw_payload.get("detail_message")),
        "zone_id": _normalize_optional_string(raw_payload.get("zone_id")),
        "target_id": _normalize_optional_string(raw_payload.get("target_id")),
        "request_type": _normalize_optional_string(raw_payload.get("request_type")),
        "requested_type": _normalize_optional_string(raw_payload.get("request_type")),
        "robot_id": _normalize_optional_string(raw_payload.get("robot_id")),
        "requested_by": _normalize_optional_string(raw_payload.get("requested_by")),
        "status": status,
        "message": normalized_message,
        "operator_message": normalized_message,
        "error": _normalize_optional_string(raw_payload.get("error")),
        "result": _normalize_optional_string(raw_payload.get("result")),
        "zone_ids": normalized_zone_ids,
        "loop_count": raw_payload.get("loop_count")
        if isinstance(raw_payload.get("loop_count"), int)
        else None,
        "patrol_mode": _normalize_optional_string(raw_payload.get("patrol_mode")),
        "plant_id": _normalize_optional_string(raw_payload.get("plant_id")),
        "fruit_id": _normalize_optional_string(raw_payload.get("fruit_id")),
        "tomato_id": _normalize_optional_string(raw_payload.get("tomato_id")),
        "received_at": _normalize_optional_string(raw_payload.get("received_at")),
        "started_at": _normalize_optional_string(raw_payload.get("started_at")),
        "completed_at": _normalize_optional_string(raw_payload.get("completed_at")),
        "updated_at": _normalize_optional_string(raw_payload.get("updated_at")) or iso_now(),
    }


def build_idle_mission_status_payload(message: str | None = None) -> dict[str, Any]:
    return build_mission_status_payload(
        {"status": DEFAULT_MISSION_STATUS},
        available=False,
        message=message,
    )


def _merge_command_request_payload(
    status_payload: dict[str, Any],
    command_payload: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(status_payload)
    if command_payload.get("command_id") != status_payload.get("command_id"):
        return merged

    for field_name in (
        "requested_command_type",
        "target_zone_id",
        "preempt_current_navigation",
        "map_id",
        "robot_id",
        "requested_by",
    ):
        if field_name in command_payload and command_payload.get(field_name) is not None:
            merged[field_name] = command_payload.get(field_name)

    if merged.get("command_type") is None and command_payload.get("command_type"):
        merged["command_type"] = command_payload.get("command_type")
    if merged.get("target_pose") is None:
        payload = command_payload.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("target_pose"), dict):
            merged["target_pose"] = payload.get("target_pose")
    if merged.get("home_waypoint_id") is None:
        payload = command_payload.get("payload")
        if isinstance(payload, dict):
            merged["home_waypoint_id"] = _normalize_optional_string(payload.get("home_waypoint_id"))

    return merged


def _attach_control_state(
    status_payload: dict[str, Any],
    control_state: dict[str, Any],
) -> dict[str, Any]:
    result = dict(status_payload)
    result["control_state"] = control_state
    result["control_mode"] = control_state["mode"]
    result["control_is_latched"] = control_state["is_latched"]
    result["control_active_activity"] = control_state["active_activity"]
    result["control_blocking_reason"] = control_state["blocking_reason"]
    result["control_message"] = control_state["message"]
    result["control_resume_available"] = control_state["resume_available"]
    result["control_updated_at"] = control_state["updated_at"]
    return result


def read_latest_command_status_payload() -> dict[str, Any]:
    control_state = read_control_state_payload()
    status_path = command_status_file_path()
    if not status_path.exists():
        return _attach_control_state(
            build_idle_command_status_payload(control_state=control_state),
            control_state,
        )

    try:
        payload = read_json_object(status_path)
    except (OSError, json.JSONDecodeError, RobotRuntimeStateError) as exc:
        raise RobotRuntimeStateError(
            f"{MANUAL_COMMAND_STATUS_FILENAME} 을 읽지 못했습니다: {exc}"
        ) from exc

    result = build_command_status_payload(payload, available=True)
    command_path = command_file_path()
    if command_path.exists():
        try:
            command_payload = read_json_object(command_path)
        except (OSError, json.JSONDecodeError, RobotRuntimeStateError):
            command_payload = {}
        result = _merge_command_request_payload(result, command_payload)

    return _attach_control_state(result, control_state)


def read_latest_mission_status_payload() -> dict[str, Any]:
    status_path = mission_status_file_path()
    if not status_path.exists():
        return build_idle_mission_status_payload()

    try:
        payload = read_json_object(status_path)
    except (OSError, json.JSONDecodeError, RobotRuntimeStateError) as exc:
        raise RobotRuntimeStateError(
            f"{MISSION_STATUS_FILENAME} 을 읽지 못했습니다: {exc}"
        ) from exc

    return build_mission_status_payload(payload, available=True)


def read_mission_status_payload(mission_id: str) -> dict[str, Any]:
    path = mission_status_record_file_path(mission_id)
    if path.exists():
        try:
            payload = read_json_object(path)
        except (OSError, json.JSONDecodeError, RobotRuntimeStateError) as exc:
            raise RobotRuntimeStateError(
                f"{path.name} 을 읽지 못했습니다: {exc}"
            ) from exc
        return build_mission_status_payload(payload, available=True)

    latest_payload = read_latest_mission_status_payload()
    if latest_payload.get("mission_id") == str(mission_id).strip():
        return latest_payload

    raise FileNotFoundError(f"mission status 파일을 찾지 못했습니다: {mission_id}")
