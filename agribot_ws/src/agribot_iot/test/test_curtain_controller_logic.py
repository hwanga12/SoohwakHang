# 이 테스트는 IoT 장치 연동 패키지의 curtain controller logic 동작을 검증한다.
from pathlib import Path
import json

from agribot_interfaces.msg import IoTCommand
from agribot_iot.curtain_controller_logic import (
    build_curtain_result_payload,
    build_curtain_state,
    classify_curtain_state,
    plan_curtain_command,
)
from agribot_iot.device_mapping import load_iot_device_catalog


REPO_ROOT = Path(__file__).resolve().parents[4]
IOT_DEVICES = (
    REPO_ROOT
    / 'agribot_ws'
    / 'src'
    / 'agribot_iot'
    / 'config'
    / 'iot_devices.yaml'
)


def test_set_curtain_position_translates_percent_closed_to_open_ratio() -> None:
    # SET 커튼 위치 translates percent closed TO open ratio 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_curtain']

    command = IoTCommand()
    command.command_id = 'curtain-01'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_curtain'
    command.device_type = 'curtain'
    command.command_type = 'set_curtain_position'
    command.target_value = 60.0
    command.unit = 'percent_closed'

    plan = plan_curtain_command(
        command,
        device,
        current_opening_ratio=100.0,
        transition_rate_percent_per_sec=40.0,
    )

    assert plan.accepted is True
    assert plan.target_opening_ratio == 40.0
    assert plan.immediate_completion is False
    assert plan.duration_sec == 1.5


def test_open_curtain_completes_immediately_when_already_open() -> None:
    # open 커튼 completes immediately when already open 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_curtain']

    command = IoTCommand()
    command.command_id = 'curtain-02'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_curtain'
    command.device_type = 'curtain'
    command.command_type = 'open_curtain'

    plan = plan_curtain_command(
        command,
        device,
        current_opening_ratio=100.0,
        transition_rate_percent_per_sec=40.0,
    )
    state = build_curtain_state(
        device,
        state=classify_curtain_state(100.0),
        opening_ratio=100.0,
        detail_message=plan.detail_message,
    )
    payload = json.loads(
        build_curtain_result_payload(
            plan,
            success=True,
            state='OPEN',
            detail_message=plan.detail_message,
            executed_duration_sec=0.0,
            opening_ratio=100.0,
        )
    )

    assert plan.accepted is True
    assert plan.immediate_completion is True
    assert state.state == 'OPEN'
    assert payload['state'] == 'OPEN'
    assert payload['opening_ratio'] == 100.0


def test_close_curtain_produces_closed_state() -> None:
    # close 커튼 produces closed 상태 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_curtain']

    command = IoTCommand()
    command.command_id = 'curtain-03'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_curtain'
    command.device_type = 'curtain'
    command.command_type = 'close_curtain'

    plan = plan_curtain_command(
        command,
        device,
        current_opening_ratio=20.0,
        transition_rate_percent_per_sec=40.0,
    )

    assert plan.accepted is True
    assert plan.target_opening_ratio == 0.0
    assert classify_curtain_state(plan.target_opening_ratio) == 'CLOSED'
