from __future__ import annotations

from dataclasses import dataclass
import json

from agribot_interfaces.msg import IoTCommand, IoTDeviceState

from .device_mapping import IoTDeviceSpec


@dataclass(frozen=True)
class WateringExecutionPlan:
    accepted: bool
    command_id: str
    zone_id: str
    device_id: str
    command_type: str
    success: bool
    immediate_completion: bool
    target_value: float
    unit: str
    duration_sec: float
    detail_message: str


def plan_watering_command(command: IoTCommand, device: IoTDeviceSpec) -> WateringExecutionPlan:
    normalized_command_type = command.command_type.strip()
    if command.device_type.strip() != 'watering':
        return WateringExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id,
            device_id=command.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            target_value=float(command.target_value),
            unit=command.unit,
            duration_sec=0.0,
            detail_message='Ignoring non-watering command.',
        )

    if command.device_id and command.device_id != device.device_id:
        return WateringExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id,
            device_id=command.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            target_value=float(command.target_value),
            unit=command.unit,
            duration_sec=0.0,
            detail_message=f'Unknown watering device_id: {command.device_id}',
        )

    if normalized_command_type == 'dispense_water':
        duration_sec = 0.0
        if device.flow_rate_per_sec > 0.0:
            duration_sec = max(0.0, float(command.target_value) / device.flow_rate_per_sec)
        return WateringExecutionPlan(
            accepted=True,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=device.device_id,
            command_type=normalized_command_type,
            success=True,
            immediate_completion=duration_sec <= 0.0,
            target_value=float(command.target_value),
            unit=command.unit or device.default_unit,
            duration_sec=duration_sec,
            detail_message=(
                f'Started watering for {float(command.target_value):.1f}'
                f'{command.unit or device.default_unit}.'
            ),
        )

    if normalized_command_type in {'stop_watering', 'hold_watering'}:
        return WateringExecutionPlan(
            accepted=True,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=device.device_id,
            command_type=normalized_command_type,
            success=True,
            immediate_completion=True,
            target_value=0.0,
            unit=device.default_unit,
            duration_sec=0.0,
            detail_message='Watering stopped.' if normalized_command_type == 'stop_watering' else 'Watering hold acknowledged.',
        )

    return WateringExecutionPlan(
        accepted=False,
        command_id=command.command_id,
        zone_id=command.zone_id or device.zone_id,
        device_id=device.device_id,
        command_type=normalized_command_type,
        success=False,
        immediate_completion=True,
        target_value=float(command.target_value),
        unit=command.unit or device.default_unit,
        duration_sec=0.0,
        detail_message=f'Unsupported watering command_type: {normalized_command_type}',
    )


def build_watering_state(
    device: IoTDeviceSpec,
    *,
    state: str,
    current_value: float,
    detail_message: str,
) -> IoTDeviceState:
    message = IoTDeviceState()
    message.device_id = device.device_id
    message.zone_id = device.zone_id
    message.device_type = device.device_type
    message.state = state
    message.current_value = float(current_value)
    message.unit = device.default_unit
    message.is_available = device.is_available
    message.detail_message = detail_message
    return message


def build_watering_result_payload(
    plan: WateringExecutionPlan,
    *,
    success: bool,
    state: str,
    detail_message: str,
    executed_duration_sec: float,
) -> str:
    payload = {
        'command_id': plan.command_id,
        'zone_id': plan.zone_id,
        'device_id': plan.device_id,
        'device_type': 'watering',
        'command_type': plan.command_type,
        'success': bool(success),
        'state': state,
        'target_value': float(plan.target_value),
        'unit': plan.unit,
        'planned_duration_sec': float(plan.duration_sec),
        'executed_duration_sec': float(executed_duration_sec),
        'detail_message': detail_message,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)
