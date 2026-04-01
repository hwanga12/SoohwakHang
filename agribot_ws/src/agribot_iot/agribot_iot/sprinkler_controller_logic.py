# 이 모듈은 IoT 장치 연동 패키지에서 sprinkler controller logic 장치 흐름을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
import json

from agribot_interfaces.msg import IoTCommand, IoTDeviceState

from .device_mapping import IoTDeviceSpec


@dataclass(frozen=True)
class SprinklerExecutionPlan:
    # sprinkler execution 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    accepted: bool
    command_id: str
    zone_id: str
    device_id: str
    command_type: str
    success: bool
    immediate_completion: bool
    treatment_type: str
    effect_color: str
    requested_by: str
    target_value: float
    unit: str
    duration_sec: float
    detail_message: str


_COMMAND_PROFILES = {
    'spray_water': {
        'treatment_type': 'water_spray',
        'effect_color': 'blue',
    },
    'spray_nutrient_solution': {
        'treatment_type': 'nutrient_solution_spray',
        'effect_color': 'green',
    },
    'spray_pesticide': {
        'treatment_type': 'pesticide_spray',
        'effect_color': 'red',
    },
    'spray_calcium_solution': {
        'treatment_type': 'calcium_solution_spray',
        'effect_color': 'yellow',
    },
}
_STOP_COMMANDS = {
    'stop_spray',
    'hold_spray',
}


def plan_sprinkler_command(command: IoTCommand, device: IoTDeviceSpec) -> SprinklerExecutionPlan:
    # sprinkler 명령를 어떤 순서와 조건으로 처리할지 계획한다.
    normalized_command_type = command.command_type.strip().lower()
    normalized_unit = command.unit.strip().lower()
    requested_by = command.requested_by.strip() or 'unknown'
    payload = _extract_payload_map(command.reason)
    command_profile = _COMMAND_PROFILES.get(normalized_command_type)
    target_value = max(0.0, float(command.target_value))
    unit = normalized_unit or device.default_unit or 'sec'

    if command.device_type.strip().lower() != 'sprinkler':
        return _build_rejected_plan(
            command=command,
            device=device,
            command_type=normalized_command_type,
            requested_by=requested_by,
            target_value=target_value,
            unit=unit,
            detail_message='Ignoring non-sprinkler command.',
        )

    if command.device_id and command.device_id != device.device_id:
        return _build_rejected_plan(
            command=command,
            device=device,
            command_type=normalized_command_type,
            requested_by=requested_by,
            target_value=target_value,
            unit=unit,
            detail_message=f'Unknown sprinkler device_id: {command.device_id}',
        )

    if normalized_command_type in _STOP_COMMANDS:
        return SprinklerExecutionPlan(
            accepted=True,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=device.device_id,
            command_type=normalized_command_type,
            success=True,
            immediate_completion=True,
            treatment_type=payload.get('treatment_type', '').strip(),
            effect_color=payload.get('effect_color', '').strip(),
            requested_by=requested_by,
            target_value=0.0,
            unit=unit,
            duration_sec=0.0,
            detail_message='Sprinkler spray stop acknowledged.',
        )

    if command_profile is None:
        return _build_rejected_plan(
            command=command,
            device=device,
            command_type=normalized_command_type,
            requested_by=requested_by,
            target_value=target_value,
            unit=unit,
            detail_message=f'Unsupported sprinkler command_type: {normalized_command_type}',
        )

    if target_value <= 0.0:
        return _build_rejected_plan(
            command=command,
            device=device,
            command_type=normalized_command_type,
            requested_by=requested_by,
            target_value=target_value,
            unit=unit,
            detail_message='Sprinkler target_value must be greater than 0 seconds.',
        )

    effect_color = payload.get('effect_color', '').strip() or command_profile['effect_color']
    treatment_type = payload.get('treatment_type', '').strip() or command_profile['treatment_type']
    return SprinklerExecutionPlan(
        accepted=True,
        command_id=command.command_id,
        zone_id=command.zone_id or device.zone_id,
        device_id=device.device_id,
        command_type=normalized_command_type,
        success=True,
        immediate_completion=False,
        treatment_type=treatment_type,
        effect_color=effect_color,
        requested_by=requested_by,
        target_value=target_value,
        unit=unit,
        duration_sec=target_value,
        detail_message=(
            f'Executing sprinkler spray {normalized_command_type} '
            f'for {target_value:.2f}{unit} requested by {requested_by}.'
        ),
    )


def build_sprinkler_state(
    device: IoTDeviceSpec,
    *,
    state: str,
    current_value: float,
    detail_message: str,
) -> IoTDeviceState:
    # sprinkler 상태를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    message = IoTDeviceState()
    message.device_id = device.device_id
    message.zone_id = device.zone_id
    message.device_type = device.device_type
    message.state = state
    message.current_value = max(0.0, float(current_value))
    message.unit = device.default_unit or 'sec'
    message.is_available = device.is_available
    message.detail_message = detail_message
    return message


def build_sprinkler_result_payload(
    plan: SprinklerExecutionPlan,
    *,
    success: bool,
    state: str,
    detail_message: str,
    executed_duration_sec: float,
) -> str:
    # sprinkler 결과 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    payload = {
        'command_id': plan.command_id,
        'zone_id': plan.zone_id,
        'device_id': plan.device_id,
        'device_type': 'sprinkler',
        'command_type': plan.command_type,
        'success': bool(success),
        'state': state,
        'target_value': float(plan.target_value),
        'unit': plan.unit,
        'planned_duration_sec': float(plan.duration_sec),
        'executed_duration_sec': float(executed_duration_sec),
        'requested_by': plan.requested_by,
        'treatment_type': plan.treatment_type,
        'effect_color': plan.effect_color,
        'detail_message': detail_message,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _build_rejected_plan(
    *,
    command: IoTCommand,
    device: IoTDeviceSpec,
    command_type: str,
    requested_by: str,
    target_value: float,
    unit: str,
    detail_message: str,
) -> SprinklerExecutionPlan:
    # rejected 계획를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return SprinklerExecutionPlan(
        accepted=False,
        command_id=command.command_id,
        zone_id=command.zone_id or device.zone_id,
        device_id=command.device_id or device.device_id,
        command_type=command_type,
        success=False,
        immediate_completion=True,
        treatment_type='',
        effect_color='',
        requested_by=requested_by,
        target_value=target_value,
        unit=unit,
        duration_sec=0.0,
        detail_message=detail_message,
    )


def _extract_payload_map(reason: str) -> dict[str, str]:
    # 원본 데이터에서 payload 지도만 골라 추출한다.
    reason = reason.strip()
    marker = 'payload='
    marker_index = reason.find(marker)
    if marker_index < 0:
        return {}

    payload_text = reason[marker_index + len(marker):].strip()
    if not payload_text:
        return {}

    parsed: dict[str, str] = {}
    for item in payload_text.split(','):
        if '=' not in item:
            continue
        key, value = item.split('=', 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            parsed[key] = value
    return parsed
