# 이 테스트는 IoT 장치 연동 패키지의 fan controller logic 동작을 검증한다.
from pathlib import Path
import json

from agribot_interfaces.msg import IoTCommand
from agribot_iot.device_mapping import load_iot_device_catalog
from agribot_iot.fan_controller_logic import (
    build_fan_result_payload,
    build_fan_state,
    classify_fan_state,
    plan_fan_command,
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


def test_set_fan_level_uses_level_target() -> None:
    # SET 환기팬 level uses level target 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_fan']

    command = IoTCommand()
    command.command_id = 'fan-01'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_fan'
    command.device_type = 'fan'
    command.command_type = 'set_fan_level'
    command.target_value = 3.0
    command.unit = 'level'

    plan = plan_fan_command(command, device, current_speed_level=0)

    assert plan.accepted is True
    assert plan.target_speed_level == 3
    assert plan.detail_message == 'Fan speed set to level 3.'


def test_turn_on_fan_uses_default_speed_level() -> None:
    # turn ON 환기팬 uses default speed level 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_fan']

    command = IoTCommand()
    command.command_id = 'fan-02'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_fan'
    command.device_type = 'fan'
    command.command_type = 'turn_on_fan'

    plan = plan_fan_command(command, device, current_speed_level=0)

    assert plan.accepted is True
    assert plan.target_speed_level == device.default_speed_level


def test_turn_off_fan_creates_off_state_and_result_payload() -> None:
    # turn OFF 환기팬 creates OFF 상태 AND 결과 payload 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    device = catalog.devices['farm_01_fan']

    command = IoTCommand()
    command.command_id = 'fan-03'
    command.zone_id = 'farm_01'
    command.device_id = 'farm_01_fan'
    command.device_type = 'fan'
    command.command_type = 'turn_off_fan'

    plan = plan_fan_command(command, device, current_speed_level=2)
    state = build_fan_state(
        device,
        state=classify_fan_state(0),
        speed_level=0,
        run_duration_sec=4.2,
        detail_message='Fan stopped after 4.2s of runtime.',
    )
    payload = json.loads(
        build_fan_result_payload(
            plan,
            success=True,
            state='STOPPED',
            detail_message='Fan stopped after 4.2s of runtime.',
            executed_duration_sec=4.2,
            speed_level=0,
        )
    )

    assert plan.accepted is True
    assert plan.target_speed_level == 0
    assert state.state == 'OFF'
    assert state.unit == 'sec'
    assert payload['executed_duration_sec'] == 4.2
    assert payload['speed_level'] == 0
