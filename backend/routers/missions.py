# 이 모듈은 백엔드의 미션 API 라우터를 정의하고, 요청을 서비스 계층과 연결한다.
from typing import List, Literal, Optional
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError

from database import SessionLocal
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
from models import Fruit, Mission, Plant, Robot, Zone

router = APIRouter()
MISSION_ID_NAMESPACE = uuid.UUID("3f8f6e6f-2087-4fd0-b0f5-c43dfcc5406b")


class PatrolStartReq(BaseModel):
    # patrol start 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    mission_id: Optional[str] = Field(default=None)
    robot_id: str
    zone_ids: List[str]
    loop_count: int = 1
    requested_by: str
    patrol_mode: Literal["diagnosis", "harvest"] = "diagnosis"


class PatrolStopReq(BaseModel):
    # patrol stop 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    command_id: Optional[str] = Field(default=None)
    robot_id: str
    requested_by: str
    reason: str


class ReturnHomeReq(BaseModel):
    # return home 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    command_id: Optional[str] = Field(default=None)
    robot_id: str
    requested_by: str
    home_waypoint_id: Optional[str] = Field(
        default=None,
        description="선택적 홈 waypoint override",
    )


class HarvestReq(BaseModel):
    # harvest 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    mission_id: Optional[str] = Field(default=None)
    robot_id: str
    plant_id: str
    fruit_id: str
    requested_by: str
    inspect_waypoint_id: Optional[str] = Field(default=None)
    inspect_waypoint_ids: List[str] = Field(default_factory=list)


def _raise_mission_http_error(exc: Exception) -> None:
    # raise 미션 http error 정보를 계산해 반환한다.
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
    # raise 로봇 명령 http error 정보를 계산해 반환한다.
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
    # 명령 OR raise를 외부 시스템이나 다음 처리 단계로 전달한다.
    try:
        return publish_robot_command(**kwargs)
    except Exception as exc:  # pragma: no cover - status mapping helper
        _raise_robot_command_http_error(exc)


def _publish_mission_or_raise(callback, **kwargs):
    # 미션 OR raise를 외부 시스템이나 다음 처리 단계로 전달한다.
    try:
        return callback(**kwargs)
    except Exception as exc:  # pragma: no cover - status mapping helper
        _raise_mission_http_error(exc)


def _normalize_db_status(value: str) -> str:
    # DB 상태를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(value).strip().upper()
    if normalized in {"SUCCEEDED"}:
        return "COMPLETED"
    if normalized in {"FAILED", "CANCELED", "RUNNING", "PENDING", "COMPLETED"}:
        return normalized
    return "PENDING"


def _mission_storage_uuid(mission_id: str) -> uuid.UUID:
    # 미션 storage uuid 정보를 계산해 반환한다.
    try:
        return uuid.UUID(str(mission_id).strip())
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(MISSION_ID_NAMESPACE, str(mission_id).strip())


def _resolve_existing_fk(db, model, value: str | None) -> str | None:
    # 현재 입력 조건을 바탕으로 existing FK를 계산하거나 결정한다.
    normalized = str(value or "").strip()
    if not normalized:
        return None
    row = db.query(model).filter(model.id == normalized).first()
    return normalized if row is not None else None


def _resolve_existing_zone_id(db, zone_id: str | None) -> str | None:
    # 현재 입력 조건을 바탕으로 existing 구역 ID를 계산하거나 결정한다.
    normalized = _resolve_existing_fk(db, Zone, zone_id)
    if normalized is not None:
        return normalized
    return _resolve_existing_fk(db, Zone, "farm_01")


def _get_or_create_robot_row(db, robot_name: str) -> Robot:
    # OR create robot ROW를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    robot = db.query(Robot).filter(Robot.name == robot_name).first()
    if robot is not None:
        return robot
    zone = db.query(Zone).filter(Zone.id == "farm_01").first()
    robot = Robot(name=robot_name, status="IDLE", battery_level=82.0, current_zone_id=None if zone is None else zone.id)
    db.add(robot)
    db.flush()
    return robot


def _upsert_mission_row(
    *,
    mission_id: str,
    robot_name: str,
    mission_type: str,
    status: str,
    target_zone_id: str | None = None,
    target_plant_id: str | None = None,
    target_fruit_id: str | None = None,
    progress_percent: int | None = None,
) -> None:
    # upsert 미션 row 정보를 계산해 반환한다.
    db = SessionLocal()
    try:
        mission_uuid = _mission_storage_uuid(mission_id)
        robot = _get_or_create_robot_row(db, robot_name)
        persisted_zone_id = _resolve_existing_zone_id(db, target_zone_id)
        persisted_plant_id = _resolve_existing_fk(db, Plant, target_plant_id)
        persisted_fruit_id = _resolve_existing_fk(db, Fruit, target_fruit_id)
        mission = db.query(Mission).filter(Mission.id == mission_uuid).first()
        if mission is None:
            mission = Mission(
                id=mission_uuid,
                robot_id=robot.id,
                mission_type=mission_type,
                target_zone_id=persisted_zone_id,
                target_plant_id=persisted_plant_id,
                target_fruit_id=persisted_fruit_id,
                status=status,
                progress_percent=progress_percent,
                started_at=None,
                completed_at=None,
            )
            db.add(mission)
        else:
            mission.robot_id = robot.id
            mission.mission_type = mission_type
            mission.target_zone_id = persisted_zone_id
            mission.target_plant_id = persisted_plant_id
            mission.target_fruit_id = persisted_fruit_id
            mission.status = status
            mission.progress_percent = progress_percent
        db.commit()
    except OperationalError:
        db.rollback()
        return
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _mission_row_payload(mission: Mission, *, requested_mission_id: str | None = None) -> dict:
    # 미션 row 페이로드 정보를 계산해 반환한다.
    payload_mission_id = str(requested_mission_id or mission.id)
    return {
        "available": True,
        "mission_id": payload_mission_id,
        "command_id": payload_mission_id,
        "mission_type": mission.mission_type,
        "request_type": mission.mission_type.lower(),
        "requested_type": mission.mission_type.lower(),
        "status": mission.status.lower(),
        "state": mission.status,
        "current_phase": "",
        "progress_pct": mission.progress_percent,
        "retry_count": None,
        "message": f"{mission.mission_type} 미션 상태",
        "operator_message": f"{mission.mission_type} 미션 상태",
        "detail_message": f"{mission.mission_type} 미션 상태",
        "error": "",
        "result": "",
        "updated_at": "",
        "zone_ids": [mission.target_zone_id] if mission.target_zone_id else [],
        "loop_count": None,
        "patrol_mode": "",
        "plant_id": mission.target_plant_id,
        "fruit_id": mission.target_fruit_id,
        "tomato_id": mission.target_fruit_id,
        "zone_id": mission.target_zone_id,
        "target_id": mission.target_fruit_id or mission.target_plant_id or mission.target_zone_id,
        "received_at": "",
        "started_at": "" if mission.started_at is None else mission.started_at.isoformat(),
        "completed_at": "" if mission.completed_at is None else mission.completed_at.isoformat(),
    }


