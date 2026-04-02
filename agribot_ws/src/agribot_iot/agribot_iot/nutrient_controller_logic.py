# 이 모듈은 IoT 장치 연동 패키지에서 nutrient controller logic 장치 흐름을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
import json

from agribot_interfaces.msg import IoTCommand, IoTDeviceState

from .device_mapping import IoTDeviceSpec


@dataclass(frozen=True)
class NutrientExecutionPlan:
    # 영양제 execution 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    accepted: bool
    command_id: str
    zone_id: str
    device_id: str
    command_type: str
    success: bool
    immediate_completion: bool
    nutrient_type: str
    requested_by: str
    target_value: float
    unit: str
    duration_sec: float
    detail_message: str


def plan_nutrient_command(command: IoTCommand, device: IoTDeviceSpec) -> NutrientExecutionPlan:
    # 영양제 명령를 어떤 순서와 조건으로 처리할지 계획한다.
    normalized_command_type = command.command_type.strip().lower()
    normalized_unit = command.unit.strip().lower()
    requested_by = command.requested_by.strip() or 'unknown'
    nutrient_type = _extract_nutrient_type(command.reason) or 'generic'
    target_value = max(0.0, float(command.target_value))
    unit = normalized_unit or device.default_unit or 'ml'

    if command.device_type.strip().lower() != 'nutrient':
        return NutrientExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id,
            device_id=command.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            nutrient_type=nutrient_type,
            requested_by=requested_by,
            target_value=target_value,
            unit=unit,
            duration_sec=0.0,
            detail_message='Ignoring non-nutrient command.',
        )

    if command.device_id and command.device_id != device.device_id:
        return NutrientExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=command.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            nutrient_type=nutrient_type,
            requested_by=requested_by,
            target_value=target_value,
            unit=unit,
            duration_sec=0.0,
            detail_message=f'Unknown nutrient device_id: {command.device_id}',
        )

    if normalized_command_type != 'apply_nutrient_recipe':
        return NutrientExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=device.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            nutrient_type=nutrient_type,
            requested_by=requested_by,
            target_value=target_value,
            unit=unit,
            duration_sec=0.0,
            detail_message=f'Unsupported nutrient command_type: {normalized_command_type}',
        )

    if target_value <= 0.0:
        return NutrientExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=device.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            nutrient_type=nutrient_type,
            requested_by=requested_by,
            target_value=target_value,
            unit=unit,
            duration_sec=0.0,
            detail_message='Nutrient target_value must be greater than 0.',
        )

    duration_sec = 0.0
    if device.flow_rate_per_sec > 0.0:
        duration_sec = max(0.0, target_value / device.flow_rate_per_sec)

    return NutrientExecutionPlan(
        accepted=True,
        command_id=command.command_id,
        zone_id=command.zone_id or device.zone_id,
        device_id=device.device_id,
        command_type=normalized_command_type,
        success=True,
        immediate_completion=duration_sec <= 0.0,
        nutrient_type=nutrient_type,
        requested_by=requested_by,
        target_value=target_value,
        unit=unit,
        duration_sec=duration_sec,
        detail_message=(
            f'Applying nutrient recipe {nutrient_type} '
            f'for {target_value:.1f}{unit} requested by {requested_by}.'
        ),
    )


def build_nutrient_state(
    device: IoTDeviceSpec,
    *,
    state: str,
    current_value: float,
    detail_message: str,
) -> IoTDeviceState:
    # 영양제 상태를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    message = IoTDeviceState()
    message.device_id = device.device_id
    message.zone_id = device.zone_id
    message.device_type = device.device_type
    message.state = state
    message.current_value = max(0.0, float(current_value))
    message.unit = device.default_unit or 'ml'
    message.is_available = device.is_available
    message.detail_message = detail_message
    return message


def build_nutrient_result_payload(
    plan: NutrientExecutionPlan,
    *,
    success: bool,
    state: str,
    detail_message: str,
    executed_duration_sec: float,
) -> str:
    # 영양제 결과 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    payload = {
        'command_id': plan.command_id,
        'zone_id': plan.zone_id,
        'device_id': plan.device_id,
        'device_type': 'nutrient',
        'command_type': plan.command_type,
        'success': bool(success),
        'state': state,
        'target_value': float(plan.target_value),
        'unit': plan.unit,
        'planned_duration_sec': float(plan.duration_sec),
        'executed_duration_sec': float(executed_duration_sec),
        'requested_by': plan.requested_by,
        'nutrient_type': plan.nutrient_type,
        'detail_message': detail_message,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _extract_nutrient_type(reason: str) -> str:
    # 원본 데이터에서 영양제 type만 골라 추출한다.
    payload = _extract_payload_map(reason)
    return payload.get('nutrient_type', '').strip()


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
