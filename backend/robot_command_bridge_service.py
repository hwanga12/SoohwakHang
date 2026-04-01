# 이 모듈은 웹 요청을 로봇 명령 형식으로 검증하고 전달한다.
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from robot_runtime_state_service import (
    RobotRuntimeStateError,
    build_idle_command_status_payload,
    build_unavailable_control_state_payload,
    command_file_path,
    command_status_file_path,
    iso_now,
    read_control_state_payload,
    read_json_object,
    read_latest_command_status_payload as _read_latest_command_status_payload,
    write_json_atomic,
)
from zone_service import resolve_zone_payload, resolve_zone_representative_pose

DEFAULT_FRAME_ID = "map"
ALLOWED_COMMAND_TYPES = {
    "emergency_stop",
    "navigate_to_pose",
    "pause",
    "pause_motion",
    "pause_patrol",
    "resume",
    "resume_motion",
    "resume_patrol",
    "return_home",
    "move_to_zone",
}
COMMAND_TYPE_ALIASES = {
    "pause": "pause_motion",
    "resume": "resume_motion",
}
FILE_BRIDGE_COMMAND_TYPES = {
    "emergency_stop",
    "navigate_to_pose",
    "pause_motion",
    "pause_patrol",
    "resume_motion",
    "resume_patrol",
    "return_home",
}
DEFAULT_PREEMPT_COMMAND_TYPES = {
    "navigate_to_pose",
    "move_to_zone",
    "return_home",
}
CONTROL_STATE_REQUIRED_COMMAND_TYPES = {
    "emergency_stop",
    "pause_motion",
    "pause_patrol",
    "resume_motion",
    "resume_patrol",
}
LATCH_RELEASE_COMMAND_TYPES = {
    "emergency_stop",
    "resume_motion",
    "resume_patrol",
}
COMMAND_RECEIPT_MESSAGES = {
    "emergency_stop": "비상 정지 요청을 접수했습니다.",
    "pause": "일시정지 요청을 접수했습니다.",
    "pause_motion": "일시정지 요청을 접수했습니다.",
    "pause_patrol": "순찰 일시정지 요청을 접수했습니다.",
    "resume": "재개 요청을 접수했습니다.",
    "resume_motion": "재개 요청을 접수했습니다.",
    "resume_patrol": "순찰 재개 요청을 접수했습니다.",
    "return_home": "홈 복귀 요청을 접수했습니다.",
    "move_to_zone": "구역 이동 요청을 접수했습니다.",
    "navigate_to_pose": "좌표 이동 요청을 접수했습니다.",
}


class RobotCommandValidationError(ValueError):
    # 로봇 명령 validation error 문제를 구분하기 위한 예외 클래스다.
    pass


class DuplicateCommandIdError(RobotCommandValidationError):
    # duplicate 명령 id error 문제를 구분하기 위한 예외 클래스다.
    pass


class RobotCommandConflictError(RobotCommandValidationError):
    # 로봇 명령 conflict error 문제를 구분하기 위한 예외 클래스다.
    pass


class RobotCommandUnavailableError(RuntimeError):
    # 로봇 명령 unavailable error 문제를 구분하기 위한 예외 클래스다.
    pass


def _generate_command_id() -> str:
    # 명령 id을 생성한다.
    timestamp = int(time.time() * 1000)
    return f"robot-cmd-{timestamp}-{uuid.uuid4().hex[:8]}"


def _sanitize_command_id(command_id: str | None) -> str:
    # sanitize 명령 id 정보를 계산해 반환한다.
    if command_id is None or not str(command_id).strip():
        return _generate_command_id()
    return str(command_id).strip()


def _check_duplicate_command_id(command_id: str) -> None:
    # duplicate 명령 id 상태를 점검한다.
    for path in (command_file_path(), command_status_file_path()):
        if not path.exists():
            continue
        try:
            payload = read_json_object(path)
        except (OSError, json.JSONDecodeError, RobotRuntimeStateError):
            continue
        if str(payload.get("command_id", "")).strip() == command_id:
            raise DuplicateCommandIdError(
                f"이미 사용한 command_id 입니다: {command_id}. 새 command_id로 다시 요청하세요."
            )


