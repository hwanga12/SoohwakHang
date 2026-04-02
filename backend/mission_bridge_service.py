# 이 모듈은 백엔드와 ROS 런타임 사이의 미션 상태 연계를 담당.
from __future__ import annotations

import json
import uuid
from typing import Any

from ros_protocol_bridge import get_ros_protocol_bridge
from robot_runtime_state_service import (
    RobotRuntimeStateError,
    build_idle_mission_status_payload,
    iso_now,
    mission_request_file_path,
    mission_status_file_path,
    mission_status_record_file_path,
    read_json_object,
    read_latest_mission_status_payload as _read_latest_mission_status_payload,
    read_mission_status_payload as _read_mission_status_payload,
    write_json_atomic,
)

ALLOWED_REQUEST_TYPES = {"start_patrol", "harvest_target"}
ALLOWED_PATROL_MODES = {"diagnosis", "harvest"}


class MissionBridgeValidationError(ValueError):
    # 미션 브리지 validation error 문제를 구분하기 위한 예외 클래스다.
    pass


class DuplicateMissionIdError(MissionBridgeValidationError):
    # duplicate 미션 id error 문제를 구분하기 위한 예외 클래스다.
    pass


class MissionBridgeConflictError(MissionBridgeValidationError):
    # 미션 브리지 conflict error 문제를 구분하기 위한 예외 클래스다.
    pass


class MissionBridgeUnavailableError(RuntimeError):
    # 미션 브리지 unavailable error 문제를 구분하기 위한 예외 클래스다.
    pass


def _generate_mission_id(prefix: str) -> str:
    # 미션 id을 생성한다.
    del prefix
    return str(uuid.uuid4())


def _sanitize_mission_id(mission_id: str | None, *, prefix: str) -> str:
    # sanitize 미션 id 정보를 계산해 반환한다.
    if mission_id is None or not str(mission_id).strip():
        return _generate_mission_id(prefix)
    return str(mission_id).strip()


def _normalize_robot_id(robot_id: str) -> str:
    # robot ID를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(robot_id).strip()
    if not normalized:
        raise MissionBridgeValidationError("robot_id 는 비어 있을 수 없습니다.")
    return normalized


def _normalize_requested_by(requested_by: str) -> str:
    # requested BY를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(requested_by).strip()
    if not normalized:
        raise MissionBridgeValidationError("requested_by 는 비어 있을 수 없습니다.")
    return normalized


def _normalize_zone_ids(zone_ids: list[str]) -> list[str]:
    # 구역 ID 목록를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized_zone_ids = [str(zone_id).strip() for zone_id in zone_ids if str(zone_id).strip()]
    if not normalized_zone_ids:
        raise MissionBridgeValidationError("zone_ids 는 비어 있을 수 없습니다.")
    return list(dict.fromkeys(normalized_zone_ids))


def _normalize_loop_count(loop_count: int) -> int:
    # loop count를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    try:
        normalized = int(loop_count)
    except (TypeError, ValueError) as exc:
        raise MissionBridgeValidationError("loop_count 는 정수여야 합니다.") from exc

    if normalized <= 0:
        raise MissionBridgeValidationError("loop_count 는 1 이상이어야 합니다.")
    return normalized


def _normalize_patrol_mode(patrol_mode: str) -> str:
    # patrol 모드를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(patrol_mode).strip().lower()
    if normalized not in ALLOWED_PATROL_MODES:
        raise MissionBridgeValidationError(
            f"지원하지 않는 patrol_mode 입니다: {normalized!r}. "
            f"허용값: {sorted(ALLOWED_PATROL_MODES)}"
        )
    return normalized


def _safe_read_latest_mission_status_payload() -> dict[str, Any]:
    # safe 읽기 최신 미션 상태 페이로드 정보를 계산해 반환한다.
    try:
        return _read_latest_mission_status_payload()
    except RobotRuntimeStateError as exc:
        return build_idle_mission_status_payload(str(exc))


