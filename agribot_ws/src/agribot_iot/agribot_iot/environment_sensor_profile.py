from __future__ import annotations

from dataclasses import dataclass
import math

from .device_mapping import SensorWaveSpec, ZoneSensorProfile


@dataclass(frozen=True)
class EnvironmentSample:
    zone_id: str
    temperature: float
    humidity: float
    soil_moisture: float
    light_level: float
    co2_level: float


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _wave_value(spec: SensorWaveSpec, elapsed_sec: float, *, phase_offset_sec: float) -> float:
    angle = ((elapsed_sec + phase_offset_sec) / spec.period_sec) * 2.0 * math.pi
    value = spec.base + (spec.amplitude * math.sin(angle))
    return _clamp(value, spec.minimum, spec.maximum)


def generate_environment_sample(
    zone_id: str,
    profile: ZoneSensorProfile,
    *,
    elapsed_sec: float,
) -> EnvironmentSample:
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
