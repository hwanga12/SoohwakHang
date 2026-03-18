from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

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