def _enrich_from_db(runtime_payload: dict, mission_id: str) -> dict:
    # enrich db 정보를 계산해 반환한다.
    db = SessionLocal()
    try:
        mission = db.query(Mission).filter(Mission.id == _mission_storage_uuid(mission_id)).first()
        if mission is None:
            return runtime_payload
        runtime_payload.setdefault("plant_id", mission.target_plant_id)
        runtime_payload.setdefault("fruit_id", mission.target_fruit_id)
        runtime_payload.setdefault("tomato_id", mission.target_fruit_id)
        runtime_payload.setdefault("zone_id", mission.target_zone_id)
        runtime_payload.setdefault(
            "target_id",
            mission.target_fruit_id or mission.target_plant_id or mission.target_zone_id,
        )
        mission.status = _normalize_db_status(str(runtime_payload.get("status") or mission.status))
        mission.progress_percent = runtime_payload.get("progress_pct") or mission.progress_percent
        if mission.status == "RUNNING" and mission.started_at is None:
            mission.started_at = datetime.utcnow()
        if mission.status in {"COMPLETED", "FAILED", "CANCELED"} and mission.completed_at is None:
            mission.completed_at = datetime.utcnow()
        db.commit()
        return runtime_payload
    except Exception:
        db.rollback()
        return runtime_payload
    finally:
        db.close()


@router.post("/patrol/start")
def start_patrol(req: PatrolStartReq):
    # patrol 실행 흐름을 시작하거나 마무리한다.
    payload = _publish_mission_or_raise(
        publish_patrol_start_mission,
        mission_id=req.mission_id,
        robot_id=req.robot_id,
        zone_ids=req.zone_ids,
        loop_count=req.loop_count,
        requested_by=req.requested_by,
        patrol_mode=req.patrol_mode,
    )
    _upsert_mission_row(
        mission_id=str(payload["mission_id"]),
        robot_name=req.robot_id,
        mission_type="PATROL",
        status="PENDING",
        target_zone_id=req.zone_ids[0] if req.zone_ids else None,
        progress_percent=0,
    )
    return {"data": payload}


@router.post("/patrol/stop")
def stop_patrol(req: PatrolStopReq):
    # patrol 실행 흐름을 시작하거나 마무리한다.
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
    # return home 정보를 계산해 반환한다.
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
    # 수확 미션 정보를 계산해 반환한다.
    payload = _publish_mission_or_raise(
        publish_harvest_target_mission,
        mission_id=req.mission_id,
        robot_id=req.robot_id,
        plant_id=req.plant_id,
        fruit_id=req.fruit_id,
        requested_by=req.requested_by,
        inspect_waypoint_id=req.inspect_waypoint_id,
        inspect_waypoint_ids=req.inspect_waypoint_ids,
    )
    _upsert_mission_row(
        mission_id=str(payload["mission_id"]),
        robot_name=req.robot_id,
        mission_type="HARVEST",
        status="PENDING",
        target_zone_id="farm_01",
        target_plant_id=req.plant_id,
        target_fruit_id=req.fruit_id,
        progress_percent=0,
    )
    return {"data": payload}


@router.get("/{mission_id}")
def get_mission_status(mission_id: str):
    # 미션 상태를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    try:
        base_payload = read_mission_status_payload(mission_id)
    except Exception as exc:  # pragma: no cover - HTTP status mapping helper
        if isinstance(exc, FileNotFoundError):
            base_payload = None
        else:
            _raise_mission_http_error(exc)
            return {"data": None}

    try:
        if base_payload is None:
            db = SessionLocal()
            try:
                mission = db.query(Mission).filter(Mission.id == _mission_storage_uuid(mission_id)).first()
                if mission is None:
                    raise FileNotFoundError(f"mission status 파일을 찾지 못했습니다: {mission_id}")
                return {"data": _mission_row_payload(mission, requested_mission_id=mission_id)}
            finally:
                db.close()

        payload = merge_mission_status_with_harvest_action(mission_id, base_payload)
        return {"data": _enrich_from_db(payload, mission_id)}
    except Exception as exc:  # pragma: no cover - HTTP status mapping helper
        _raise_mission_http_error(exc)
