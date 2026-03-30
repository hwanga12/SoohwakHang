from pathlib import Path
import json

from agribot_interfaces.msg import IoTCommand
from agribot_iot.device_mapping import load_iot_device_catalog
from agribot_iot.watering_controller_logic import (
    build_watering_result_payload,
    build_watering_state,
    plan_watering_command,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
IOT_DEVICES = (
    REPO_ROOT
    / 'agribot_ws'
    / 'src'
    / 'agribot_iot'
    / 'config'
    / 'iot_devices.yaml'
)


def test_dispense_water_command_creates_duration_from_flow_rate() -> None:
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_watering']

    command = IoTCommand()
    command.command_id = 'watering-01'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_watering'
    command.device_type = 'watering'
    command.command_type = 'dispense_water'
    command.target_value = 360.0
    command.unit = 'ml'

    plan = plan_watering_command(command, device)

    assert plan.accepted is True
    assert plan.immediate_completion is False
    assert plan.duration_sec == 2.0


def test_stop_watering_completes_immediately_and_reports_payload() -> None:
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_watering']

    command = IoTCommand()
    command.command_id = 'watering-02'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_watering'
    command.device_type = 'watering'
    command.command_type = 'stop_watering'

    plan = plan_watering_command(command, device)
    state = build_watering_state(
        device,
        state='OFF',
        current_value=0.0,
        detail_message='Watering stopped.',
    )
    payload = json.loads(
        build_watering_result_payload(
            plan,
            success=True,
            state='STOPPED',
            detail_message='Watering stopped.',
            executed_duration_sec=0.0,
        )
    )

    assert plan.accepted is True
    assert plan.immediate_completion is True
    assert state.state == 'OFF'
    assert payload['state'] == 'STOPPED'
    assert payload['success'] is True
