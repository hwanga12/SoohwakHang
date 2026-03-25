from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

SUPPORTED_REQUEST_TYPES = {'start_patrol', 'harvest_target'}
PATROL_RUNNING_STATES = {'starting', 'running', 'observing', 'stopping'}
HARVEST_RUNNING_STATES = {
    'waiting_for_patrol_pause',
    'approaching',
    'aligning',
    'aligned',
    'harvesting',
    'returning',
    'resuming_patrol',
}


class MissionBridgeValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MissionRequest:
    command_id: str
    mission_id: str
    request_type: str
    robot_id: str
    requested_by: str
    zone_ids: tuple[str, ...] = ()
    loop_count: int = 1
    patrol_mode: str = 'diagnosis'
    plant_id: str | None = None
    fruit_id: str | None = None
    tomato_id: str | None = None

    @property
    def effective_tomato_id(self) -> str:
        return self.tomato_id or self.fruit_id or ''


def _extract_string(payload: dict[str, Any], key: str, *, default: str = '') -> str:
    raw_value = payload.get(key, default)
    return str(raw_value).strip() if raw_value is not None else default


def _extract_int(payload: dict[str, Any], key: str, *, default: int) -> int:
    raw_value = payload.get(key, default)
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise MissionBridgeValidationError(f'{key} 는 정수여야 합니다.') from exc


def _extract_payload_object(raw_payload: dict[str, Any]) -> dict[str, Any]:
    payload = raw_payload.get('payload')
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise MissionBridgeValidationError('payload는 JSON object여야 합니다.')
    return payload


def _extract_string_list(raw_payload: dict[str, Any], payload: dict[str, Any], key: str) -> tuple[str, ...]:
    source_value = raw_payload.get(key, payload.get(key))
    if source_value is None:
        return ()
    if not isinstance(source_value, list):
        raise MissionBridgeValidationError(f'{key} 는 문자열 배열이어야 합니다.')

    normalized_values: list[str] = []
    for item in source_value:
        normalized = str(item).strip()
        if normalized:
            normalized_values.append(normalized)
    return tuple(dict.fromkeys(normalized_values))


def parse_status_payload(raw_data: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def parse_mission_request_payload(
    raw_payload: dict[str, Any],
    *,
    default_robot_id: str = 'AGR-02',
) -> MissionRequest:
    payload = _extract_payload_object(raw_payload)
    command_id = _extract_string(raw_payload, 'command_id')
    request_type = (
        _extract_string(raw_payload, 'request_type')
        or _extract_string(raw_payload, 'command_type')
        or _extract_string(payload, 'request_type')
        or _extract_string(payload, 'command_type')
    )
    robot_id = _extract_string(raw_payload, 'robot_id', default=default_robot_id) or default_robot_id
    requested_by = (
        _extract_string(raw_payload, 'requested_by')
        or _extract_string(payload, 'requested_by')
    )
    mission_id = _extract_string(raw_payload, 'mission_id') or command_id

    if not command_id:
        raise MissionBridgeValidationError('robot_mission_request.json에 command_id가 없습니다.')
    if request_type not in SUPPORTED_REQUEST_TYPES:
        raise MissionBridgeValidationError(
            f'지원하지 않는 request_type 입니다: {request_type!r}. '
            f'허용값: {sorted(SUPPORTED_REQUEST_TYPES)}'
        )
    if not requested_by:
        raise MissionBridgeValidationError('requested_by 는 비어 있을 수 없습니다.')

    zone_ids = _extract_string_list(raw_payload, payload, 'zone_ids')
    loop_count = _extract_int(raw_payload, 'loop_count', default=_extract_int(payload, 'loop_count', default=1))
    patrol_mode = (
        _extract_string(raw_payload, 'patrol_mode')
        or _extract_string(payload, 'patrol_mode')
        or 'diagnosis'
    ).lower()
    plant_id = _extract_string(raw_payload, 'plant_id') or _extract_string(payload, 'plant_id') or None
    fruit_id = _extract_string(raw_payload, 'fruit_id') or _extract_string(payload, 'fruit_id') or None
    tomato_id = _extract_string(raw_payload, 'tomato_id') or _extract_string(payload, 'tomato_id') or None

    if request_type == 'start_patrol':
        if not zone_ids:
            raise MissionBridgeValidationError('start_patrol 요청에는 zone_ids가 필요합니다.')
        if loop_count <= 0:
            raise MissionBridgeValidationError('loop_count 는 1 이상이어야 합니다.')
        if patrol_mode not in {'diagnosis', 'harvest'}:
            raise MissionBridgeValidationError(
                "patrol_mode 는 'diagnosis' 또는 'harvest' 여야 합니다."
            )
    else:
        if not (tomato_id or fruit_id):
            raise MissionBridgeValidationError(
                'harvest_target 요청에는 fruit_id 또는 tomato_id 가 필요합니다.'
            )

    return MissionRequest(
        command_id=command_id,
        mission_id=mission_id,
        request_type=request_type,
        robot_id=robot_id,
        requested_by=requested_by,
        zone_ids=zone_ids,
        loop_count=max(1, loop_count),
        patrol_mode=patrol_mode,
        plant_id=plant_id,
        fruit_id=fruit_id,
        tomato_id=tomato_id,
    )


def patrol_bridge_status_from_payload(payload: dict[str, Any]) -> tuple[str, str, str | None, bool] | None:
    state = str(payload.get('state', '')).strip().lower()
    message = str(payload.get('message') or '').strip() or 'Patrol 상태를 확인했습니다.'
    error = str(payload.get('error') or '').strip() or None

    if state in PATROL_RUNNING_STATES:
        return ('running', message, None, False)
    if state == 'completed':
        return ('succeeded', message, None, True)
    if state == 'error':
        return ('failed', message, error or 'patrol_error', True)
    if state == 'stopped':
        return ('canceled', message, 'patrol_stopped', True)
    return None


def harvest_status_refers_to_request(payload: dict[str, Any], tomato_id: str) -> bool:
    if not tomato_id:
        return False

    active_tomato_id = str(payload.get('active_tomato_id') or '').strip()
    if active_tomato_id == tomato_id:
        return True

    message = str(payload.get('message') or '').strip()
    return tomato_id in message


def harvest_bridge_status_from_payload(payload: dict[str, Any]) -> tuple[str, str, str | None, bool] | None:
    state = str(payload.get('state', '')).strip().lower()
    message = str(payload.get('message') or '').strip() or 'Harvest route 상태를 확인했습니다.'
    error = str(payload.get('error') or '').strip() or None

    if state in HARVEST_RUNNING_STATES:
        return ('running', message, None, False)
    if state == 'completed':
        return ('succeeded', message, None, True)
    if state == 'error':
        return ('failed', message, error or 'harvest_route_error', True)
    return None
