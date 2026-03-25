from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from robot_map_service import read_map_payload
from zone_service import resolve_zone_payload, resolve_zone_representative_pose

DEFAULT_FRAME_ID = "map"
DEFAULT_RUNTIME_DIR = Path(os.environ.get("AGRIBOT_RUNTIME_DIR", "/tmp/agribot_runtime"))
MANUAL_COMMAND_PATH = DEFAULT_RUNTIME_DIR / "robot_manual_command.json"
MANUAL_COMMAND_STATUS_PATH = DEFAULT_RUNTIME_DIR / "robot_manual_command_status.json"
ALLOWED_COMMAND_TYPES = {
    "navigate_to_pose",
    "pause_patrol",
    "resume_patrol",
    "return_home",
    "move_to_zone",
}
FILE_BRIDGE_COMMAND_TYPES = {
    "navigate_to_pose",
    "pause_patrol",
    "resume_patrol",
    "return_home",
}
TERMINAL_STATUSES = {"succeeded", "failed", "canceled"}
DEFAULT_PREEMPT_COMMAND_TYPES = {
    "navigate_to_pose",
    "move_to_zone",
    "return_home",
}


class RobotCommandValidationError(ValueError):
    pass


class DuplicateCommandIdError(RobotCommandValidationError):
    pass


def _runtime_dir() -> Path:
    runtime_dir = Path(os.environ.get("AGRIBOT_RUNTIME_DIR", str(DEFAULT_RUNTIME_DIR)))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def command_file_path() -> Path:
    return _runtime_dir() / MANUAL_COMMAND_PATH.name


def command_status_file_path() -> Path:
    return _runtime_dir() / MANUAL_COMMAND_STATUS_PATH.name


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RobotCommandValidationError(f"{path.name} 최상위 payload는 JSON object여야 합니다.")
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _generate_command_id() -> str:
    timestamp = int(time.time() * 1000)
    return f"robot-cmd-{timestamp}-{uuid.uuid4().hex[:8]}"


def _sanitize_command_id(command_id: str | None) -> str:
    if command_id is None or not str(command_id).strip():
        return _generate_command_id()
    return str(command_id).strip()


def _check_duplicate_command_id(command_id: str) -> None:
    for path in (command_file_path(), command_status_file_path()):
        if not path.exists():
            continue
        try:
            payload = _read_json_object(path)
        except (OSError, json.JSONDecodeError, RobotCommandValidationError):
            continue
        if str(payload.get("command_id", "")).strip() == command_id:
            raise DuplicateCommandIdError(
                f"이미 사용한 command_id 입니다: {command_id}. 새 command_id로 다시 요청하세요."
            )


def _validate_command_type(command_type: str) -> str:
    normalized = str(command_type).strip()
    if normalized not in ALLOWED_COMMAND_TYPES:
        raise RobotCommandValidationError(
            f"지원하지 않는 command_type 입니다: {normalized!r}. "
            f"허용값: {sorted(ALLOWED_COMMAND_TYPES)}"
        )
    return normalized


