# 이 테스트는 IoT 장치 연동 패키지의 environment sensor profile 동작을 검증한다.
from pathlib import Path

from agribot_iot.device_mapping import load_iot_device_catalog
from agribot_iot.environment_sensor_profile import generate_environment_sample


REPO_ROOT = Path(__file__).resolve().parents[4]
IOT_DEVICES = (
    REPO_ROOT
    / 'agribot_ws'
    / 'src'
    / 'agribot_iot'
    / 'config'
    / 'iot_devices.yaml'
)


def test_environment_sensor_profile_generates_bounded_values() -> None:
    # environment sensor 프로필 generates bounded values 동작과 회귀 여부를 검증한다.
    catalog = load_iot_device_catalog(IOT_DEVICES)
    zone = catalog.zones['farm_01']

    sample = generate_environment_sample('farm_01', zone.sensor_profile, elapsed_sec=45.0)

    assert sample.zone_id == 'farm_01'
    assert 19.0 <= sample.temperature <= 30.0
    assert 45.0 <= sample.humidity <= 80.0
    assert 20.0 <= sample.soil_moisture <= 55.0
    assert 8000.0 <= sample.light_level <= 24000.0
    assert 420.0 <= sample.co2_level <= 700.0
