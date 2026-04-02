# 이 모듈은 상위 제어와 의사결정 패키지에서 environment disease rules 판단과 실행 보조 로직을 담당한다.
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DecisionType(str, Enum):
    # decision type 값을 명확히 구분하기 위한 열거형 클래스를 정의한다.
    RECOMMEND = 'RECOMMEND'
    HOLD = 'HOLD'


@dataclass(slots=True)
class EnvironmentSnapshot:
    # environment 시점의 값을 기록하기 위한 스냅샷 클래스를 정의한다.
    zone_id: str
    temperature: float
    humidity: float
    soil_moisture: float
    light_level: float
    co2_level: float = 0.0


@dataclass(slots=True)
class DiseaseSignal:
    # disease 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    class_name: str = ''
    disease_name: str = ''
    health_score: float = 1.0
    repeat_count: int = 0
    growth_stage: str = ''
    confidence: float = 0.0


@dataclass(slots=True)
class RuleDecision:
    # rule 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    decision_type: str
    device_type: str
    command_type: str
    target_value: float
    unit: str
    priority: int
    auto_execute: bool
    requires_approval: bool
    reason: str
    source_rule: str
    command_payload: dict[str, str] = field(default_factory=dict)


def evaluate_environment_disease_rules(
    environment: EnvironmentSnapshot,
    disease_signal: DiseaseSignal | None = None,
) -> list[RuleDecision]:
    # 환경 disease 규칙 조건을 평가한다.
    disease_signal = disease_signal or DiseaseSignal()
    decisions: list[RuleDecision] = []

    humid_fungal_risk = _is_humid_fungal_risk(environment, disease_signal)
    if humid_fungal_risk:
        decisions.append(
            RuleDecision(
                decision_type=DecisionType.HOLD.value,
                device_type='watering',
                command_type='hold_watering',
                target_value=0.0,
                unit='ml',
                priority=340,
                auto_execute=True,
                requires_approval=False,
                reason=(
                    '습도가 높고 곰팡이 계열 질병이 반복되어 급수를 잠시 보류합니다.'
                ),
                source_rule='R-HOLD-WATER-HUMID-FUNGAL',
            )
        )

    if not humid_fungal_risk:
        if environment.soil_moisture < 22.0:
            decisions.append(
                RuleDecision(
                    decision_type=DecisionType.RECOMMEND.value,
                    device_type='watering',
                    command_type='dispense_water',
                    target_value=900.0,
                    unit='ml',
                    priority=300,
                    auto_execute=True,
                    requires_approval=False,
                    reason='토양 수분이 매우 낮아 즉시 급수가 필요한 상태입니다.',
                    source_rule='R-WATER-LOW-SOIL-AUTO',
                )
            )
        elif environment.soil_moisture < 30.0:
            decisions.append(
                RuleDecision(
                    decision_type=DecisionType.RECOMMEND.value,
                    device_type='watering',
                    command_type='dispense_water',
                    target_value=600.0,
                    unit='ml',
                    priority=220,
                    auto_execute=False,
                    requires_approval=True,
                    reason='토양 수분이 낮아 급수 후보로 올리되 사람 확인을 먼저 받습니다.',
                    source_rule='R-WATER-MID-SOIL-REVIEW',
                )
            )

    if _needs_calcium_support(disease_signal):
        decisions.append(
            RuleDecision(
                decision_type=DecisionType.RECOMMEND.value,
                device_type='nutrient',
                command_type='apply_nutrient_recipe',
                target_value=250.0,
                unit='ml',
                priority=230,
                auto_execute=False,
                requires_approval=True,
                reason='착화/과실기 칼슘 결핍 계열 이상 징후라 칼슘 보강제를 권장합니다.',
                source_rule='R-NUTRIENT-CALCIUM-FRUITING',
                command_payload={'nutrient_type': 'calcium_boost'},
            )
        )

    return sorted(
        decisions,
        key=lambda decision: (-decision.priority, decision.device_type, decision.command_type),
    )


def _is_humid_fungal_risk(
    environment: EnvironmentSnapshot,
    disease_signal: DiseaseSignal,
) -> bool:
    # humid fungal risk인지 여부를 불리언 값으로 판단한다.
    if environment.humidity < 80.0:
        return False
    if disease_signal.repeat_count < 2:
        return False
    disease_text = _normalized_disease_text(disease_signal)
    return any(
        keyword in disease_text
        for keyword in (
            'powdery_mildew',
            'gray_mold',
            'mold',
            'fungal',
            '곰팡이',
            '흰가루',
        )
    )


def _needs_calcium_support(disease_signal: DiseaseSignal) -> bool:
    # calcium support 여부를 판단해 반환한다.
    if disease_signal.confidence and disease_signal.confidence < 0.5:
        return False

    growth_stage = disease_signal.growth_stage.strip().lower()
    if growth_stage not in {
        '13',
        'flowering_fruiting_stage',
        'fruiting',
        'flowering',
        '착화/과실기',
    }:
        return False

    disease_text = _normalized_disease_text(disease_signal)
    return any(
        keyword in disease_text
        for keyword in (
            'blossom_end_rot',
            'calcium_deficiency',
            '칼슘결핍',
            '배꼽썩음',
        )
    )


def _normalized_disease_text(disease_signal: DiseaseSignal) -> str:
    # normalized disease 텍스트 정보를 계산해 반환한다.
    return ' '.join(
        item.strip().lower()
        for item in (disease_signal.class_name, disease_signal.disease_name)
        if item.strip()
    )
