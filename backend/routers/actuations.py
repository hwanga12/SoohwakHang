# 이 모듈은 백엔드의 장치 제어 API 라우터를 정의하고, 요청을 서비스 계층과 연결한다.
import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from services.actuation.dispatcher import TreatmentCommandDispatcher
from services.actuation.rule_engine import DiseaseTreatmentRuleEngine
from services.actuation.schemas import (
    DiseaseTreatmentDispatchRequest,
    DiseaseTreatmentDispatchResponse,
    DiseaseTreatmentPlan,
    DiseaseTreatmentPlanRequest,
)
from services.operations_service import OperationsService

router = APIRouter()
_treatment_rule_engine = DiseaseTreatmentRuleEngine()
_treatment_dispatcher = TreatmentCommandDispatcher()
_operations_service = OperationsService()

class ApproveReq(BaseModel):
    # approve 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    reviewed_by: str
    auto_execute: bool = True

class RejectReq(BaseModel):
    # reject 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    reviewed_by: str
    comment: Optional[str] = None

class WateringReq(BaseModel):
    # 급수 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    zone_id: str
    device_id: str
    target_value: float
    value_unit: str = "ml"
    requested_by: str
    request_source: str
    recommendation_id: Optional[str] = None

class CurtainReq(BaseModel):
    # 커튼 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    zone_id: str
    device_id: str
    target_value: float
    value_unit: str = "percent"
    requested_by: str
    request_source: str

class FanReq(BaseModel):
    # 환기팬 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    zone_id: str
    device_id: str
    target_value: float
    value_unit: str = "level"
    requested_by: str
    request_source: str

class NutrientsReq(BaseModel):
    # nutrients 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    zone_id: str
    device_id: str
    target_value: float
    value_unit: str = "ml"
    requested_by: str
    request_source: str
    recommendation_id: Optional[str] = None
    command_payload: Optional[dict] = None

@router.get("/recommendations")
def get_recommendations():
    # recommendations를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return {"data": _operations_service.list_recommendations()}

@router.post("/treatment-plan", response_model=DiseaseTreatmentPlan)
def build_treatment_plan(req: DiseaseTreatmentPlanRequest):
    # 처치 계획를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return _treatment_rule_engine.evaluate(
        disease_label=req.disease_label,
        zone_id=req.zone_id,
        target_position=req.target_position,
    )

@router.post("/disease-treatment/dispatch", response_model=DiseaseTreatmentDispatchResponse)
def dispatch_disease_treatment(req: DiseaseTreatmentDispatchRequest):
    # disease 처치를 외부 시스템이나 다음 처리 단계로 전달한다.
    observation_id = req.observation_id or str(uuid.uuid4())
    treatment_plan = _treatment_rule_engine.evaluate(
        disease_label=req.disease_label,
        zone_id=req.zone_id,
        target_position=req.target_position,
    )
    dispatch_result = _treatment_dispatcher.dispatch_plan(
        treatment_plan,
        observation_id=observation_id,
        requested_by=req.requested_by,
        auto_execute=bool(req.auto_execute),
    )
    return DiseaseTreatmentDispatchResponse(
        observation_id=observation_id,
        treatment_plan=treatment_plan,
        dispatch_result=dispatch_result,
    )

@router.post("/recommendations/{id}/approve")
def approve_recommendation(id: str, req: ApproveReq):
    # approve recommendation 정보를 계산해 반환한다.
    return {
        "data": _operations_service.approve_recommendation(
            id,
            reviewed_by=req.reviewed_by,
            auto_execute=bool(req.auto_execute),
        )
    }

@router.post("/recommendations/{id}/reject")
def reject_recommendation(id: str, req: RejectReq):
    # reject recommendation 정보를 계산해 반환한다.
    return {"data": {"id": id, "status": "REJECTED", "reviewed_by": req.reviewed_by, "comment": req.comment}}

@router.post("/watering")
def water_plants(req: WateringReq):
    # water 작물 정보를 계산해 반환한다.
    return {
        "data": _operations_service.create_manual_command(
            zone_id=req.zone_id,
            device_id=req.device_id,
            command_type="WATERING",
            target_value=req.target_value,
            value_unit=req.value_unit,
            requested_by=req.requested_by,
            request_source=req.request_source,
            recommendation_id=req.recommendation_id,
        )
    }

@router.post("/curtain")
def control_curtain(req: CurtainReq):
    # 제어 커튼 정보를 계산해 반환한다.
    return {
        "data": _operations_service.create_manual_command(
            zone_id=req.zone_id,
            device_id=req.device_id,
            command_type="CURTAIN",
            target_value=req.target_value,
            value_unit=req.value_unit,
            requested_by=req.requested_by,
            request_source=req.request_source,
        )
    }

@router.post("/fan")
def control_fan(req: FanReq):
    # 제어 환기팬 정보를 계산해 반환한다.
    return {
        "data": _operations_service.create_manual_command(
            zone_id=req.zone_id,
            device_id=req.device_id,
            command_type="FAN",
            target_value=req.target_value,
            value_unit=req.value_unit,
            requested_by=req.requested_by,
            request_source=req.request_source,
        )
    }

@router.post("/nutrients")
def control_nutrients(req: NutrientsReq):
    # 제어 nutrients 정보를 계산해 반환한다.
    return {
        "data": _operations_service.create_manual_command(
            zone_id=req.zone_id,
            device_id=req.device_id,
            command_type="NUTRIENTS",
            target_value=req.target_value,
            value_unit=req.value_unit,
            requested_by=req.requested_by,
            request_source=req.request_source,
            recommendation_id=req.recommendation_id,
        )
    }

@router.get("/history")
def get_actuation_history():
    # actuation 이력를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return {"data": _operations_service.list_actuation_history()}
