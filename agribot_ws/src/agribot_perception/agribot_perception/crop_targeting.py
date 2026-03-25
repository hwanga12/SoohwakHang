from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any


_DEFAULT_CROP_INSTANCES_RELATIVE_PATH = Path(
    'agribot_ws/src/agribot_description/config/crop_instances.yaml'
)
_ZONE_ALIASES = {
    'farm_01': 'farm_01',
    'greenhouse_01': 'farm_01',
}


@dataclass(frozen=True)
class CropPosition:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class CropTarget:
    plant_id: str
    zone_id: str
    world_model_name: str
    position: CropPosition
    fruit_id: str = ''


class CropTargetResolver:
    """Pick the most plausible crop target from the robot pose and crop catalog."""

    def __init__(
        self,
        *,
        crop_instances_path: Path | None = None,
        zone_id: str = '',
        max_distance_m: float = 3.0,
        max_bearing_deg: float = 65.0,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        default_path = repo_root / _DEFAULT_CROP_INSTANCES_RELATIVE_PATH
        self._crop_instances_path = Path(crop_instances_path or default_path).expanduser()
        self._zone_id = _normalize_zone_id(zone_id)
        self._max_distance_m = max(0.1, float(max_distance_m))
        self._max_bearing_rad = math.radians(max(1.0, float(max_bearing_deg)))
        self._targets = _load_targets(self._crop_instances_path)
        self._targets_by_plant_id = {item.plant_id: item for item in self._targets}

    @property
    def crop_instances_path(self) -> Path:
        return self._crop_instances_path

    def lookup(self, plant_id: str) -> CropTarget | None:
        return self._targets_by_plant_id.get(plant_id.strip())

    def resolve(
        self,
        *,
        robot_x: float | None,
        robot_y: float | None,
        robot_yaw: float | None,
        preferred_plant_id: str = '',
    ) -> CropTarget | None:
        preferred = preferred_plant_id.strip()
        if preferred:
            return self.lookup(preferred)

        if robot_x is None or robot_y is None or robot_yaw is None:
            return None

        candidates: list[tuple[float, float, CropTarget]] = []
        for target in self._targets:
            if self._zone_id and _normalize_zone_id(target.zone_id) != self._zone_id:
                continue

            delta_x = target.position.x - robot_x
            delta_y = target.position.y - robot_y
            distance = math.hypot(delta_x, delta_y)
            if distance > self._max_distance_m:
                continue

            bearing = abs(_normalize_angle(math.atan2(delta_y, delta_x) - robot_yaw))
            if bearing > self._max_bearing_rad:
                continue

            candidates.append((bearing, distance, target))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1], item[2].plant_id))
        return candidates[0][2]


def _load_targets(path: Path) -> list[CropTarget]:
    if not path.exists():
        raise FileNotFoundError(f'crop_instances.yaml not found at {path}')

    import yaml

    payload = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'Expected a YAML mapping at the top of {path}')

    tomatoes_by_plant_id = _index_tomatoes_by_plant_id(payload.get('tomatoes', []))
    targets: list[CropTarget] = []
    for item in payload.get('plants', []):
        if not isinstance(item, dict):
            continue

        plant_id = str(item.get('plant_id', '')).strip()
        if not plant_id:
            continue

        pose = item.get('pose') or {}
        fruit_id = tomatoes_by_plant_id.get(plant_id, '')
        targets.append(
            CropTarget(
                plant_id=plant_id,
                zone_id=str(item.get('zone_id', '')).strip(),
                world_model_name=str(item.get('world_model_name', '')).strip(),
                position=CropPosition(
                    x=float(pose.get('x', 0.0) or 0.0),
                    y=float(pose.get('y', 0.0) or 0.0),
                    z=float(pose.get('z', 0.0) or 0.0),
                ),
                fruit_id=fruit_id,
            )
        )

    if not targets:
        raise ValueError(f'No plant targets were loaded from {path}')
    return targets


def _index_tomatoes_by_plant_id(items: Any) -> dict[str, str]:
    indexed: dict[str, str] = {}
    if not isinstance(items, list):
        return indexed
    for item in items:
        if not isinstance(item, dict):
            continue
        parent_plant_id = str(item.get('parent_plant_id', '')).strip()
        tomato_id = str(item.get('tomato_id', '')).strip()
        if parent_plant_id and tomato_id and parent_plant_id not in indexed:
            indexed[parent_plant_id] = tomato_id
    return indexed


def _normalize_zone_id(zone_id: str) -> str:
    normalized = zone_id.strip().lower()
    if not normalized:
        return ''
    return _ZONE_ALIASES.get(normalized, normalized)


def _normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))
