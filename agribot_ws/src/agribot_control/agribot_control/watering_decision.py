from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .environment_disease_rules import (
    DecisionType,
    DiseaseSignal,
    EnvironmentSnapshot,
    RuleDecision,
    evaluate_environment_disease_rules,
)


class WateringDecisionState(str, Enum):
    AUTO_EXECUTE = 'AUTO_EXECUTE'
    REQUIRES_APPROVAL = 'REQUIRES_APPROVAL'
    HOLD = 'HOLD'
    NO_ACTION = 'NO_ACTION'


@dataclass(slots=True)
class WateringDecision:
    zone_id: str
    state: str
    command_type: str
    target_value: float
    unit: str
    auto_execute: bool
    requires_approval: bool
    reason: str
    source_rule: str
    soil_moisture: float
    humidity: float
    disease_context: str


def evaluate_watering_decision(
    environment: EnvironmentSnapshot,
    disease_signal: DiseaseSignal | None = None,
) -> WateringDecision:
    disease_signal = disease_signal or DiseaseSignal()
    all_decisions = evaluate_environment_disease_rules(environment, disease_signal)
    watering_candidates = [
        decision
        for decision in all_decisions
        if decision.device_type == 'watering'
    ]

    hold_candidate = _select_candidate(
        watering_candidates,
        decision_type=DecisionType.HOLD.value,
    )
    if hold_candidate is not None:
        return _build_watering_decision(
            environment,
            disease_signal,
            hold_candidate,
            state=WateringDecisionState.HOLD.value,
        )

    recommend_candidate = _select_candidate(
        watering_candidates,
        decision_type=DecisionType.RECOMMEND.value,
    )
    if recommend_candidate is not None:
        state = (
            WateringDecisionState.AUTO_EXECUTE.value
            if recommend_candidate.auto_execute
            else WateringDecisionState.REQUIRES_APPROVAL.value
        )
        return _build_watering_decision(
            environment,
            disease_signal,
            recommend_candidate,
            state=state,
        )

    return WateringDecision(
        zone_id=environment.zone_id,
        state=WateringDecisionState.NO_ACTION.value,
        command_type='noop',
        target_value=0.0,
        unit='ml',
        auto_execute=False,
        requires_approval=False,
        reason='토양 수분이 기준 이상이라 급수 후보를 만들지 않습니다.',
        source_rule='R-WATER-NONE',
        soil_moisture=environment.soil_moisture,
        humidity=environment.humidity,
        disease_context=_format_disease_context(disease_signal),
    )


def format_watering_decision_log(decision: WateringDecision) -> str:
    target_text = (
        f'{decision.target_value:.1f}{decision.unit}'
        if decision.command_type != 'noop'
        else '-'
    )
    return (
        'Watering decision: '
        f'zone={decision.zone_id}, '
        f'state={decision.state}, '
        f'command={decision.command_type}, '
        f'target={target_text}, '
        f'soil_moisture={decision.soil_moisture:.1f}, '
        f'humidity={decision.humidity:.1f}, '
        f'disease={decision.disease_context}, '
        f'rule={decision.source_rule}, '
        f'reason={decision.reason}'
    )


def _select_candidate(
    candidates: list[RuleDecision],
    *,
    decision_type: str,
) -> RuleDecision | None:
    filtered_candidates = [
        candidate for candidate in candidates if candidate.decision_type == decision_type
    ]
    if not filtered_candidates:
        return None
    return min(
        filtered_candidates,
        key=lambda candidate: (-candidate.priority, candidate.command_type),
    )


def _build_watering_decision(
    environment: EnvironmentSnapshot,
    disease_signal: DiseaseSignal,
    candidate: RuleDecision,
    *,
    state: str,
) -> WateringDecision:
    return WateringDecision(
        zone_id=environment.zone_id,
        state=state,
        command_type=candidate.command_type,
        target_value=candidate.target_value,
        unit=candidate.unit,
        auto_execute=candidate.auto_execute,
        requires_approval=candidate.requires_approval,
        reason=candidate.reason,
        source_rule=candidate.source_rule,
        soil_moisture=environment.soil_moisture,
        humidity=environment.humidity,
        disease_context=_format_disease_context(disease_signal),
    )


def _format_disease_context(disease_signal: DiseaseSignal) -> str:
    disease_parts = [
        item.strip()
        for item in (disease_signal.class_name, disease_signal.disease_name)
        if item.strip()
    ]
    if not disease_parts:
        return 'none'

    summary = '/'.join(disease_parts)
    if disease_signal.repeat_count > 1:
        summary = f'{summary} x{disease_signal.repeat_count}'
    return summary