def _check_duplicate_mission_id(mission_id: str) -> None:
    # duplicate 미션 id 상태를 점검한다.
    for path in (
        mission_request_file_path(),
        mission_status_file_path(),
        mission_status_record_file_path(mission_id),
    ):
        if not path.exists():
            continue
        try:
            payload = read_json_object(path)
        except (OSError, json.JSONDecodeError, RobotRuntimeStateError):
            continue
        existing_id = str(payload.get("mission_id") or payload.get("command_id") or "").strip()
        if existing_id == mission_id:
            raise DuplicateMissionIdError(
                f"이미 사용한 mission_id 입니다: {mission_id}. 새 mission_id로 다시 요청하세요."
            )


def _ensure_no_active_mission() -> None:
    # NO active 미션가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
    latest_status = _safe_read_latest_mission_status_payload()
    if str(latest_status.get("status") or "").strip().lower() not in {"pending", "running"}:
        return

    active_request_type = str(latest_status.get("request_type") or "").strip()
    active_mission_id = str(latest_status.get("mission_id") or latest_status.get("command_id") or "").strip()
    raise MissionBridgeConflictError(
        "아직 완료되지 않은 operator mission 이 있습니다. "
        f"(request_type={active_request_type or 'unknown'}, mission_id={active_mission_id or 'unknown'})"
    )


