from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()

class PatrolStartReq(BaseModel):
    robot_id: str
    zone_ids: List[str]
    loop_count: int = 1
    requested_by: str

class PatrolStopReq(BaseModel):
    robot_id: str
    requested_by: str
    reason: str

class ReturnHomeReq(BaseModel):
    robot_id: str
    requested_by: str

class HarvestReq(BaseModel):
    robot_id: str
    plant_id: str
    fruit_id: str
    requested_by: str


@router.post("/patrol/start")
def start_patrol(req: PatrolStartReq):
    """순찰 시작 미션 생성 및 MQTT 발행"""
    return {"data": {"mission_id": "mission-patrol-example", "status": "PENDING"}}

@router.post("/patrol/stop")
def stop_patrol(req: PatrolStopReq):
    """순찰 정지"""
    return {"message": "Patrol Stopped"}

@router.post("/return-home")
def return_home(req: ReturnHomeReq):
    """스테이션 복귀 미션"""
    return {"message": "Returning home"}

@router.post("/harvest")
def harvest_mission(req: HarvestReq):
    """수확 단일 미션"""
    return {"data": {"mission_id": "mission-harvest-example", "status": "PENDING"}}

@router.get("/{mission_id}")
def get_mission_status(mission_id: str):
    """특정 미션 진행도/상태 조회"""
    return {"message": f"Mission {mission_id} status"}
