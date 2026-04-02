# Typed IoT command result contract helpers shared across controllers and MQTT bridge.
from __future__ import annotations

import json
from typing import Any

from agribot_interfaces.msg import IoTCommandResult


def _normalize_string(value: Any) -> str:
    # Normalize arbitrary values into a transport-safe string.
    return str(value).strip() if value is not None else ''


def command_result_message_from_payload(
    payload: str | bytes | dict[str, Any],
    *,
    stamp=None,
    frame_id: str = 'map',
) -> IoTCommandResult:
    # Build a typed command result message from JSON payload text or a decoded mapping.
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError('IoT command result payload must decode to a JSON object.')

    message = IoTCommandResult()
    if stamp is not None:
        message.header.stamp = stamp
    message.header.frame_id = frame_id
    message.command_id = _normalize_string(payload.get('command_id'))
    message.zone_id = _normalize_string(payload.get('zone_id'))
    message.device_id = _normalize_string(payload.get('device_id'))
    message.device_type = _normalize_string(payload.get('device_type'))
    message.command_type = _normalize_string(payload.get('command_type'))
    message.success = bool(payload.get('success'))
    message.state = _normalize_string(payload.get('state'))
    message.target_value = float(payload.get('target_value', 0.0) or 0.0)
    message.unit = _normalize_string(payload.get('unit'))
    message.planned_duration_sec = float(payload.get('planned_duration_sec', 0.0) or 0.0)
    message.executed_duration_sec = float(payload.get('executed_duration_sec', 0.0) or 0.0)
    message.detail_message = _normalize_string(payload.get('detail_message'))
    message.requested_by = _normalize_string(payload.get('requested_by'))
    message.treatment_type = _normalize_string(payload.get('treatment_type'))
    message.effect_color = _normalize_string(payload.get('effect_color'))
    message.nutrient_type = _normalize_string(payload.get('nutrient_type'))
    message.speed_level = float(payload.get('speed_level', 0.0) or 0.0)
    message.opening_ratio = float(payload.get('opening_ratio', 0.0) or 0.0)
    message.source_speed_level = float(payload.get('source_speed_level', 0.0) or 0.0)
    message.source_opening_ratio = float(payload.get('source_opening_ratio', 0.0) or 0.0)
    return message


def command_result_payload_from_message(message: IoTCommandResult) -> dict[str, Any]:
    # Convert a typed command result message into the MQTT/backend JSON contract.
    payload = {
        'command_id': _normalize_string(message.command_id),
        'zone_id': _normalize_string(message.zone_id),
        'device_id': _normalize_string(message.device_id),
        'device_type': _normalize_string(message.device_type),
        'command_type': _normalize_string(message.command_type),
        'success': bool(message.success),
        'state': _normalize_string(message.state),
        'target_value': float(message.target_value),
        'unit': _normalize_string(message.unit),
        'planned_duration_sec': float(message.planned_duration_sec),
        'executed_duration_sec': float(message.executed_duration_sec),
        'detail_message': _normalize_string(message.detail_message),
    }
    optional_fields = {
        'requested_by': _normalize_string(message.requested_by),
        'treatment_type': _normalize_string(message.treatment_type),
        'effect_color': _normalize_string(message.effect_color),
        'nutrient_type': _normalize_string(message.nutrient_type),
    }
    numeric_optional_fields = {
        'speed_level': float(message.speed_level),
        'opening_ratio': float(message.opening_ratio),
        'source_speed_level': float(message.source_speed_level),
        'source_opening_ratio': float(message.source_opening_ratio),
    }
    payload.update({key: value for key, value in optional_fields.items() if value})
    payload.update(
        {key: value for key, value in numeric_optional_fields.items() if abs(value) > 1.0e-9}
    )
    return payload
