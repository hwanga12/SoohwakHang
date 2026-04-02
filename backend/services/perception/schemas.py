# 이 모듈은 인지 서비스 계층에서 인지 서비스에서 쓰는 데이터 계약을 정의한다.
from __future__ import annotations

from pydantic import BaseModel, Field

from services.actuation.schemas import ActuationDispatchResult, DiseaseTreatmentPlan, Point3D


class BoundingBox(BaseModel):
    # bounding 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    x1: float
    y1: float
    x2: float
    y2: float


class ThinInferenceConfirmRequest(BaseModel):
    # thin inference confirm 요청 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    observation_id: str | None = None
    robot_id: str = ''
    zone_id: str = ''
    plant_id: str = ''
    fruit_id: str = ''
    frame_id: str = ''
    target_position: Point3D | None = None
    requested_by: str = ''
    auto_execute_treatment: bool = True
    preliminary_label: str = ''
    preliminary_confidence: float = Field(default=0.0, ge=0.0)
    test_override_final_label: str = ''
    test_override_final_confidence: float = Field(default=0.99, ge=0.0)
    image_base64: str
    image_format: str = 'jpg'
    bbox: BoundingBox | None = None


class ThinInferenceConfirmResponse(BaseModel):
    # thin inference confirm 응답 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    observation_id: str
    preliminary_label: str
    preliminary_confidence: float
    final_label: str
    final_confidence: float
    image_path: str
    reviewed_at: str
    decision_source: str
    treatment_plan: DiseaseTreatmentPlan | None = None
    dispatch_result: ActuationDispatchResult | None = None
    disease_judgment_id: str | None = None
    harvest_decision_id: str | None = None
