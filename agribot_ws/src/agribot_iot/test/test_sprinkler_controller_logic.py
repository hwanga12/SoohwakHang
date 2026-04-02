# 이 테스트는 IoT 장치 연동 패키지의 sprinkler controller logic 동작을 검증한다.
from pathlib import Path
import json

from agribot_interfaces.msg import IoTCommand
from agribot_iot.device_mapping import load_iot_device_catalog
from agribot_iot.sprinkler_controller_logic import (
    build_sprinkler_result_payload,
    build_sprinkler_state,
    plan_sprinkler_command,
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


def test_spray_pesticide_command_maps_to_red_effect() -> None:
    # spray pesticide 명령 지도 목록 TO RED effect 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['sprinkler_2']

    command = IoTCommand()
    command.command_id = 'sprinkler-01'
    command.zone_id = 'farm_01'
    command.device_id = 'sprinkler_2'
    command.device_type = 'sprinkler'
    command.command_type = 'spray_pesticide'
    command.target_value = 3.0
    command.unit = 'sec'
    command.reason = '병해 치료 payload=effect_color=red,treatment_type=pesticide_spray'

    plan = plan_sprinkler_command(command, device)

    assert plan.accepted is True
    assert plan.effect_color == 'red'
    assert plan.treatment_type == 'pesticide_spray'
    assert plan.duration_sec == 3.0


def test_spray_calcium_command_maps_to_yellow_effect() -> None:
    # spray calcium 명령 지도 목록 TO yellow effect 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['sprinkler_1']

    command = IoTCommand()
    command.command_id = 'sprinkler-02'
    command.zone_id = 'farm_01'
    command.device_id = 'sprinkler_1'
    command.device_type = 'sprinkler'
    command.command_type = 'spray_calcium_solution'
    command.target_value = 2.5
    command.unit = 'sec'

    plan = plan_sprinkler_command(command, device)

    assert plan.accepted is True
    assert plan.effect_color == 'yellow'
    assert plan.treatment_type == 'calcium_solution_spray'


def test_spray_water_command_maps_to_blue_effect() -> None:
    # spray water 명령 지도 목록 TO blue effect 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['sprinkler_0']

    command = IoTCommand()
    command.command_id = 'sprinkler-04'
    command.zone_id = 'farm_01'
    command.device_id = 'sprinkler_0'
    command.device_type = 'sprinkler'
    command.command_type = 'spray_water'
    command.target_value = 3.0
    command.unit = 'sec'

    plan = plan_sprinkler_command(command, device)

    assert plan.accepted is True
    assert plan.effect_color == 'blue'
    assert plan.treatment_type == 'water_spray'


def test_spray_nutrient_command_maps_to_green_effect() -> None:
    # spray 영양제 명령 지도 목록 TO green effect 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['sprinkler_3']

    command = IoTCommand()
    command.command_id = 'sprinkler-05'
    command.zone_id = 'farm_01'
    command.device_id = 'sprinkler_3'
    command.device_type = 'sprinkler'
    command.command_type = 'spray_nutrient_solution'
    command.target_value = 2.5
    command.unit = 'sec'

    plan = plan_sprinkler_command(command, device)

    assert plan.accepted is True
    assert plan.effect_color == 'green'
    assert plan.treatment_type == 'nutrient_solution_spray'


def test_stop_spray_completes_immediately_and_reports_payload() -> None:
    # stop spray completes immediately AND reports payload 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['sprinkler_0']

    command = IoTCommand()
    command.command_id = 'sprinkler-03'
    command.zone_id = 'farm_01'
    command.device_id = 'sprinkler_0'
    command.device_type = 'sprinkler'
    command.command_type = 'stop_spray'
    command.reason = '정지 payload=effect_color=red,treatment_type=pesticide_spray'

    plan = plan_sprinkler_command(command, device)
    state = build_sprinkler_state(
        device,
        state='IDLE',
        current_value=0.0,
        detail_message=plan.detail_message,
    )
    payload = json.loads(
        build_sprinkler_result_payload(
            plan,
            success=True,
            state='STOPPED',
            detail_message='Sprinkler spray stop acknowledged.',
            executed_duration_sec=0.0,
        )
    )

    assert plan.accepted is True
    assert plan.immediate_completion is True
    assert state.device_type == 'sprinkler'
    assert payload['state'] == 'STOPPED'
    assert payload['effect_color'] == 'red'
