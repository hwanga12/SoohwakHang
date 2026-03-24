from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory
from agribot_interfaces.msg import EnvironmentData, IoTCommand, IoTDeviceState
from std_msgs.msg import String
import yaml


@dataclass(frozen=True)
class MqttBrokerConfig:
    host: str
    port: int
    client_id: str
    keepalive_sec: int
    qos: int
    retain_default: bool


@dataclass(frozen=True)
class RosToMqttRoute:
    ros_topic: str
    ros_type: str
    mqtt_topic_template: str
    serializer: str
    retain: bool


@dataclass(frozen=True)
class MqttToRosRoute:
    mqtt_topic: str
    ros_topic: str
    ros_type: str
    deserializer: str


@dataclass(frozen=True)
class MqttBridgeConfig:
    schema_version: int
    broker: MqttBrokerConfig
    ros_to_mqtt: tuple[RosToMqttRoute, ...]
    mqtt_to_ros: tuple[MqttToRosRoute, ...]


def get_default_mqtt_topics_path() -> Path:
    return Path(get_package_share_directory('agribot_iot')) / 'config' / 'mqtt_topics.yaml'


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f'Expected a mapping at the top level of {path}.')
    return payload


def load_mqtt_bridge_config(path: Path) -> MqttBridgeConfig:
    payload = _load_yaml(path)
    broker_payload = dict(payload['broker'])
    return MqttBridgeConfig(
        schema_version=int(payload.get('schema_version', 1)),
        broker=MqttBrokerConfig(
            host=str(broker_payload.get('host', 'localhost')),
            port=int(broker_payload.get('port', 1883)),
            client_id=str(broker_payload.get('client_id', 'agribot_iot_bridge')),
            keepalive_sec=int(broker_payload.get('keepalive_sec', 30)),
            qos=int(broker_payload.get('qos', 1)),
            retain_default=bool(broker_payload.get('retain_default', False)),
        ),
        ros_to_mqtt=tuple(
            RosToMqttRoute(
                ros_topic=str(route['ros_topic']),
                ros_type=str(route['ros_type']),
                mqtt_topic_template=str(route['mqtt_topic_template']),
                serializer=str(route['serializer']),
                retain=bool(route.get('retain', False)),
            )
            for route in payload.get('ros_to_mqtt', [])
        ),
        mqtt_to_ros=tuple(
            MqttToRosRoute(
                mqtt_topic=str(route['mqtt_topic']),
                ros_topic=str(route['ros_topic']),
                ros_type=str(route['ros_type']),
                deserializer=str(route['deserializer']),
            )
            for route in payload.get('mqtt_to_ros', [])
        ),
    )


def serialize_environment_data(message: EnvironmentData) -> dict[str, Any]:
    return {
        'zone_id': message.zone_id,
        'temperature': float(message.temperature),
        'humidity': float(message.humidity),
        'soil_moisture': float(message.soil_moisture),
        'light_level': float(message.light_level),
        'co2_level': float(message.co2_level),
    }


def serialize_iot_command(message: IoTCommand) -> dict[str, Any]:
    return {
        'stamp': {
            'sec': int(message.header.stamp.sec),
            'nanosec': int(message.header.stamp.nanosec),
        },
        'frame_id': message.header.frame_id,
        'command_id': message.command_id,
        'zone_id': message.zone_id,
        'device_id': message.device_id,
        'device_type': message.device_type,
        'command_type': message.command_type,
        'target_value': float(message.target_value),
        'unit': message.unit,
        'requires_approval': bool(message.requires_approval),
        'auto_execute': bool(message.auto_execute),
        'requested_by': message.requested_by,
        'reason': message.reason,
    }


def serialize_iot_device_state(message: IoTDeviceState) -> dict[str, Any]:
    return {
        'stamp': {
            'sec': int(message.header.stamp.sec),
            'nanosec': int(message.header.stamp.nanosec),
        },
        'frame_id': message.header.frame_id,
        'device_id': message.device_id,
        'zone_id': message.zone_id,
        'device_type': message.device_type,
        'state': message.state,
        'opening_ratio': float(message.opening_ratio),
        'speed_level': float(message.speed_level),
        'current_value': float(message.current_value),
        'unit': message.unit,
        'is_available': bool(message.is_available),
        'detail_message': message.detail_message,
    }


def serialize_std_string_json(message: String) -> dict[str, Any]:
    payload = message.data.strip()
    if not payload:
        return {}
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return {'data': payload}
    if isinstance(decoded, dict):
        return decoded
    return {'data': decoded}


def resolve_mqtt_topic(template: str, message: Any) -> str:
    zone_id = getattr(message, 'zone_id', '')
    device_id = getattr(message, 'device_id', '')
    command_id = getattr(message, 'command_id', '')
    return template.format(
        zone_id=zone_id,
        device_id=device_id,
        command_id=command_id,
    )


def serialize_message(serializer: str, message: Any) -> dict[str, Any]:
    serializer_map = {
        'environment_data': serialize_environment_data,
        'iot_command': serialize_iot_command,
        'iot_device_state': serialize_iot_device_state,
        'raw_json': serialize_std_string_json,
    }
    try:
        serializer_fn = serializer_map[serializer]
    except KeyError as exc:
        raise ValueError(f'Unsupported serializer: {serializer}') from exc
    return serializer_fn(message)


def deserialize_iot_command_payload(payload: str | bytes | dict[str, Any]) -> IoTCommand:
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError('IoT command payload must decode to a JSON object.')

    message = IoTCommand()
    message.command_id = str(payload.get('command_id', ''))
    message.zone_id = str(payload.get('zone_id', ''))
    message.device_id = str(payload.get('device_id', ''))
    message.device_type = str(payload.get('device_type', ''))
    message.command_type = str(payload.get('command_type', ''))
    message.target_value = float(payload.get('target_value', 0.0))
    message.unit = str(payload.get('unit', ''))
    message.requires_approval = bool(payload.get('requires_approval', False))
    message.auto_execute = bool(payload.get('auto_execute', False))
    message.requested_by = str(payload.get('requested_by', 'mqtt_bridge'))
    message.reason = str(payload.get('reason', ''))
    return message
