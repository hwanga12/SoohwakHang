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

router = APIRouter()
_treatment_rule_engine = DiseaseTreatmentRuleEngine()
_treatment_dispatcher = TreatmentCommandDispatcher()

class ApproveReq(BaseModel):
    reviewed_by: str
    auto_execute: bool = True

class RejectReq(BaseModel):
    reviewed_by: str
    comment: Optional[str] = None

class WateringReq(BaseModel):
    zone_id: str
    device_id: str
    target_value: float
    value_unit: str = "ml"
    requested_by: str
    request_source: str
    recommendation_id: Optional[str] = None

class CurtainReq(BaseModel):
    zone_id: str
    device_id: str
    target_value: float
    value_unit: str = "percent"
    requested_by: str
    request_source: str

class FanReq(BaseModel):
    zone_id: str
    device_id: str
    target_value: float
    value_unit: str = "level"
    requested_by: str
    request_source: str

class NutrientsReq(BaseModel):
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
    """IoT 자동 추천 목록 조회"""
    return {"message": "List of recommendations"}

@router.post("/treatment-plan", response_model=DiseaseTreatmentPlan)
def build_treatment_plan(req: DiseaseTreatmentPlanRequest):
    """병해 규칙 엔진으로 분사 계획을 계산"""
    return _treatment_rule_engine.evaluate(
        disease_label=req.disease_label,
        zone_id=req.zone_id,
        target_position=req.target_position,
    )

@router.post("/disease-treatment/dispatch", response_model=DiseaseTreatmentDispatchResponse)
def dispatch_disease_treatment(req: DiseaseTreatmentDispatchRequest):
    """병해 규칙 엔진을 평가하고 준비된 분사 명령을 IoT로 전달"""
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
    """추천 승인 후 실제 명령으로 전환"""
    return {"message": f"Approved recommendation {id}"}

@router.post("/recommendations/{id}/reject")
def reject_recommendation(id: str, req: RejectReq):
    """추천 거절"""
    return {"message": f"Rejected recommendation {id}"}

@router.post("/watering")
def water_plants(req: WateringReq):
    """급수 명령 생성"""
    return {"message": "Watering command sent"}

@router.post("/curtain")
def control_curtain(req: CurtainReq):
    """천장 커튼 제어명령 생성"""
    return {"message": "Curtain command sent"}

@router.post("/fan")
def control_fan(req: FanReq):
    """환기팬 제어 명령 생성"""
    return {"message": "Fan command sent"}

@router.post("/nutrients")
def control_nutrients(req: NutrientsReq):
    """영양제 실행 명령 생성"""
    return {"message": "Nutrients command sent"}

@router.get("/history")
def get_actuation_history():
    """장치 실행 이력 조회"""
    return {"message": "List of actuation history"}
