from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Point3D(BaseModel):
    x: float
    y: float
    z: float = 0.0


class SprinklerSelection(BaseModel):
    device_id: str
    zone_id: str
    distance_m: float = Field(ge=0.0)
    position: Point3D


class DiseaseTreatmentPlanRequest(BaseModel):
    zone_id: str = ''
    disease_label: str = ''
    target_position: Point3D | None = None


class ActuationDispatchResult(BaseModel):
    dispatched: bool
    status: str
    command_id: str | None = None
    topic: str | None = None
    device_id: str | None = None
    device_type: str | None = None
    method: str | None = None
    detail_message: str


class DiseaseTreatmentPlan(BaseModel):
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
    observation_id: str | None = None
    zone_id: str = ''
    disease_label: str = ''
    target_position: Point3D | None = None
    requested_by: str = ''
    auto_execute: bool = True


class DiseaseTreatmentDispatchResponse(BaseModel):
    observation_id: str
    treatment_plan: DiseaseTreatmentPlan
    dispatch_result: ActuationDispatchResult