def _build_request_payload(
    *,
    mission_id: str,
    request_type: str,
    robot_id: str,
    requested_by: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    # 요청 데이터 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    if request_type not in ALLOWED_REQUEST_TYPES:
        raise MissionBridgeValidationError(
            f"지원하지 않는 request_type 입니다: {request_type!r}. "
            f"허용값: {sorted(ALLOWED_REQUEST_TYPES)}"
        )

    return {
        "mission_id": mission_id,
        "command_id": mission_id,
        "request_type": request_type,
        "robot_id": robot_id,
        "requested_by": requested_by,
        "issued_at": iso_now(),
        **payload,
    }


def _build_publish_response(
    *,
    bridge_payload: dict[str, Any],
    operator_message: str,
) -> dict[str, Any]:
    # publish 응답 데이터를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    mission_id = str(bridge_payload["mission_id"])
    request_type = str(bridge_payload["request_type"])

    response = {
        "accepted": True,
        "request_status": "accepted",
        "message": operator_message,
        "operator_message": operator_message,
        "mission_id": mission_id,
        "command_id": mission_id,
        "request_type": request_type,
        "requested_type": request_type,
        "robot_id": bridge_payload["robot_id"],
        "requested_by": bridge_payload["requested_by"],
        "bridge_file": str(mission_request_file_path()),
        "status_endpoint": f"/api/v1/missions/{mission_id}",
        "request": {
            "accepted": True,
            "status": "accepted",
            "message": operator_message,
            "requested_at": bridge_payload["issued_at"],
        },
    }

    for field_name in (
        "zone_ids",
        "loop_count",
        "patrol_mode",
        "plant_id",
        "fruit_id",
        "tomato_id",
        "inspect_waypoint_id",
        "inspect_waypoint_ids",
    ):
        if field_name in bridge_payload and bridge_payload.get(field_name) is not None:
            response[field_name] = bridge_payload.get(field_name)

    return response


def publish_patrol_start_mission(
    *,
    robot_id: str,
    zone_ids: list[str],
    loop_count: int,
    requested_by: str,
    patrol_mode: str,
    mission_id: str | None = None,
) -> dict[str, Any]:
    # patrol start 미션를 외부 시스템이나 다음 처리 단계로 전달한다.
    _ensure_no_active_mission()
    normalized_robot_id = _normalize_robot_id(robot_id)
    normalized_requested_by = _normalize_requested_by(requested_by)
    normalized_zone_ids = _normalize_zone_ids(zone_ids)
    normalized_loop_count = _normalize_loop_count(loop_count)
    normalized_patrol_mode = _normalize_patrol_mode(patrol_mode)
    resolved_mission_id = _sanitize_mission_id(mission_id, prefix="mission-patrol")
    _check_duplicate_mission_id(resolved_mission_id)

    bridge_payload = _build_request_payload(
        mission_id=resolved_mission_id,
        request_type="start_patrol",
        robot_id=normalized_robot_id,
        requested_by=normalized_requested_by,
        payload={
            "zone_ids": normalized_zone_ids,
            "loop_count": normalized_loop_count,
            "patrol_mode": normalized_patrol_mode,
        },
    )
    bridge = get_ros_protocol_bridge()
    published_transport = "ros_topic" if bridge.publish_mission_request(bridge_payload) else "runtime_file"
    if published_transport != "ros_topic":
        write_json_atomic(mission_request_file_path(), bridge_payload)

    operator_message = "패트롤 시작 요청을 접수했습니다. mission status를 확인하세요."
    response = _build_publish_response(
        bridge_payload=bridge_payload,
        operator_message=operator_message,
    )
    response["transport"] = published_transport
    return response


def publish_harvest_target_mission(
    *,
    robot_id: str,
    plant_id: str,
    fruit_id: str,
    requested_by: str,
    mission_id: str | None = None,
    inspect_waypoint_id: str | None = None,
    inspect_waypoint_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    # harvest target 미션를 외부 시스템이나 다음 처리 단계로 전달한다.
    _ensure_no_active_mission()
    normalized_robot_id = _normalize_robot_id(robot_id)
    normalized_requested_by = _normalize_requested_by(requested_by)
    normalized_plant_id = str(plant_id).strip()
    normalized_fruit_id = str(fruit_id).strip()
    normalized_inspect_waypoint_id = str(inspect_waypoint_id or "").strip() or None
    normalized_inspect_waypoint_ids = [
        str(waypoint_id).strip()
        for waypoint_id in (inspect_waypoint_ids or [])
        if str(waypoint_id).strip()
    ]
    if normalized_inspect_waypoint_id and normalized_inspect_waypoint_id not in normalized_inspect_waypoint_ids:
        normalized_inspect_waypoint_ids.insert(0, normalized_inspect_waypoint_id)

    if not normalized_plant_id:
        raise MissionBridgeValidationError("plant_id 는 비어 있을 수 없습니다.")
    if not normalized_fruit_id:
        raise MissionBridgeValidationError("fruit_id 는 비어 있을 수 없습니다.")

    resolved_mission_id = _sanitize_mission_id(mission_id, prefix="mission-harvest")
    _check_duplicate_mission_id(resolved_mission_id)

    bridge_payload = _build_request_payload(
        mission_id=resolved_mission_id,
        request_type="harvest_target",
        robot_id=normalized_robot_id,
        requested_by=normalized_requested_by,
        payload={
            "plant_id": normalized_plant_id,
            "fruit_id": normalized_fruit_id,
            "tomato_id": normalized_fruit_id,
            "inspect_waypoint_id": normalized_inspect_waypoint_id,
            "inspect_waypoint_ids": normalized_inspect_waypoint_ids or None,
        },
    )
    bridge = get_ros_protocol_bridge()
    published_transport = "ros_topic" if bridge.publish_mission_request(bridge_payload) else "runtime_file"
    if published_transport != "ros_topic":
        write_json_atomic(mission_request_file_path(), bridge_payload)

    operator_message = "수확 target 요청을 접수했습니다. mission status를 확인하세요."
    response = _build_publish_response(
        bridge_payload=bridge_payload,
        operator_message=operator_message,
    )
    response["transport"] = published_transport
    return response


def read_latest_mission_status_payload() -> dict[str, Any]:
    # latest 미션 상태 payload를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return _read_latest_mission_status_payload()


def read_mission_status_payload(mission_id: str) -> dict[str, Any]:
    # 미션 상태 payload를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return _read_mission_status_payload(mission_id)
