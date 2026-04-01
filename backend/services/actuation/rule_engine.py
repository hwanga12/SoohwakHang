# 이 모듈은 백엔드 장치 제어 영역에서 환경 상태를 바탕으로 장치 제어 규칙을 계산한다.
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
from typing import Iterable
import xml.etree.ElementTree as ET

from services.actuation.schemas import (
    DiseaseTreatmentPlan,
    Point3D,
    SprinklerSelection,
)


_DEFAULT_WORLD_RELATIVE_PATH = Path('agribot_ws/src/agribot_description/worlds/farm_world.sdf')
_DEFAULT_SPRINKLER_ZONE_ID = 'farm_01'
_ZONE_ALIASES = {
    'farm_01': 'farm_01',
    'greenhouse_01': 'farm_01',
}


@dataclass(frozen=True)
class _TreatmentRule:
    # 처치 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    rule_id: str
    treatment_type: str
    treatment_label: str
    effect_color: str
    command_type: str
    duration_sec: float


@dataclass(frozen=True)
class _SprinklerSpec:
    # sprinkler 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    device_id: str
    zone_id: str
    position: Point3D


_ACTION_RULES: dict[str, _TreatmentRule] = {
    'tomato_powdery_mildew': _TreatmentRule(
        rule_id='R-DISEASE-SPRAY-POWDERY-MILDEW',
        treatment_type='pesticide_spray',
        treatment_label='약재 살포',
        effect_color='red',
        command_type='spray_pesticide',
        duration_sec=3.0,
    ),
    'tomato_calcium_deficiency': _TreatmentRule(
        rule_id='R-DISEASE-SPRAY-CALCIUM-DEFICIENCY',
        treatment_type='calcium_solution_spray',
        treatment_label='칼슘액비 살포',
        effect_color='yellow',
        command_type='spray_calcium_solution',
        duration_sec=2.5,
    ),
}
_RULE_LABEL_ALIASES = {
    'tomato_powdery_mildew_disease': 'tomato_powdery_mildew',
    'tomato_calcium_deficiency_disease': 'tomato_calcium_deficiency',
    'tomato_gray_mold_disease': 'tomato_gray_mold',
    'tomato_blossom_end_rot': 'tomato_calcium_deficiency',
    'blossom_end_rot': 'tomato_calcium_deficiency',
    'tomato_fruit_cracking_disease': 'tomato_crack',
}
_NO_ACTION_LABELS = {
    'tomato_gray_mold',
    'tomato_gray_mold_disease',
    'tomato_crack',
    'tomato_fruit_cracking_disease',
    'tomato_macro_npk_deficiency_disease',
}