def _coerce_target_pose(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RobotCommandValidationError("payload는 JSON object여야 합니다.")

    target_pose = payload.get("target_pose")
    if not isinstance(target_pose, dict):
        raise RobotCommandValidationError(
            "navigate_to_pose 명령에는 payload.target_pose가 필요합니다."
        )

    missing = [field for field in ("x", "y", "yaw", "frame_id") if field not in target_pose]
    if missing:
        raise RobotCommandValidationError(
            f"payload.target_pose에 필요한 필드가 없습니다: {missing}"
        )

    frame_id = str(target_pose.get("frame_id", "")).strip()
    if frame_id != DEFAULT_FRAME_ID:
        raise RobotCommandValidationError("target_pose.frame_id 는 map 만 허용합니다.")

    return {
        "x": float(target_pose["x"]),
        "y": float(target_pose["y"]),
        "z": float(target_pose.get("z", 0.0)),
        "yaw": float(target_pose["yaw"]),
        "frame_id": frame_id,
    }


def _coerce_target_pose_object(target_pose: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(target_pose, dict):
        raise RobotCommandValidationError("target_pose 는 JSON object여야 합니다.")
    return _coerce_target_pose({"target_pose": target_pose})


def _validate_target_pose_bounds(target_pose: dict[str, Any], map_id: str | None = None) -> dict[str, Any]:
    bounds = read_map_payload(map_id)["bounds"]
    x_value = float(target_pose["x"])
    y_value = float(target_pose["y"])

    if not (float(bounds["min_x"]) <= x_value <= float(bounds["max_x"])):
        raise RobotCommandValidationError(
            f"target_pose.x={x_value} 가 맵 bounds를 벗어났습니다."
        )
    if not (float(bounds["min_y"]) <= y_value <= float(bounds["max_y"])):
        raise RobotCommandValidationError(
            f"target_pose.y={y_value} 가 맵 bounds를 벗어났습니다."
        )

    return target_pose


def _normalize_requested_by(requested_by: str) -> str:
    normalized = str(requested_by).strip()
    if not normalized:
        raise RobotCommandValidationError("requested_by 는 비어 있을 수 없습니다.")
    return normalized


def _normalize_robot_id(robot_id: str) -> str:
    normalized = str(robot_id).strip()
    if not normalized:
        raise RobotCommandValidationError("robot_id 는 비어 있을 수 없습니다.")
    return normalized


def _payload_or_empty(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise RobotCommandValidationError("payload는 JSON object여야 합니다.")
    return payload


def _coerce_optional_bool(value: Any, *, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value in {0, 1}:
            return bool(value)
        raise RobotCommandValidationError(f"{field_name} 는 bool 이어야 합니다.")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    raise RobotCommandValidationError(f"{field_name} 는 bool 이어야 합니다.")


def _resolve_preempt_current_navigation(
    *,
    command_type: str,
    payload: dict[str, Any],
    explicit_value: bool | None,
) -> bool:
    if explicit_value is not None:
        return explicit_value

    payload_value = _coerce_optional_bool(
        payload.get("preempt_current_navigation"),
        field_name="payload.preempt_current_navigation",
    )
    if payload_value is not None:
        return payload_value

    return command_type in DEFAULT_PREEMPT_COMMAND_TYPES


def _build_bridge_payload(
    *,
    command_id: str,
    command_type: str,
    robot_id: str,
    requested_by: str,
    map_id: str,
    payload: dict[str, Any],
    preempt_current_navigation: bool,
    target_zone_id: str | None = None,
    requested_command_type: str | None = None,
) -> dict[str, Any]:
    bridge_payload: dict[str, Any] = {
        "command_id": command_id,
        "command_type": command_type,
        "robot_id": robot_id,
        "requested_by": requested_by,
        "map_id": map_id,
        "issued_at": _iso_now(),
        "preempt_current_navigation": preempt_current_navigation,
    }
    if payload:
        bridge_payload["payload"] = payload
    if target_zone_id:
        bridge_payload["target_zone_id"] = target_zone_id
    if requested_command_type and requested_command_type != command_type:
        bridge_payload["requested_command_type"] = requested_command_type
    return bridge_payload


def publish_robot_command(
    *,
    robot_id: str,
    command_type: str,
    requested_by: str,
    target_zone_id: str | None = None,
    payload: dict[str, Any] | None = None,
    target_pose: dict[str, Any] | None = None,
    command_id: str | None = None,
    map_id: str | None = None,
    preempt_current_navigation: bool | None = None,
) -> dict[str, Any]:
    resolved_map_id = read_map_payload(map_id)["map_id"]
    normalized_robot_id = _normalize_robot_id(robot_id)
    normalized_requested_by = _normalize_requested_by(requested_by)
    normalized_command_type = _validate_command_type(command_type)
    normalized_payload = _payload_or_empty(payload)
    resolved_command_id = _sanitize_command_id(command_id)
    resolved_preempt_current_navigation = _resolve_preempt_current_navigation(
        command_type=normalized_command_type,
        payload=normalized_payload,
        explicit_value=_coerce_optional_bool(
            preempt_current_navigation,
            field_name="preempt_current_navigation",
        ),
    )
    _check_duplicate_command_id(resolved_command_id)

    resolved_zone: dict[str, Any] | None = None
    command_payload: dict[str, Any] = {}
    file_command_type = normalized_command_type

    if normalized_command_type == "navigate_to_pose":
        explicit_target_pose = target_pose if target_pose is not None else normalized_payload.get("target_pose")
        command_payload["target_pose"] = _validate_target_pose_bounds(
            _coerce_target_pose_object(explicit_target_pose),
            resolved_map_id,
        )
    elif normalized_command_type == "move_to_zone":
        zone_id = str(target_zone_id or "").strip()
        if not zone_id:
            raise RobotCommandValidationError(
                "move_to_zone 명령에는 target_zone_id 가 필요합니다."
            )
        resolved_zone = resolve_zone_payload(zone_id, resolved_map_id)
        command_payload["target_pose"] = _validate_target_pose_bounds(
            resolve_zone_representative_pose(zone_id, resolved_map_id),
            resolved_map_id,
        )
        file_command_type = "navigate_to_pose"
    elif normalized_command_type == "return_home":
        home_waypoint_id = str(normalized_payload.get("home_waypoint_id", "")).strip()
        if home_waypoint_id:
            command_payload["home_waypoint_id"] = home_waypoint_id

    if file_command_type not in FILE_BRIDGE_COMMAND_TYPES:
        raise RobotCommandValidationError(
            f"파일 브리지로 내보낼 수 없는 command_type 입니다: {file_command_type!r}"
        )

    bridge_payload = _build_bridge_payload(
        command_id=resolved_command_id,
        command_type=file_command_type,
        requested_command_type=normalized_command_type,
        robot_id=normalized_robot_id,
        requested_by=normalized_requested_by,
        map_id=resolved_map_id,
        target_zone_id=target_zone_id,
        payload=command_payload,
        preempt_current_navigation=resolved_preempt_current_navigation,
    )
    _write_json_atomic(command_file_path(), bridge_payload)

    response = {
        "accepted": True,
        "command_id": resolved_command_id,
        "requested_command_type": normalized_command_type,
        "command_type": file_command_type,
        "robot_id": normalized_robot_id,
        "requested_by": normalized_requested_by,
        "map_id": resolved_map_id,
        "bridge_file": str(command_file_path()),
        "status_endpoint": "/api/v1/robot/commands/latest",
        "target_pose": command_payload.get("target_pose"),
        "preempt_current_navigation": resolved_preempt_current_navigation,
    }
    if resolved_zone is not None:
        response["target_zone"] = {
            "id": resolved_zone["id"],
            "name": resolved_zone["name"],
            "representative_waypoint_id": resolved_zone["representative_waypoint_id"],
        }
    if command_payload.get("home_waypoint_id"):
        response["home_waypoint_id"] = command_payload["home_waypoint_id"]
    return response


def read_latest_command_status_payload() -> dict[str, Any]:
    status_path = command_status_file_path()
    if not status_path.exists():
        return {
            "source": "runtime_file",
            "available": False,
            "status": "idle",
            "message": "아직 executor가 기록한 command status 파일이 없습니다.",
            "updated_at": _iso_now(),
        }

    try:
        payload = _read_json_object(status_path)
    except (OSError, json.JSONDecodeError, RobotCommandValidationError) as exc:
        raise RobotCommandValidationError(
            f"robot_manual_command_status.json 을 읽지 못했습니다: {exc}"
        ) from exc

    result = {"source": "runtime_file", "available": True, **payload}
    command_path = command_file_path()
    if command_path.exists():
        try:
            command_payload = _read_json_object(command_path)
        except (OSError, json.JSONDecodeError, RobotCommandValidationError):
            command_payload = {}

        if command_payload.get("command_id") == payload.get("command_id"):
            requested_command_type = command_payload.get("requested_command_type")
            if requested_command_type:
                result["requested_command_type"] = requested_command_type
            if command_payload.get("target_zone_id"):
                result["target_zone_id"] = command_payload["target_zone_id"]
            if "preempt_current_navigation" in command_payload:
                result["preempt_current_navigation"] = bool(
                    command_payload["preempt_current_navigation"]
                )

    return result
