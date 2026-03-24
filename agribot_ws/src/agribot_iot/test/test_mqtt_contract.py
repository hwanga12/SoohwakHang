from pathlib import Path

from agribot_interfaces.msg import EnvironmentData, IoTCommand, IoTDeviceState
from agribot_iot.mqtt_contract import (
    deserialize_iot_command_payload,
    load_mqtt_bridge_config,
    resolve_mqtt_topic,
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
    config = load_mqtt_bridge_config(MQTT_TOPICS)

    assert config.broker.host == 'localhost'
    assert config.broker.port == 1883
    assert len(config.ros_to_mqtt) == 3
    assert len(config.mqtt_to_ros) == 1
    assert config.mqtt_to_ros[0].mqtt_topic == 'agribot/commands/actuation'


def test_serializers_match_expected_json_shape() -> None:
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
