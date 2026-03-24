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


class RequestRoute(str, Enum):
    AUTO = 'AUTO'
    REVIEW = 'REVIEW'


@dataclass(slots=True)
class ActuationRequestPlan:
    zone_id: str
    device_id: str
    device_type: str
    command_type: str
    target_value: float
    unit: str
    requires_approval: bool
    auto_execute: bool
    requested_by: str
    reason: str
    source_rule: str
    route: str


def plan_actuation_requests(
    environment: EnvironmentSnapshot,
    disease_signal: DiseaseSignal | None = None,
    *,
    requested_by: str,
) -> list[ActuationRequestPlan]:
    disease_signal = disease_signal or DiseaseSignal()
    decisions = evaluate_environment_disease_rules(environment, disease_signal)
    requests: list[ActuationRequestPlan] = []

    for decision in decisions:
        if decision.decision_type != DecisionType.RECOMMEND.value:
            continue

        route = (
            RequestRoute.AUTO.value if decision.auto_execute else RequestRoute.REVIEW.value
        )
        requests.append(
            ActuationRequestPlan(
                zone_id=environment.zone_id,
                device_id=_default_device_id(environment.zone_id, decision),
                device_type=decision.device_type,
                command_type=decision.command_type,
                target_value=decision.target_value,
                unit=decision.unit,
                requires_approval=decision.requires_approval,
                auto_execute=decision.auto_execute,
                requested_by=requested_by,
                reason=_build_reason(decision),
                source_rule=decision.source_rule,
                route=route,
            )
        )

    return requests


def request_signature(plan: ActuationRequestPlan) -> tuple[str, ...]:
    return (
        plan.zone_id,
        plan.device_type,
        plan.command_type,
        f'{plan.target_value:.3f}',
        plan.unit,
        plan.route,
        plan.source_rule,
        str(plan.requires_approval),
        str(plan.auto_execute),
        plan.reason,
    )


def _default_device_id(zone_id: str, decision: RuleDecision) -> str:
    return f'{zone_id}_{decision.device_type}'


def _build_reason(decision: RuleDecision) -> str:
    payload_items = [
        f'{key}={value}'
        for key, value in sorted(decision.command_payload.items())
        if key.strip() and str(value).strip()
    ]
    if not payload_items:
        return decision.reason
    return f'{decision.reason} payload=' + ','.join(payload_items)
