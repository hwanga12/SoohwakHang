# 이 모듈은 상위 제어와 의사결정 패키지에서 actuation request planner 판단과 실행 보조 로직을 담당한다.
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
    # 요청 데이터 경로 값을 명확히 구분하기 위한 열거형 클래스를 정의한다.
    AUTO = 'AUTO'
    REVIEW = 'REVIEW'


@dataclass(slots=True)
class ActuationRequestPlan:
    # actuation 요청 데이터 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
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
    # actuation requests를 어떤 순서와 조건으로 처리할지 계획한다.
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
    # request signature 정보를 계산해 반환한다.
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
    # default 장치 id 정보를 계산해 반환한다.
    return f'{zone_id}_{decision.device_type}'


def _build_reason(decision: RuleDecision) -> str:
    # reason를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    payload_items = [
        f'{key}={value}'
        for key, value in sorted(decision.command_payload.items())
        if key.strip() and str(value).strip()
    ]
    if not payload_items:
        return decision.reason
    return f'{decision.reason} payload=' + ','.join(payload_items)
