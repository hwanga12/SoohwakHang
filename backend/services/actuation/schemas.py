# 이 모듈은 백엔드 장치 제어 영역에서 장치 제어 서비스에서 쓰는 데이터 계약을 정의한다.
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Point3D(BaseModel):
    # point 3 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    x: float
    y: float
    z: float = 0.0


class SprinklerSelection(BaseModel):
    # sprinkler 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    device_id: str
    zone_id: str
    distance_m: float = Field(ge=0.0)
    position: Point3D


class DiseaseTreatmentPlanRequest(BaseModel):
    # disease 처치 계획 요청 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    zone_id: str = ''
    disease_label: str = ''
    target_position: Point3D | None = None


class ActuationDispatchResult(BaseModel):
    # actuation dispatch 처리 결과를 한 번에 전달하기 위한 클래스를 정의한다.
    dispatched: bool
    status: str
    command_id: str | None = None
    topic: str | None = None
    device_id: str | None = None
    device_type: str | None = None
    method: str | None = None
    detail_message: str


class DiseaseTreatmentPlan(BaseModel):
    # disease 처치 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    disease_label: str
    normalized_disease_label: str
    action_required: bool
    status: str
    rule_id: str
    treatment_type: str | None = None
    treatment_label: str | None = None
    effect_color: str | None = None
    target_position: Point3D | None = None
    selected_sprinkler: SprinklerSelection | None = None
    command_payload: dict[str, Any] | None = None
    reason: str


class DiseaseTreatmentDispatchRequest(BaseModel):
    # disease 처치 dispatch 요청 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    observation_id: str | None = None
    zone_id: str = ''
    disease_label: str = ''
    target_position: Point3D | None = None
    requested_by: str = ''
    auto_execute: bool = True


class DiseaseTreatmentDispatchResponse(BaseModel):
    # disease 처치 dispatch 응답 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    observation_id: str
    treatment_plan: DiseaseTreatmentPlan
    dispatch_result: ActuationDispatchResult
