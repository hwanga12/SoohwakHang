# 이 모듈은 IoT 장치 연동 패키지에서 device mapping 장치 흐름을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory
import yaml


@dataclass(frozen=True)
class SensorWaveSpec:
    # sensor wave 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    base: float
    amplitude: float
    period_sec: float
    minimum: float
    maximum: float


@dataclass(frozen=True)
class ZoneSensorProfile:
    # 구역 sensor 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    publish_hz: float
    phase_offset_sec: float
    temperature: SensorWaveSpec
    humidity: SensorWaveSpec
    soil_moisture: SensorWaveSpec
    light_level: SensorWaveSpec
    co2_level: SensorWaveSpec


@dataclass(frozen=True)
class IoTDeviceSpec:
    # IO T 장치 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    device_id: str
    zone_id: str
    device_type: str
    display_name: str
    command_topic: str
    state_topic: str
    result_topic: str
    mqtt_command_topic: str
    mqtt_state_topic: str
    mqtt_result_topic: str
    supported_commands: tuple[str, ...]
    default_unit: str
    is_available: bool
    flow_rate_per_sec: float
    default_speed_level: int
    max_speed_level: int


@dataclass(frozen=True)
class IoTZoneSpec:
    # IO T 구역 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    zone_id: str
    display_name: str
    mqtt_namespace: str
    sensor_profile: ZoneSensorProfile
    devices: dict[str, IoTDeviceSpec]


@dataclass(frozen=True)
class IoTDeviceCatalog:
    # IO T 장치 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    schema_version: int
    default_zone_id: str
    frame_id: str
    zones: dict[str, IoTZoneSpec]
    devices: dict[str, IoTDeviceSpec]

    def zone_devices(self, zone_id: str) -> tuple[IoTDeviceSpec, ...]:
        # 구역 장치 정보를 계산해 반환한다.
        zone = self.zones[zone_id]
        return tuple(zone.devices.values())

    def primary_device(self, zone_id: str, device_type: str) -> IoTDeviceSpec:
        # primary 장치 정보를 계산해 반환한다.
        zone = self.zones[zone_id]
        for device in zone.devices.values():
            if device.device_type == device_type:
                return device
        raise KeyError(f'No {device_type} device mapped for zone {zone_id}.')


def get_default_iot_devices_path() -> Path:
    # default IoT 장치 목록 경로를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return Path(get_package_share_directory('agribot_iot')) / 'config' / 'iot_devices.yaml'


def _load_yaml(path: Path) -> dict[str, Any]:
    # YAML 데이터를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    with path.open('r', encoding='utf-8') as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f'Expected a mapping at the top level of {path}.')
    return payload


def _require_float(payload: dict[str, Any], key: str, context: str) -> float:
    # require float 정보를 계산해 반환한다.
    try:
        return float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f'Invalid float field {key!r} in {context}.') from exc


def _load_wave_spec(payload: dict[str, Any], *, context: str) -> SensorWaveSpec:
    # wave spec를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return SensorWaveSpec(
        base=_require_float(payload, 'base', context),
        amplitude=_require_float(payload, 'amplitude', context),
        period_sec=max(1.0, _require_float(payload, 'period_sec', context)),
        minimum=_require_float(payload, 'minimum', context),
        maximum=_require_float(payload, 'maximum', context),
    )


def _load_sensor_profile(payload: dict[str, Any], *, context: str) -> ZoneSensorProfile:
    # sensor 프로필를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return ZoneSensorProfile(
        publish_hz=max(0.1, _require_float(payload, 'publish_hz', context)),
        phase_offset_sec=float(payload.get('phase_offset_sec', 0.0)),
        temperature=_load_wave_spec(dict(payload['temperature']), context=f'{context}.temperature'),
        humidity=_load_wave_spec(dict(payload['humidity']), context=f'{context}.humidity'),
        soil_moisture=_load_wave_spec(
            dict(payload['soil_moisture']),
            context=f'{context}.soil_moisture',
        ),
        light_level=_load_wave_spec(dict(payload['light_level']), context=f'{context}.light_level'),
        co2_level=_load_wave_spec(dict(payload['co2_level']), context=f'{context}.co2_level'),
    )


def _load_device_spec(payload: dict[str, Any], *, zone_id: str, context: str) -> IoTDeviceSpec:
    # 장치 spec를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    capabilities = payload.get('capabilities', {})
    if not isinstance(capabilities, dict):
        raise ValueError(f'capabilities must be a mapping in {context}.')
    supported_commands = tuple(str(item).strip() for item in capabilities.get('supported_commands', []))

    return IoTDeviceSpec(
        device_id=str(payload['device_id']),
        zone_id=zone_id,
        device_type=str(payload['device_type']),
        display_name=str(payload['display_name']),
        command_topic=str(payload['command_topic']),
        state_topic=str(payload['state_topic']),
        result_topic=str(payload['result_topic']),
        mqtt_command_topic=str(payload['mqtt_command_topic']),
        mqtt_state_topic=str(payload['mqtt_state_topic']),
        mqtt_result_topic=str(payload['mqtt_result_topic']),
        supported_commands=supported_commands,
        default_unit=str(capabilities.get('default_unit', '')),
        is_available=bool(payload.get('is_available', True)),
        flow_rate_per_sec=float(capabilities.get('flow_rate_per_sec', 0.0)),
        default_speed_level=max(0, int(capabilities.get('default_speed_level', 1))),
        max_speed_level=max(1, int(capabilities.get('max_speed_level', 3))),
    )


def load_iot_device_catalog(path: Path) -> IoTDeviceCatalog:
    # IoT 장치 카탈로그를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    payload = _load_yaml(path)
    zones: dict[str, IoTZoneSpec] = {}
    devices: dict[str, IoTDeviceSpec] = {}

    for index, zone_payload in enumerate(payload.get('zones', [])):
        if not isinstance(zone_payload, dict):
            raise ValueError(f'zones[{index}] must be a mapping.')
        zone_id = str(zone_payload['zone_id'])
        if zone_id in zones:
            raise ValueError(f'Duplicate zone_id in IoT catalog: {zone_id}')

        loaded_devices: dict[str, IoTDeviceSpec] = {}
        for device_index, device_payload in enumerate(zone_payload.get('devices', [])):
            if not isinstance(device_payload, dict):
                raise ValueError(f'devices[{device_index}] in zone {zone_id} must be a mapping.')
            context = f'zones[{zone_id}].devices[{device_index}]'
            device = _load_device_spec(device_payload, zone_id=zone_id, context=context)
            if device.device_id in devices:
                raise ValueError(f'Duplicate device_id in IoT catalog: {device.device_id}')
            devices[device.device_id] = device
            loaded_devices[device.device_id] = device

        zones[zone_id] = IoTZoneSpec(
            zone_id=zone_id,
            display_name=str(zone_payload['display_name']),
            mqtt_namespace=str(zone_payload.get('mqtt_namespace', 'agribot')),
            sensor_profile=_load_sensor_profile(
                dict(zone_payload['sensor_profile']),
                context=f'zones[{zone_id}].sensor_profile',
            ),
            devices=loaded_devices,
        )

    if not zones:
        raise ValueError('IoT device catalog must define at least one zone.')
    if not devices:
        raise ValueError('IoT device catalog must define at least one device.')

    return IoTDeviceCatalog(
        schema_version=int(payload.get('schema_version', 1)),
        default_zone_id=str(payload['default_zone_id']),
        frame_id=str(payload.get('frame_id', 'map')),
        zones=zones,
        devices=devices,
    )
