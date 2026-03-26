from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from harvest_runtime_service import merge_mission_status_with_harvest_action
from mission_bridge_service import (
    DuplicateMissionIdError,
    MissionBridgeConflictError,
    MissionBridgeUnavailableError,
    MissionBridgeValidationError,
    publish_harvest_target_mission,
    publish_patrol_start_mission,
    read_mission_status_payload,
)
from robot_command_bridge_service import (
    DuplicateCommandIdError,
    RobotCommandConflictError,
    RobotCommandUnavailableError,
    RobotCommandValidationError,
    publish_robot_command,
)

router = APIRouter()


class PatrolStartReq(BaseModel):
    mission_id: Optional[str] = Field(default=None)
    robot_id: str
    zone_ids: List[str]
    loop_count: int = 1
    requested_by: str
    patrol_mode: Literal["diagnosis", "harvest"] = "diagnosis"


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
    mission_id: Optional[str] = Field(default=None)
    robot_id: str
    plant_id: str
    fruit_id: str
    requested_by: str


def _raise_mission_http_error(exc: Exception) -> None:
    if isinstance(exc, DuplicateMissionIdError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, MissionBridgeConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, MissionBridgeValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, MissionBridgeUnavailableError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


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


def _publish_mission_or_raise(callback, **kwargs):
    try:
        return callback(**kwargs)
    except Exception as exc:  # pragma: no cover - status mapping helper
        _raise_mission_http_error(exc)


@router.post("/patrol/start")
def start_patrol(req: PatrolStartReq):
    """operator patrol 미션 요청을 runtime bridge request 파일로 기록합니다."""
    payload = _publish_mission_or_raise(
        publish_patrol_start_mission,
        mission_id=req.mission_id,
        robot_id=req.robot_id,
        zone_ids=req.zone_ids,
        loop_count=req.loop_count,
        requested_by=req.requested_by,
        patrol_mode=req.patrol_mode,
    )
    return {"data": payload}


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
    """operator harvest target 요청을 runtime bridge request 파일로 기록합니다."""
    payload = _publish_mission_or_raise(
        publish_harvest_target_mission,
        mission_id=req.mission_id,
        robot_id=req.robot_id,
        plant_id=req.plant_id,
        fruit_id=req.fruit_id,
        requested_by=req.requested_by,
    )
    return {"data": payload}


@router.get("/{mission_id}")
def get_mission_status(mission_id: str):
    """runtime bridge가 기록한 mission status 파일을 조회합니다."""
    try:
        base_payload = read_mission_status_payload(mission_id)
    except Exception as exc:  # pragma: no cover - HTTP status mapping helper
        if isinstance(exc, FileNotFoundError):
            base_payload = None
        else:
            _raise_mission_http_error(exc)
            return {"data": None}

    try:
        return {"data": merge_mission_status_with_harvest_action(mission_id, base_payload)}
    except Exception as exc:  # pragma: no cover - HTTP status mapping helper
        _raise_mission_http_error(exc)