class DiseaseTreatmentRuleEngine:
    # disease 처치 rule 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    def __init__(
        self,
        *,
        world_path: Path | None = None,
        sprinklers: Iterable[SprinklerSelection | _SprinklerSpec] | None = None,
    ) -> None:
        # DiseaseTreatmentRuleEngine 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        repo_root = Path(__file__).resolve().parents[3]
        default_world_path = repo_root / _DEFAULT_WORLD_RELATIVE_PATH
        self._world_path = Path(
            os.environ.get('AGRIBOT_WORLD_SDF_PATH', str(world_path or default_world_path))
        ).expanduser()
        if sprinklers is None:
            self._sprinklers = self._load_sprinklers()
        else:
            self._sprinklers = [self._coerce_sprinkler(item) for item in sprinklers]

    def evaluate(
        self,
        *,
        disease_label: str,
        zone_id: str = '',
        target_position: Point3D | None = None,
    ) -> DiseaseTreatmentPlan:
        # 대상 조건을 평가한다.
        normalized_label = disease_label.strip().lower()
        canonical_rule_label = _RULE_LABEL_ALIASES.get(normalized_label, normalized_label)
        rule = _ACTION_RULES.get(canonical_rule_label)
        if rule is None:
            return self._build_no_action_plan(
                disease_label=disease_label,
                normalized_label=normalized_label,
                zone_id=zone_id,
                target_position=target_position,
                reason=(
                    'No spray rule is configured for this disease.'
                    if normalized_label in _NO_ACTION_LABELS or canonical_rule_label in _NO_ACTION_LABELS
                    else 'Disease label is not supported by the treatment rule engine.'
                ),
            )

        if target_position is None:
            return DiseaseTreatmentPlan(
                disease_label=disease_label,
                normalized_disease_label=normalized_label,
                action_required=True,
                status='awaiting_target_position',
                rule_id=rule.rule_id,
                treatment_type=rule.treatment_type,
                treatment_label=rule.treatment_label,
                effect_color=rule.effect_color,
                target_position=None,
                selected_sprinkler=None,
                command_payload=None,
                reason='Actionable disease detected, but target_position was not provided.',
            )

        sprinkler = self._select_nearest_sprinkler(
            zone_id=zone_id,
            target_position=target_position,
        )
        if sprinkler is None:
            return DiseaseTreatmentPlan(
                disease_label=disease_label,
                normalized_disease_label=normalized_label,
                action_required=True,
                status='no_available_sprinkler',
                rule_id=rule.rule_id,
                treatment_type=rule.treatment_type,
                treatment_label=rule.treatment_label,
                effect_color=rule.effect_color,
                target_position=target_position,
                selected_sprinkler=None,
                command_payload=None,
                reason='No sprinkler was available for the requested zone.',
            )

        return DiseaseTreatmentPlan(
            disease_label=disease_label,
            normalized_disease_label=normalized_label,
            action_required=True,
            status='ready',
            rule_id=rule.rule_id,
            treatment_type=rule.treatment_type,
            treatment_label=rule.treatment_label,
            effect_color=rule.effect_color,
            target_position=target_position,
            selected_sprinkler=sprinkler,
            command_payload={
                'device_type': 'sprinkler',
                'device_id': sprinkler.device_id,
                'zone_id': sprinkler.zone_id,
                'command_type': rule.command_type,
                'treatment_type': rule.treatment_type,
                'effect_color': rule.effect_color,
                'target_value': rule.duration_sec,
                'unit': 'sec',
            },
            reason='Nearest sprinkler selected for the actionable disease.',
        )

    def _build_no_action_plan(
        self,
        *,
        disease_label: str,
        normalized_label: str,
        zone_id: str,
        target_position: Point3D | None,
        reason: str,
    ) -> DiseaseTreatmentPlan:
        # NO action 계획를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
        del zone_id
        return DiseaseTreatmentPlan(
            disease_label=disease_label,
            normalized_disease_label=normalized_label,
            action_required=False,
            status='no_action',
            rule_id='R-DISEASE-NO-SPRAY',
            treatment_type=None,
            treatment_label=None,
            effect_color=None,
            target_position=target_position,
            selected_sprinkler=None,
            command_payload=None,
            reason=reason,
        )

    def _select_nearest_sprinkler(
        self,
        *,
        zone_id: str,
        target_position: Point3D,
    ) -> SprinklerSelection | None:
        # nearest 스프링클러 가운데 필요한 대상을 고른다.
        if not self._sprinklers:
            return None

        normalized_zone_id = _normalize_zone_id(zone_id)
        candidates = [
            sprinkler
            for sprinkler in self._sprinklers
            if _normalize_zone_id(sprinkler.zone_id) == normalized_zone_id
        ]
        if not candidates:
            candidates = self._sprinklers

        # Prefer the sprinkler in the same crop column first so the selected
        # head matches what the operator sees next to the diagnosed plant.
        nearest = min(
            candidates,
            key=lambda sprinkler: (
                abs(sprinkler.position.x - target_position.x),
                abs(sprinkler.position.y - target_position.y),
                _distance_between(sprinkler.position, target_position),
            ),
        )
        return SprinklerSelection(
            device_id=nearest.device_id,
            zone_id=nearest.zone_id,
            distance_m=_distance_between(nearest.position, target_position),
            position=nearest.position,
        )

    def _load_sprinklers(self) -> list[_SprinklerSpec]:
        # sprinklers를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        if not self._world_path.exists():
            return []

        root = ET.fromstring(self._world_path.read_text(encoding='utf-8'))
        sprinklers: list[_SprinklerSpec] = []
        default_zone_id = os.environ.get(
            'AGRIBOT_SPRINKLER_ZONE_ID',
            _DEFAULT_SPRINKLER_ZONE_ID,
        ).strip() or _DEFAULT_SPRINKLER_ZONE_ID

        for include in root.findall('.//include'):
            name = (include.findtext('name') or '').strip()
            if not name.startswith('sprinkler_'):
                continue
            pose_text = (include.findtext('pose') or '').strip()
            position = _parse_pose_to_point(pose_text)
            if position is None:
                continue
            sprinklers.append(
                _SprinklerSpec(
                    device_id=name,
                    zone_id=default_zone_id,
                    position=position,
                )
            )
        return sprinklers

    def _coerce_sprinkler(
        self,
        sprinkler: SprinklerSelection | _SprinklerSpec,
    ) -> _SprinklerSpec:
        # coerce 스프링클러 정보를 계산해 반환한다.
        if isinstance(sprinkler, _SprinklerSpec):
            return sprinkler
        return _SprinklerSpec(
            device_id=sprinkler.device_id,
            zone_id=sprinkler.zone_id,
            position=sprinkler.position,
        )


def _parse_pose_to_point(pose_text: str) -> Point3D | None:
    # 위치 자세 TO point를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    parts = pose_text.split()
    if len(parts) < 3:
        return None
    try:
        return Point3D(
            x=float(parts[0]),
            y=float(parts[1]),
            z=float(parts[2]),
        )
    except ValueError:
        return None


def _distance_between(a: Point3D, b: Point3D) -> float:
    # distance between 정보를 계산해 반환한다.
    return math.sqrt(
        ((a.x - b.x) ** 2)
        + ((a.y - b.y) ** 2)
        + ((a.z - b.z) ** 2)
    )


def _normalize_zone_id(zone_id: str) -> str:
    # 구역 ID를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = zone_id.strip().lower()
    if not normalized:
        return _DEFAULT_SPRINKLER_ZONE_ID
    return _ZONE_ALIASES.get(normalized, normalized)
