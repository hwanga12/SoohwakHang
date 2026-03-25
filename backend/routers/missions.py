from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from robot_command_bridge_service import (
    DuplicateCommandIdError,
    RobotCommandConflictError,
    RobotCommandUnavailableError,
    RobotCommandValidationError,
    publish_robot_command,
)

router = APIRouter()


class PatrolStartReq(BaseModel):
    robot_id: str
    zone_ids: List[str]
    loop_count: int = 1
    requested_by: str


class PatrolStopReq(BaseModel):
    command_id: Optional[str] = Field(default=None)
    robot_id: str
    requested_by: str
    reason: str


class ReturnHomeReq(BaseModel):
    command_id: Optional[str] = Field(default=None)
    robot_id: str
    requested_by: str
    home_waypoint_id: Optional[str] = Field(
        default=None,
        description="선택적 홈 waypoint override",
    )


class HarvestReq(BaseModel):
    robot_id: str
    plant_id: str
    fruit_id: str
    requested_by: str


def _raise_robot_command_http_error(exc: Exception) -> None:
    if isinstance(exc, DuplicateCommandIdError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, RobotCommandConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, RobotCommandValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, RobotCommandUnavailableError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


def _publish_command_or_raise(**kwargs):
    try:
        return publish_robot_command(**kwargs)
    except Exception as exc:  # pragma: no cover - status mapping helper
        _raise_robot_command_http_error(exc)


@router.post("/patrol/start")
def start_patrol(req: PatrolStartReq):
    """순찰 시작 미션 생성 및 MQTT 발행"""
    return {"data": {"mission_id": "mission-patrol-example", "status": "PENDING"}}


@router.post("/patrol/stop")
def stop_patrol(req: PatrolStopReq):
    """순찰 중지 호환 endpoint. 내부적으로 pause_patrol 명령 publish 결과를 반환합니다."""
    payload = _publish_command_or_raise(
        command_id=req.command_id,
        robot_id=req.robot_id,
        command_type="pause_patrol",
        requested_by=req.requested_by,
        payload={"reason": req.reason},
    )
    return {"data": payload}


@router.post("/return-home")
def return_home(req: ReturnHomeReq):
    """홈 복귀 호환 endpoint. 내부적으로 return_home 명령 publish 결과를 반환합니다."""
    payload = _publish_command_or_raise(
        command_id=req.command_id,
        robot_id=req.robot_id,
        command_type="return_home",
        requested_by=req.requested_by,
        payload={"home_waypoint_id": req.home_waypoint_id}
        if req.home_waypoint_id
        else None,
    )
    return {"data": payload}


@router.post("/harvest")
def harvest_mission(req: HarvestReq):
    """수확 단일 미션"""
    return {"data": {"mission_id": "mission-harvest-example", "status": "PENDING"}}


@router.get("/{mission_id}")
def get_mission_status(mission_id: str):
    """특정 미션 진행도/상태 조회"""
    return {"message": f"Mission {mission_id} status"}
