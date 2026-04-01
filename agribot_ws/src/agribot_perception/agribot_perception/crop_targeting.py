# 이 모듈은 인지와 추론 패키지에서 crop targeting 기능을 담당한다.
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
    # 작물 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class CropTarget:
    # 작물 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    plant_id: str
    zone_id: str
    world_model_name: str
    position: CropPosition
    fruit_id: str = ''


@dataclass(frozen=True)
class _TomatoTarget:
    # tomato 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    fruit_id: str
    position: CropPosition


class CropTargetResolver:
    # 작물 target 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    def __init__(
        self,
        *,
        crop_instances_path: Path | None = None,
        zone_id: str = '',
        max_distance_m: float = 3.0,
        max_bearing_deg: float = 65.0,
    ) -> None:
        # CropTargetResolver 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
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
        # 작물 instances 경로 정보를 계산해 반환한다.
        return self._crop_instances_path

    def lookup(self, plant_id: str) -> CropTarget | None:
        # lookup 정보를 계산해 반환한다.
        return self._targets_by_plant_id.get(plant_id.strip())

    def resolve(
        self,
        *,
        robot_x: float | None,
        robot_y: float | None,
        robot_yaw: float | None,
        preferred_plant_id: str = '',
    ) -> CropTarget | None:
        # 현재 입력 조건을 바탕으로 데이터를 계산하거나 결정한다.
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
    # targets를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
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
        fruit_target = tomatoes_by_plant_id.get(plant_id)
        target_position = (
            fruit_target.position
            if fruit_target is not None
            else CropPosition(
                x=float(pose.get('x', 0.0) or 0.0),
                y=float(pose.get('y', 0.0) or 0.0),
                z=float(pose.get('z', 0.0) or 0.0),
            )
        )
        targets.append(
            CropTarget(
                plant_id=plant_id,
                zone_id=str(item.get('zone_id', '')).strip(),
                world_model_name=str(item.get('world_model_name', '')).strip(),
                position=target_position,
                fruit_id='' if fruit_target is None else fruit_target.fruit_id,
            )
        )

    if not targets:
        raise ValueError(f'No plant targets were loaded from {path}')
    return targets


def _index_tomatoes_by_plant_id(items: Any) -> dict[str, _TomatoTarget]:
    # index tomatoes 작물 id 정보를 계산해 반환한다.
    indexed: dict[str, _TomatoTarget] = {}
    if not isinstance(items, list):
        return indexed
    for item in items:
        if not isinstance(item, dict):
            continue
        parent_plant_id = str(item.get('parent_plant_id', '')).strip()
        tomato_id = str(item.get('tomato_id', '')).strip()
        pose = item.get('pose') or {}
        if parent_plant_id and tomato_id and parent_plant_id not in indexed:
            indexed[parent_plant_id] = _TomatoTarget(
                fruit_id=tomato_id,
                position=CropPosition(
                    x=float(pose.get('x', 0.0) or 0.0),
                    y=float(pose.get('y', 0.0) or 0.0),
                    z=float(pose.get('z', 0.0) or 0.0),
                ),
            )
    return indexed


def _normalize_zone_id(zone_id: str) -> str:
    # 구역 ID를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = zone_id.strip().lower()
    if not normalized:
        return ''
    return _ZONE_ALIASES.get(normalized, normalized)


def _normalize_angle(angle: float) -> float:
    # angle를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    return math.atan2(math.sin(angle), math.cos(angle))
