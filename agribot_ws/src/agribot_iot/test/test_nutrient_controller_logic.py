from pathlib import Path
import json

from agribot_interfaces.msg import IoTCommand
from agribot_iot.device_mapping import load_iot_device_catalog
from agribot_iot.nutrient_controller_logic import (
    build_nutrient_result_payload,
    build_nutrient_state,
    plan_nutrient_command,
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


def test_apply_nutrient_recipe_extracts_payload_and_duration() -> None:
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_nutrient']

    command = IoTCommand()
    command.command_id = 'nutrient-01'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_nutrient'
    command.device_type = 'nutrient'
    command.command_type = 'apply_nutrient_recipe'
    command.target_value = 180.0
    command.unit = 'ml'
    command.requested_by = 'operator:test'
    command.reason = '칼슘 보강제 권장 payload=nutrient_type=calcium_boost'

    plan = plan_nutrient_command(command, device)

    assert plan.accepted is True
    assert plan.nutrient_type == 'calcium_boost'
    assert plan.requested_by == 'operator:test'
    assert plan.duration_sec == 2.0


def test_apply_nutrient_recipe_rejects_non_positive_target() -> None:
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_nutrient']

    command = IoTCommand()
    command.command_id = 'nutrient-02'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_nutrient'
    command.device_type = 'nutrient'
    command.command_type = 'apply_nutrient_recipe'
    command.target_value = 0.0
    command.unit = 'ml'

    plan = plan_nutrient_command(command, device)

    assert plan.accepted is False
    assert 'greater than 0' in plan.detail_message


def test_nutrient_result_payload_contains_recipe_and_requester() -> None:
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_nutrient']

    command = IoTCommand()
    command.command_id = 'nutrient-03'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_nutrient'
    command.device_type = 'nutrient'
    command.command_type = 'apply_nutrient_recipe'
    command.target_value = 250.0
    command.unit = 'ml'
    command.requested_by = 'dashboard:user'
    command.reason = '승인 완료 payload=nutrient_type=calcium_boost'

    plan = plan_nutrient_command(command, device)
    state = build_nutrient_state(
        device,
        state='DISPENSING',
        current_value=250.0,
        detail_message=plan.detail_message,
    )
    payload = json.loads(
        build_nutrient_result_payload(
            plan,
            success=True,
            state='COMPLETED',
            detail_message='Nutrient dispensing completed successfully.',
            executed_duration_sec=2.8,
        )
    )

    assert state.device_type == 'nutrient'
    assert state.state == 'DISPENSING'
    assert payload['requested_by'] == 'dashboard:user'
    assert payload['nutrient_type'] == 'calcium_boost'
    assert payload['executed_duration_sec'] == 2.8
