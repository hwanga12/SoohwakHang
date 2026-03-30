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


class DeviceDecisionState(str, Enum):
    AUTO_EXECUTE = 'AUTO_EXECUTE'
    REQUIRES_APPROVAL = 'REQUIRES_APPROVAL'
    NO_ACTION = 'NO_ACTION'


@dataclass(slots=True)
class DeviceDecision:
    zone_id: str
    device_type: str
    state: str
    command_type: str
    target_value: float
    unit: str
    auto_execute: bool
    requires_approval: bool
    reason: str
    source_rule: str
    temperature: float
    humidity: float
    light_level: float
    disease_context: str


def evaluate_curtain_decision(
    environment: EnvironmentSnapshot,
    disease_signal: DiseaseSignal | None = None,
) -> DeviceDecision:
    return _evaluate_device_decision(
        environment,
        disease_signal or DiseaseSignal(),
        device_type='curtain',
        no_action_reason='온도와 조도가 기준 이하라 커튼 제어 후보를 만들지 않습니다.',
        no_action_rule='R-CURTAIN-NONE',
        default_unit='percent_closed',
    )


def evaluate_fan_decision(
    environment: EnvironmentSnapshot,
    disease_signal: DiseaseSignal | None = None,
) -> DeviceDecision:
    return _evaluate_device_decision(
        environment,
        disease_signal or DiseaseSignal(),
        device_type='fan',
        no_action_reason='습도와 병해 조건이 기준 이하라 환기팬 제어 후보를 만들지 않습니다.',
        no_action_rule='R-FAN-NONE',
        default_unit='level',
    )


def format_device_decision_log(decision: DeviceDecision) -> str:
    target_text = (
        f'{decision.target_value:.1f}{decision.unit}'
        if decision.command_type != 'noop'
        else '-'
    )
    return (
        f'{decision.device_type.capitalize()} decision: '
        f'zone={decision.zone_id}, '
        f'state={decision.state}, '
        f'command={decision.command_type}, '
        f'target={target_text}, '
        f'temperature={decision.temperature:.1f}, '
        f'humidity={decision.humidity:.1f}, '
        f'light={decision.light_level:.1f}, '
        f'disease={decision.disease_context}, '
        f'rule={decision.source_rule}, '
        f'reason={decision.reason}'
    )


def _evaluate_device_decision(
    environment: EnvironmentSnapshot,
    disease_signal: DiseaseSignal,
    *,
    device_type: str,
    no_action_reason: str,
    no_action_rule: str,
    default_unit: str,
) -> DeviceDecision:
    all_decisions = evaluate_environment_disease_rules(environment, disease_signal)
    candidates = [
        decision for decision in all_decisions if decision.device_type == device_type
    ]

    selected_candidate = _select_candidate(candidates)
    if selected_candidate is None:
        return DeviceDecision(
            zone_id=environment.zone_id,
            device_type=device_type,
            state=DeviceDecisionState.NO_ACTION.value,
            command_type='noop',
            target_value=0.0,
            unit=default_unit,
            auto_execute=False,
            requires_approval=False,
            reason=no_action_reason,
            source_rule=no_action_rule,
            temperature=environment.temperature,
            humidity=environment.humidity,
            light_level=environment.light_level,
            disease_context=_format_disease_context(disease_signal),
        )

    state = (
        DeviceDecisionState.AUTO_EXECUTE.value
        if selected_candidate.auto_execute
        else DeviceDecisionState.REQUIRES_APPROVAL.value
    )
    return DeviceDecision(
        zone_id=environment.zone_id,
        device_type=device_type,
        state=state,
        command_type=selected_candidate.command_type,
        target_value=selected_candidate.target_value,
        unit=selected_candidate.unit,
        auto_execute=selected_candidate.auto_execute,
        requires_approval=selected_candidate.requires_approval,
        reason=selected_candidate.reason,
        source_rule=selected_candidate.source_rule,
        temperature=environment.temperature,
        humidity=environment.humidity,
        light_level=environment.light_level,
        disease_context=_format_disease_context(disease_signal),
    )


def _select_candidate(candidates: list[RuleDecision]) -> RuleDecision | None:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda candidate: (-candidate.priority, candidate.command_type),
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