def _validate_command_type(command_type: str) -> str:
    # 명령 type가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
    normalized = str(command_type).strip()
    if normalized not in ALLOWED_COMMAND_TYPES:
        raise RobotCommandValidationError(
            f"지원하지 않는 command_type 입니다: {normalized!r}. "
            f"허용값: {sorted(ALLOWED_COMMAND_TYPES)}"
        )
    return normalized


def _coerce_target_pose(payload: dict[str, Any]) -> dict[str, Any]:
    # coerce 대상 위치 자세 정보를 계산해 반환한다.
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
    # coerce 대상 위치 자세 object 정보를 계산해 반환한다.
    if not isinstance(target_pose, dict):
        raise RobotCommandValidationError("target_pose 는 JSON object여야 합니다.")
    return _coerce_target_pose({"target_pose": target_pose})


def _coerce_optional_waypoint_id(
    payload: dict[str, Any],
    *,
    field_name: str,
) -> str | None:
    # coerce optional 웨이포인트 id 정보를 계산해 반환한다.
    raw_value = payload.get(field_name)
    if raw_value is None:
        return None

    normalized = str(raw_value).strip()
    return normalized or None


def _coerce_optional_string_list(
    payload: dict[str, Any],
    *,
    field_name: str,
) -> list[str]:
    # coerce optional string 목록 정보를 계산해 반환한다.
    raw_value = payload.get(field_name)
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise RobotCommandValidationError(f"{field_name} 는 문자열 배열이어야 합니다.")

    values: list[str] = []
    for item in raw_value:
        normalized = str(item).strip()
        if normalized:
            values.append(normalized)

    return values


def _coerce_optional_observation_candidates(
    payload: dict[str, Any],
    *,
    field_name: str,
    map_id: str | None,
) -> list[dict[str, Any]]:
    # coerce optional 관측 후보 정보를 계산해 반환한다.
    raw_value = payload.get(field_name)
    if raw_value is None:
        return []
    if not isinstance(raw_value, list):
        raise RobotCommandValidationError(f"{field_name} 는 배열이어야 합니다.")

    candidates: list[dict[str, Any]] = []
    seen_waypoint_ids: set[str] = set()

    for index, item in enumerate(raw_value):
        if not isinstance(item, dict):
            raise RobotCommandValidationError(f"{field_name}[{index}] 는 JSON object여야 합니다.")

        inspect_waypoint_id = str(item.get("inspect_waypoint_id", "")).strip()
        if not inspect_waypoint_id:
            raise RobotCommandValidationError(
                f"{field_name}[{index}].inspect_waypoint_id 가 필요합니다."
            )
        if inspect_waypoint_id in seen_waypoint_ids:
            continue
        seen_waypoint_ids.add(inspect_waypoint_id)

        final_target_pose_payload = item.get("final_target_pose")
        if not isinstance(final_target_pose_payload, dict):
            raise RobotCommandValidationError(
                f"{field_name}[{index}].final_target_pose 가 필요합니다."
            )

        candidate_payload = {
            "inspect_waypoint_id": inspect_waypoint_id,
            "final_target_pose": _validate_target_pose_bounds(
                _coerce_target_pose_object(final_target_pose_payload),
                map_id,
            ),
        }

        inspect_waypoint_name = str(item.get("inspect_waypoint_name", "")).strip()
        if inspect_waypoint_name:
            candidate_payload["inspect_waypoint_name"] = inspect_waypoint_name

        navigation_pose_payload = item.get("navigation_pose")
        if isinstance(navigation_pose_payload, dict):
            candidate_payload["navigation_pose"] = _validate_target_pose_bounds(
                _coerce_target_pose_object(navigation_pose_payload),
                map_id,
            )

        candidates.append(candidate_payload)

    return candidates


def _validate_target_pose_bounds(
    target_pose: dict[str, Any],
    map_id: str | None = None,
) -> dict[str, Any]:
    # target 위치 자세 bounds가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
    from robot_map_service import read_map_payload

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
    # requested BY를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(requested_by).strip()
    if not normalized:
        raise RobotCommandValidationError("requested_by 는 비어 있을 수 없습니다.")
    return normalized


