# 이 모듈은 IoT 장치 연동 패키지에서 mqtt contract 장치 흐름을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory
from agribot_interfaces.msg import EnvironmentData, IoTCommand, IoTCommandResult, IoTDeviceState
import yaml

from .command_result_contract import command_result_payload_from_message


@dataclass(frozen=True)
class MqttBrokerConfig:
    # mqtt broker 실행 설정을 한 번에 묶어 다루기 위한 클래스를 정의한다.
    host: str
    port: int
    client_id: str
    keepalive_sec: int
    qos: int
    retain_default: bool
    clean_session: bool
    reconnect_min_delay_sec: float
    reconnect_max_delay_sec: float
    publish_retry_count: int
    publish_retry_backoff_sec: float
    offline_queue_dir: str
    offline_queue_max_messages: int


@dataclass(frozen=True)
class RosToMqttRoute:
    # ROS TO mqtt 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    ros_topic: str
    ros_type: str
    mqtt_topic_template: str
    serializer: str
    retain: bool


@dataclass(frozen=True)
class MqttToRosRoute:
    # mqtt TO ROS 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    mqtt_topic: str
    ros_topic: str
    ros_type: str
    deserializer: str


@dataclass(frozen=True)
class MqttBridgeConfig:
    # mqtt 브리지 실행 설정을 한 번에 묶어 다루기 위한 클래스를 정의한다.
    schema_version: int
    broker: MqttBrokerConfig
    ros_to_mqtt: tuple[RosToMqttRoute, ...]
    mqtt_to_ros: tuple[MqttToRosRoute, ...]


def get_default_mqtt_topics_path() -> Path:
    # default mqtt topics 경로를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return Path(get_package_share_directory('agribot_iot')) / 'config' / 'mqtt_topics.yaml'


def _load_yaml(path: Path) -> dict[str, Any]:
    # YAML 데이터를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    with path.open('r', encoding='utf-8') as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f'Expected a mapping at the top level of {path}.')
    return payload


def load_mqtt_bridge_config(path: Path) -> MqttBridgeConfig:
    # mqtt 브리지 설정를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
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
            clean_session=bool(broker_payload.get('clean_session', False)),
            reconnect_min_delay_sec=float(broker_payload.get('reconnect_min_delay_sec', 1.0)),
            reconnect_max_delay_sec=float(broker_payload.get('reconnect_max_delay_sec', 30.0)),
            publish_retry_count=max(0, int(broker_payload.get('publish_retry_count', 3))),
            publish_retry_backoff_sec=max(
                0.0,
                float(broker_payload.get('publish_retry_backoff_sec', 0.5)),
            ),
            offline_queue_dir=str(
                broker_payload.get('offline_queue_dir', '/tmp/agribot_mqtt_offline')
            ),
            offline_queue_max_messages=max(
                1,
                int(broker_payload.get('offline_queue_max_messages', 256)),
            ),
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
    # environment data를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    return {
        'zone_id': message.zone_id,
        'temperature': float(message.temperature),
        'humidity': float(message.humidity),
        'soil_moisture': float(message.soil_moisture),
        'light_level': float(message.light_level),
        'co2_level': float(message.co2_level),
    }


def serialize_iot_command(message: IoTCommand) -> dict[str, Any]:
    # IoT 명령를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
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
    # IoT 장치 상태를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
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


def serialize_iot_command_result(message: IoTCommandResult) -> dict[str, Any]:
    # IoT command result를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    return command_result_payload_from_message(message)


def resolve_mqtt_topic(template: str, message: Any) -> str:
    # 현재 입력 조건을 바탕으로 mqtt topic를 계산하거나 결정한다.
    zone_id = getattr(message, 'zone_id', '')
    device_id = getattr(message, 'device_id', '')
    command_id = getattr(message, 'command_id', '')
    return template.format(
        zone_id=zone_id,
        device_id=device_id,
        command_id=command_id,
    )


def serialize_message(serializer: str, message: Any) -> dict[str, Any]:
    # message를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    serializer_map = {
        'environment_data': serialize_environment_data,
        'iot_command': serialize_iot_command,
        'iot_device_state': serialize_iot_device_state,
        'iot_command_result': serialize_iot_command_result,
    }
    try:
        serializer_fn = serializer_map[serializer]
    except KeyError as exc:
        raise ValueError(f'Unsupported serializer: {serializer}') from exc
    return serializer_fn(message)


def deserialize_iot_command_payload(payload: str | bytes | dict[str, Any]) -> IoTCommand:
    # IoT 명령 payload를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
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
