from pathlib import Path

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


def test_iot_device_catalog_uses_shared_zone_device_names() -> None:
    catalog = load_iot_device_catalog(IOT_DEVICES)

    assert catalog.default_zone_id == 'farm_01'
    assert set(catalog.zones) == {'farm_01'}
    assert set(catalog.devices) == {
        'farm_01_watering',
        'farm_01_curtain',
        'farm_01_fan',
        'farm_01_nutrient',
        'sprinkler_0',
        'sprinkler_1',
        'sprinkler_2',
        'sprinkler_3',
    }
    assert catalog.primary_device('farm_01', 'watering').device_id == 'farm_01_watering'
    assert catalog.primary_device('farm_01', 'sprinkler').device_id == 'sprinkler_0'
