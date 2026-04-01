# 이 모듈은 IoT 장치 연동 패키지에서 environment sensor profile 장치 흐름을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
import math

from .device_mapping import SensorWaveSpec, ZoneSensorProfile


@dataclass(frozen=True)
class EnvironmentSample:
    # environment 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    zone_id: str
    temperature: float
    humidity: float
    soil_moisture: float
    light_level: float
    co2_level: float


def _clamp(value: float, minimum: float, maximum: float) -> float:
    # 대상 값을 허용 범위로 제한한다.
    return max(minimum, min(value, maximum))


def _wave_value(spec: SensorWaveSpec, elapsed_sec: float, *, phase_offset_sec: float) -> float:
    # wave 값 정보를 계산해 반환한다.
    angle = ((elapsed_sec + phase_offset_sec) / spec.period_sec) * 2.0 * math.pi
    value = spec.base + (spec.amplitude * math.sin(angle))
    return _clamp(value, spec.minimum, spec.maximum)


def generate_environment_sample(
    zone_id: str,
    profile: ZoneSensorProfile,
    *,
    elapsed_sec: float,
) -> EnvironmentSample:
    # 환경 sample을 생성한다.
    phase_offset_sec = profile.phase_offset_sec
    return EnvironmentSample(
        zone_id=zone_id,
        temperature=_wave_value(profile.temperature, elapsed_sec, phase_offset_sec=phase_offset_sec),
        humidity=_wave_value(profile.humidity, elapsed_sec, phase_offset_sec=phase_offset_sec + 7.5),
        soil_moisture=_wave_value(
            profile.soil_moisture,
            elapsed_sec,
            phase_offset_sec=phase_offset_sec + 15.0,
        ),
        light_level=_wave_value(
            profile.light_level,
            elapsed_sec,
            phase_offset_sec=phase_offset_sec + 22.5,
        ),
        co2_level=_wave_value(profile.co2_level, elapsed_sec, phase_offset_sec=phase_offset_sec + 30.0),
    )