def _normalize_robot_id(robot_id: str) -> str:
    # robot ID를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(robot_id).strip()
    if not normalized:
        raise RobotCommandValidationError("robot_id 는 비어 있을 수 없습니다.")
    return normalized


def _payload_or_empty(payload: dict[str, Any] | None) -> dict[str, Any]:
    # 페이로드 empty 정보를 계산해 반환한다.
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise RobotCommandValidationError("payload는 JSON object여야 합니다.")
    return payload


def _coerce_optional_bool(value: Any, *, field_name: str) -> bool | None:
    # coerce optional bool 정보를 계산해 반환한다.
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
    # 현재 입력 조건을 바탕으로 preempt current navigation를 계산하거나 결정한다.
    if explicit_value is not None:
        return explicit_value

    payload_value = _coerce_optional_bool(
        payload.get("preempt_current_navigation"),
        field_name="payload.preempt_current_navigation",
    )
    if payload_value is not None:
        return payload_value

    return command_type in DEFAULT_PREEMPT_COMMAND_TYPES


def _normalize_command_for_bridge(command_type: str) -> tuple[str, str]:
    # 명령 FOR 브리지를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    requested_command_type = _validate_command_type(command_type)
    return requested_command_type, COMMAND_TYPE_ALIASES.get(
        requested_command_type,
        requested_command_type,
    )


def _safe_read_control_state_payload() -> dict[str, Any]:
    # safe 읽기 제어 상태 페이로드 정보를 계산해 반환한다.
    try:
        return read_control_state_payload()
    except RobotRuntimeStateError as exc:
        return build_unavailable_control_state_payload(str(exc))


def _safe_read_latest_command_status_payload(
    *,
    control_state: dict[str, Any],
) -> dict[str, Any]:
    # safe 읽기 최신 명령 상태 페이로드 정보를 계산해 반환한다.
    try:
        return _read_latest_command_status_payload()
    except RobotRuntimeStateError as exc:
        return {
            **build_idle_command_status_payload(str(exc), control_state=control_state),
            "control_state": control_state,
            "control_mode": control_state["mode"],
            "control_is_latched": control_state["is_latched"],
            "control_active_activity": control_state["active_activity"],
            "control_blocking_reason": control_state["blocking_reason"],
            "control_message": control_state["message"],
            "control_resume_available": control_state["resume_available"],
            "control_updated_at": control_state["updated_at"],
        }


def _effective_active_activity(
    control_state: dict[str, Any],
    latest_status: dict[str, Any],
) -> str:
    # effective active activity 정보를 계산해 반환한다.
    active_activity = str(control_state.get("active_activity") or "").strip() or "idle"
    if active_activity != "idle":
        return active_activity

    if str(latest_status.get("status") or "").strip() not in {"pending", "running"}:
        return active_activity

    requested_command_type = str(latest_status.get("requested_command_type") or "").strip()
    command_type = str(latest_status.get("command_type") or "").strip()
    effective_command_type = requested_command_type or command_type
    if effective_command_type in {"navigate_to_pose", "move_to_zone", "return_home"}:
        return "manual_navigation"
    if effective_command_type in {"pause_patrol", "resume_patrol"}:
        return "patrol"
    return active_activity


def _resume_context_type(control_state: dict[str, Any]) -> str | None:
    # resume context type 정보를 계산해 반환한다.
    resume_context = control_state.get("resume_context")
    if not isinstance(resume_context, dict):
        return None
    normalized = str(resume_context.get("context_type") or "").strip()
    return normalized or None


