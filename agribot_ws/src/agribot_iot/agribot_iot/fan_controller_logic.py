# 이 모듈은 IoT 장치 연동 패키지에서 fan controller logic 장치 흐름을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
import json

from agribot_interfaces.msg import IoTCommand, IoTDeviceState

from .device_mapping import IoTDeviceSpec


@dataclass(frozen=True)
class FanExecutionPlan:
    # 환기팬 execution 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    accepted: bool
    command_id: str
    zone_id: str
    device_id: str
    command_type: str
    success: bool
    immediate_completion: bool
    source_speed_level: int
    target_speed_level: int
    unit: str
    detail_message: str


def plan_fan_command(
    command: IoTCommand,
    device: IoTDeviceSpec,
    *,
    current_speed_level: int,
) -> FanExecutionPlan:
    # 환기팬 명령를 어떤 순서와 조건으로 처리할지 계획한다.
    normalized_command_type = command.command_type.strip().lower()
    normalized_unit = command.unit.strip().lower()

    if command.device_type.strip().lower() != 'fan':
        return FanExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id,
            device_id=command.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            source_speed_level=int(current_speed_level),
            target_speed_level=int(current_speed_level),
            unit='level',
            detail_message='Ignoring non-fan command.',
        )

    if command.device_id and command.device_id != device.device_id:
        return FanExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=command.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            source_speed_level=int(current_speed_level),
            target_speed_level=int(current_speed_level),
            unit='level',
            detail_message=f'Unknown fan device_id: {command.device_id}',
        )

    target_speed_level = _resolve_target_speed_level(
        command_type=normalized_command_type,
        target_value=float(command.target_value),
        unit=normalized_unit,
        device=device,
    )
    if target_speed_level is None:
        return FanExecutionPlan(
            accepted=False,
            command_id=command.command_id,
            zone_id=command.zone_id or device.zone_id,
            device_id=device.device_id,
            command_type=normalized_command_type,
            success=False,
            immediate_completion=True,
            source_speed_level=int(current_speed_level),
            target_speed_level=int(current_speed_level),
            unit='level',
            detail_message=f'Unsupported fan command_type: {normalized_command_type}',
        )

    if target_speed_level == int(current_speed_level):
        detail_message = (
            f'Fan already off.'
            if target_speed_level == 0
            else f'Fan already running at level {target_speed_level}.'
        )
    elif target_speed_level == 0:
        detail_message = 'Fan stopped.'
    else:
        detail_message = f'Fan speed set to level {target_speed_level}.'

    return FanExecutionPlan(
        accepted=True,
        command_id=command.command_id,
        zone_id=command.zone_id or device.zone_id,
        device_id=device.device_id,
        command_type=normalized_command_type,
        success=True,
        immediate_completion=True,
        source_speed_level=int(current_speed_level),
        target_speed_level=int(target_speed_level),
        unit='level',
        detail_message=detail_message,
    )


def build_fan_state(
    device: IoTDeviceSpec,
    *,
    state: str,
    speed_level: int,
    run_duration_sec: float,
    detail_message: str,
) -> IoTDeviceState:
    # 환기팬 상태를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    message = IoTDeviceState()
    message.device_id = device.device_id
    message.zone_id = device.zone_id
    message.device_type = device.device_type
    message.state = state
    message.speed_level = float(max(0, speed_level))
    message.current_value = max(0.0, float(run_duration_sec))
    message.unit = 'sec'
    message.is_available = device.is_available
    message.detail_message = detail_message
    return message


def build_fan_result_payload(
    plan: FanExecutionPlan,
    *,
    success: bool,
    state: str,
    detail_message: str,
    executed_duration_sec: float,
    speed_level: int,
) -> str:
    # 환기팬 결과 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    payload = {
        'command_id': plan.command_id,
        'zone_id': plan.zone_id,
        'device_id': plan.device_id,
        'device_type': 'fan',
        'command_type': plan.command_type,
        'success': bool(success),
        'state': state,
        'source_speed_level': int(plan.source_speed_level),
        'target_value': int(plan.target_speed_level),
        'speed_level': int(max(0, speed_level)),
        'unit': 'level',
        'planned_duration_sec': 0.0,
        'executed_duration_sec': max(0.0, float(executed_duration_sec)),
        'detail_message': detail_message,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def classify_fan_state(speed_level: int) -> str:
    # classify 환기팬 상태 정보를 계산해 반환한다.
    return 'ON' if int(speed_level) > 0 else 'OFF'


def _resolve_target_speed_level(
    *,
    command_type: str,
    target_value: float,
    unit: str,
    device: IoTDeviceSpec,
) -> int | None:
    # 현재 입력 조건을 바탕으로 target speed level를 계산하거나 결정한다.
    if command_type in {'turn_off_fan', 'stop_fan'}:
        return 0
    if command_type == 'turn_on_fan':
        return min(device.max_speed_level, max(1, device.default_speed_level))
    if command_type not in {'set_fan_level', 'set_fan_speed'}:
        return None

    if unit not in {'', 'level', 'speed_level'}:
        return None
    return _clamp_speed_level(target_value, max_speed_level=device.max_speed_level)


def _clamp_speed_level(value: float, *, max_speed_level: int) -> int:
    # speed level 값을 허용 범위로 제한한다.
    rounded = int(round(float(value)))
    return max(0, min(int(max_speed_level), rounded))
