# 이 테스트는 IoT 장치 연동 패키지의 mqtt contract 동작을 검증한다.
from pathlib import Path
import json

from agribot_interfaces.msg import EnvironmentData, IoTCommand, IoTDeviceState
from agribot_iot.mqtt_contract import (
    deserialize_iot_command_payload,
    load_mqtt_bridge_config,
    resolve_mqtt_topic,
    serialize_message,
    serialize_environment_data,
    serialize_iot_command,
    serialize_iot_device_state,
)
from std_msgs.msg import String


REPO_ROOT = Path(__file__).resolve().parents[4]
MQTT_TOPICS = (
    REPO_ROOT
    / 'agribot_ws'
    / 'src'
    / 'agribot_iot'
    / 'config'
    / 'mqtt_topics.yaml'
)


def test_load_mqtt_bridge_config_contains_expected_routes() -> None:
    # load mqtt 브리지 설정 contains expected 경로 목록 동작과 회귀 여부를 검증한다.
    config = load_mqtt_bridge_config(MQTT_TOPICS)

    assert config.broker.host == 'localhost'
    assert config.broker.port == 1883
    assert len(config.ros_to_mqtt) == 3
    assert len(config.mqtt_to_ros) == 1
    assert config.mqtt_to_ros[0].mqtt_topic == 'agribot/commands/actuation'
    device_state_route = next(route for route in config.ros_to_mqtt if route.ros_topic == '/iot/device_state')
    command_result_route = next(route for route in config.ros_to_mqtt if route.ros_topic == '/iot/command_result')

    assert device_state_route.serializer == 'iot_device_state'
    assert device_state_route.retain is True
    assert command_result_route.serializer == 'raw_json'
    assert command_result_route.retain is False


def test_serializers_match_expected_json_shape() -> None:
    # serializers match expected JSON 데이터 shape 동작과 회귀 여부를 검증한다.
    environment = EnvironmentData()
    environment.zone_id = 'farm_01'
    environment.temperature = 24.5
    environment.humidity = 60.0
    environment.soil_moisture = 33.0
    environment.light_level = 15000.0
    environment.co2_level = 510.0

    command = IoTCommand()
    command.command_id = 'command-01'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_watering'
    command.device_type = 'watering'
    command.command_type = 'dispense_water'
    command.target_value = 900.0
    command.unit = 'ml'
    command.auto_execute = True

    state = IoTDeviceState()
    state.device_id = 'farm_01_watering'
    state.zone_id = 'farm_01'
    state.device_type = 'watering'
    state.state = 'ON'
    state.current_value = 900.0
    state.unit = 'ml'
    state.is_available = True

    assert serialize_environment_data(environment)['zone_id'] == 'farm_01'
    assert serialize_iot_command(command)['device_id'] == 'farm_01_watering'
    assert serialize_iot_device_state(state)['state'] == 'ON'
    assert resolve_mqtt_topic('agribot/environment/{zone_id}', environment) == 'agribot/environment/farm_01'


def test_deserialize_iot_command_payload_rebuilds_message() -> None:
    # deserialize IoT 명령 payload rebuilds message 동작과 회귀 여부를 검증한다.
    payload = String()
    payload.data = (
        '{"command_id":"command-02","zone_id":"farm_01","device_id":"farm_01_watering",'
        '"device_type":"watering","command_type":"dispense_water","target_value":450.0,'
        '"unit":"ml","requested_by":"backend:test"}'
    )

    message = deserialize_iot_command_payload(payload.data)

    assert message.command_id == 'command-02'
    assert message.zone_id == 'farm_01'
    assert message.device_id == 'farm_01_watering'
    assert message.command_type == 'dispense_water'
    assert message.target_value == 450.0


def test_raw_json_serializer_keeps_command_result_payload_fields() -> None:
    # RAW JSON 데이터 serializer keeps 명령 결과 payload fields 동작과 회귀 여부를 검증한다.
    payload = String()
    payload.data = json.dumps(
        {
            'command_id': 'result-01',
            'zone_id': 'farm_01',
            'device_id': 'farm_01_nutrient',
            'device_type': 'nutrient',
            'command_type': 'apply_nutrient_recipe',
            'state': 'COMPLETED',
            'success': True,
            'nutrient_type': 'calcium_boost',
            'requested_by': 'dashboard:user',
        },
        ensure_ascii=True,
        sort_keys=True,
    )

    serialized = serialize_message('raw_json', payload)

    assert serialized['device_type'] == 'nutrient'
    assert serialized['nutrient_type'] == 'calcium_boost'
    assert serialized['requested_by'] == 'dashboard:user'