def _validate_command_for_current_state(
    *,
    requested_command_type: str,
    normalized_command_type: str,
    control_state: dict[str, Any],
    latest_status: dict[str, Any],
) -> None:
    # 명령 FOR current 상태가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
    if (
        normalized_command_type in CONTROL_STATE_REQUIRED_COMMAND_TYPES
        and not bool(control_state.get("available"))
    ):
        raise RobotCommandUnavailableError(
            "executor control state를 읽을 수 없어 제어 명령을 검증할 수 없습니다. "
            "agribot_ws runtime executor 상태를 먼저 확인하세요."
        )

    control_mode = str(control_state.get("mode") or "normal")
    if (
        bool(control_state.get("is_latched"))
        and normalized_command_type not in LATCH_RELEASE_COMMAND_TYPES
    ):
        raise RobotCommandConflictError(
            f"현재 제어 상태가 {control_mode} 이라 {requested_command_type} 요청을 받을 수 없습니다. "
            "resume_motion 또는 resume_patrol 로 먼저 해제하세요."
        )

    effective_activity = _effective_active_activity(control_state, latest_status)
    resume_context_type = _resume_context_type(control_state)

    if normalized_command_type == "emergency_stop" and control_mode == "emergency_stop":
        raise RobotCommandConflictError("이미 비상 정지 상태입니다.")

    if normalized_command_type in {"pause_motion", "pause_patrol"}:
        if control_mode == "paused":
            raise RobotCommandConflictError("이미 일시정지 상태입니다.")
        if control_mode == "emergency_stop":
            raise RobotCommandConflictError("비상 정지 상태에서는 추가 pause 요청을 받을 수 없습니다.")
        if effective_activity == "idle":
            if normalized_command_type == "pause_patrol":
                raise RobotCommandConflictError("현재 일시정지할 순찰이 없습니다.")
            raise RobotCommandConflictError("현재 일시정지할 동작이 없습니다.")
        if normalized_command_type == "pause_patrol" and effective_activity != "patrol":
            raise RobotCommandConflictError(
                "현재 순찰 중이 아니어서 pause_patrol 을 적용할 수 없습니다."
            )

    if normalized_command_type == "resume_motion" and control_mode == "normal":
        raise RobotCommandConflictError("현재 해제하거나 재개할 제어 latch가 없습니다.")

    if normalized_command_type == "resume_patrol":
        if control_mode != "normal" and resume_context_type not in {None, "patrol"}:
            raise RobotCommandConflictError(
                "저장된 재개 문맥이 순찰이 아니어서 resume_patrol 을 적용할 수 없습니다."
            )
        if control_mode == "normal" and effective_activity == "patrol":
            raise RobotCommandConflictError("이미 순찰이 실행 중입니다.")


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
    # 브리지 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    bridge_payload: dict[str, Any] = {
        "command_id": command_id,
        "command_type": command_type,
        "robot_id": robot_id,
        "requested_by": requested_by,
        "map_id": map_id,
        "issued_at": iso_now(),
        "preempt_current_navigation": preempt_current_navigation,
    }
    if payload:
        bridge_payload["payload"] = payload
    if target_zone_id:
        bridge_payload["target_zone_id"] = target_zone_id
    if requested_command_type and requested_command_type != command_type:
        bridge_payload["requested_command_type"] = requested_command_type
    return bridge_payload


def _build_command_receipt_message(requested_command_type: str) -> str:
    # 명령 receipt message를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return COMMAND_RECEIPT_MESSAGES.get(
        requested_command_type,
        f"{requested_command_type} 요청을 접수했습니다.",
    )


