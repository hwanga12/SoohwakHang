from __future__ import annotations

from dataclasses import dataclass
import json

from agribot_interfaces.msg import IoTCommand, IoTDeviceState

from .device_mapping import IoTDeviceSpec


@dataclass(frozen=True)
class CurtainExecutionPlan:
    accepted: bool
    command_id: str
    zone_id: str
    device_id: str
    command_type: str
    success: bool
    immediate_completion: bool
    source_opening_ratio: float
    target_opening_ratio: float
    unit: str
    duration_sec: float
    detail_message: str


def plan_curtain_command(
    command: IoTCommand,
    device: IoTDeviceSpec,
    *,
    current_opening_ratio: float,
    transition_rate_percent_per_sec: float,
) -> CurtainExecutionPlan:
    normalized_command_type = command.command_type.strip().lower()
    normalized_unit = command.unit.strip().lower()

    if command.device_type.strip() != 'curtain':
        return CurtainExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id,
            device_id=command.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            source_opening_ratio=float(current_opening_ratio),
            target_opening_ratio=float(current_opening_ratio),
            unit='percent',
            duration_sec=0.0,
            detail_message='Ignoring non-curtain command.',
        )

    if command.device_id and command.device_id != device.device_id:
        return CurtainExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=command.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            source_opening_ratio=float(current_opening_ratio),
            target_opening_ratio=float(current_opening_ratio),
            unit='percent',
            duration_sec=0.0,
            detail_message=f'Unknown curtain device_id: {command.device_id}',
        )

    target_opening_ratio = _resolve_target_opening_ratio(
        command_type=normalized_command_type,
        target_value=float(command.target_value),
        unit=normalized_unit,
        default_unit=device.default_unit,
        current_opening_ratio=float(current_opening_ratio),
    )
    if target_opening_ratio is None:
        return CurtainExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=device.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            source_opening_ratio=float(current_opening_ratio),
            target_opening_ratio=float(current_opening_ratio),
            unit='percent',
            duration_sec=0.0,
            detail_message=f'Unsupported curtain command_type: {normalized_command_type}',
        )

    duration_sec = 0.0
    if transition_rate_percent_per_sec > 0.0:
        duration_sec = abs(target_opening_ratio - float(current_opening_ratio)) / transition_rate_percent_per_sec
    immediate_completion = duration_sec <= 0.0 or abs(target_opening_ratio - float(current_opening_ratio)) < 1e-3

    if immediate_completion:
        detail_message = (
            f'Curtain already at {target_opening_ratio:.1f}% open.'
            if abs(target_opening_ratio - float(current_opening_ratio)) < 1e-3
            else f'Curtain moved immediately to {target_opening_ratio:.1f}% open.'
        )
    else:
        detail_message = (
            f'Curtain moving from {float(current_opening_ratio):.1f}% open '
            f'to {target_opening_ratio:.1f}% open.'
        )

    return CurtainExecutionPlan(
        accepted=True,
        command_id=command.command_id,
        zone_id=command.zone_id or device.zone_id,
        device_id=device.device_id,
        command_type=normalized_command_type,
        success=True,
        immediate_completion=immediate_completion,
        source_opening_ratio=float(current_opening_ratio),
        target_opening_ratio=target_opening_ratio,
        unit='percent',
        duration_sec=max(0.0, duration_sec),
        detail_message=detail_message,
    )


def classify_curtain_state(
    opening_ratio: float,
    *,
    target_opening_ratio: float | None = None,
) -> str:
    opening_ratio = _clamp_percent(opening_ratio)
    if target_opening_ratio is not None:
        target_opening_ratio = _clamp_percent(target_opening_ratio)
        if target_opening_ratio > opening_ratio + 1e-3:
            return 'OPENING'
        if target_opening_ratio < opening_ratio - 1e-3:
            return 'CLOSING'
    if opening_ratio >= 99.5:
        return 'OPEN'
    if opening_ratio <= 0.5:
        return 'CLOSED'
    return 'PARTIAL_OPEN'


def build_curtain_state(
    device: IoTDeviceSpec,
    *,
    state: str,
    opening_ratio: float,
    detail_message: str,
) -> IoTDeviceState:
    message = IoTDeviceState()
    message.device_id = device.device_id
    message.zone_id = device.zone_id
    message.device_type = device.device_type
    message.state = state
    message.opening_ratio = _clamp_percent(opening_ratio)
    message.current_value = message.opening_ratio
    message.unit = 'percent'
    message.is_available = device.is_available
    message.detail_message = detail_message
    return message


def build_curtain_result_payload(
    plan: CurtainExecutionPlan,
    *,
    success: bool,
    state: str,
    detail_message: str,
    executed_duration_sec: float,
    opening_ratio: float,
) -> str:
    payload = {
        'command_id': plan.command_id,
        'zone_id': plan.zone_id,
        'device_id': plan.device_id,
        'device_type': 'curtain',
        'command_type': plan.command_type,
        'success': bool(success),
        'state': state,
        'source_opening_ratio': float(plan.source_opening_ratio),
        'target_value': float(plan.target_opening_ratio),
        'opening_ratio': _clamp_percent(opening_ratio),
        'unit': 'percent',
        'planned_duration_sec': float(plan.duration_sec),
        'executed_duration_sec': float(executed_duration_sec),
        'detail_message': detail_message,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def _resolve_target_opening_ratio(
    *,
    command_type: str,
    target_value: float,
    unit: str,
    default_unit: str,
    current_opening_ratio: float,
) -> float | None:
    effective_unit = unit or default_unit.strip().lower()
    if command_type == 'open_curtain':
        return 100.0
    if command_type == 'close_curtain':
        return 0.0
    if command_type != 'set_curtain_position':
        return None

    if effective_unit in {'percent_closed', 'closed_percent'}:
        return _clamp_percent(100.0 - target_value)
    if effective_unit in {'percent', 'percent_open', 'opening_ratio', ''}:
        return _clamp_percent(target_value)
    if effective_unit == 'delta_percent':
        return _clamp_percent(current_opening_ratio + target_value)
    return None


def _clamp_percent(value: float) -> float:
    return max(0.0, min(100.0, float(value)))