def _build_publish_response(
    *,
    bridge_payload: dict[str, Any],
    requested_command_type: str,
    command_type: str,
    robot_id: str,
    requested_by: str,
    map_id: str,
    preempt_current_navigation: bool,
    target_pose: dict[str, Any] | None,
    target_zone_id: str | None,
    target_zone: dict[str, Any] | None,
    home_waypoint_id: str | None,
    current_control_state: dict[str, Any],
) -> dict[str, Any]:
    # publish 응답 데이터를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    message = _build_command_receipt_message(requested_command_type)
    response = {
        "accepted": True,
        "request_status": "accepted",
        "message": message,
        "command_id": bridge_payload["command_id"],
        "requested_command_type": requested_command_type,
        "command_type": command_type,
        "robot_id": robot_id,
        "requested_by": requested_by,
        "map_id": map_id,
        "bridge_file": str(command_file_path()),
        "status_endpoint": "/api/v1/robot/commands/latest",
        "control_status_endpoint": "/api/v1/robot/control/status",
        "target_pose": target_pose,
        "target_zone_id": target_zone_id,
        "preempt_current_navigation": preempt_current_navigation,
        "request": {
            "accepted": True,
            "status": "accepted",
            "message": message,
            "requested_at": bridge_payload["issued_at"],
        },
        "current_control_state": current_control_state,
    }
    if target_zone is not None:
        response["target_zone"] = {
            "id": target_zone["id"],
            "name": target_zone["name"],
            "representative_waypoint_id": target_zone["representative_waypoint_id"],
        }
    if home_waypoint_id:
        response["home_waypoint_id"] = home_waypoint_id
    return response


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
    # robot 명령를 외부 시스템이나 다음 처리 단계로 전달한다.
    from robot_map_service import read_map_payload

    requested_command_type, normalized_command_type = _normalize_command_for_bridge(command_type)
    control_state = _safe_read_control_state_payload()
    latest_status = _safe_read_latest_command_status_payload(control_state=control_state)
    _validate_command_for_current_state(
        requested_command_type=requested_command_type,
        normalized_command_type=normalized_command_type,
        control_state=control_state,
        latest_status=latest_status,
    )

    resolved_map_id = read_map_payload(map_id)["map_id"]
    normalized_robot_id = _normalize_robot_id(robot_id)
    normalized_requested_by = _normalize_requested_by(requested_by)
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
        inspect_waypoint_id = _coerce_optional_waypoint_id(
            normalized_payload,
            field_name="inspect_waypoint_id",
        )
        if inspect_waypoint_id:
            command_payload["inspect_waypoint_id"] = inspect_waypoint_id
        inspect_waypoint_ids = _coerce_optional_string_list(
            normalized_payload,
            field_name="inspect_waypoint_ids",
        )
        if inspect_waypoint_ids:
            command_payload["inspect_waypoint_ids"] = inspect_waypoint_ids
        observation_candidates = _coerce_optional_observation_candidates(
            normalized_payload,
            field_name="observation_candidates",
            map_id=resolved_map_id,
        )
        if observation_candidates:
            command_payload["observation_candidates"] = observation_candidates
        plant_id = str(normalized_payload.get("plant_id", "")).strip()
        if plant_id:
            command_payload["plant_id"] = plant_id
    elif normalized_command_type == "move_to_zone":
        resolved_target_zone_id = str(target_zone_id or "").strip()
        if not resolved_target_zone_id:
            raise RobotCommandValidationError(
                "move_to_zone 명령에는 target_zone_id 가 필요합니다."
            )
        resolved_zone = resolve_zone_payload(resolved_target_zone_id, resolved_map_id)
        command_payload["target_pose"] = _validate_target_pose_bounds(
            resolve_zone_representative_pose(resolved_target_zone_id, resolved_map_id),
            resolved_map_id,
        )
        target_zone_id = resolved_target_zone_id
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
        requested_command_type=requested_command_type,
        robot_id=normalized_robot_id,
        requested_by=normalized_requested_by,
        map_id=resolved_map_id,
        target_zone_id=target_zone_id,
        payload=command_payload,
        preempt_current_navigation=resolved_preempt_current_navigation,
    )
    write_json_atomic(command_file_path(), bridge_payload)

    return _build_publish_response(
        bridge_payload=bridge_payload,
        requested_command_type=requested_command_type,
        command_type=file_command_type,
        robot_id=normalized_robot_id,
        requested_by=normalized_requested_by,
        map_id=resolved_map_id,
        preempt_current_navigation=resolved_preempt_current_navigation,
        target_pose=command_payload.get("target_pose"),
        target_zone_id=target_zone_id,
        target_zone=resolved_zone,
        home_waypoint_id=command_payload.get("home_waypoint_id"),
        current_control_state=control_state,
    )


def read_latest_command_status_payload() -> dict[str, Any]:
    # latest 명령 상태 payload를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return _read_latest_command_status_payload()
