from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from robot_map_service import (
    image_path_for_map,
    read_layers_payload,
    read_map_payload,
    read_pose_payload,
    read_status_payload,
)

router = APIRouter()


class RobotCommandReq(BaseModel):
    robot_id: str
    command_type: str
    requested_by: str
    target_zone_id: Optional[str] = None
    payload: Optional[dict] = None


@router.get("/status")
def get_robot_status(map_id: Optional[str] = Query(default=None)):
    """현재 로봇 상태 카드와 실시간 상태 화면용 데이터 조회"""
    try:
        return {"data": read_status_payload(map_id)}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pose")
def get_robot_pose(map_id: Optional[str] = Query(default=None)):
    """지도 위에 로봇 위치와 방향 표기 용도 데이터"""
    try:
        return {"data": read_pose_payload(map_id)}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/map")
def get_robot_map(map_id: Optional[str] = Query(default=None)):
    """정적 occupancy map 메타데이터 반환"""
    try:
        return {"data": read_map_payload(map_id)}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/map/raw")
def get_robot_map_raw(map_id: Optional[str] = Query(default=None)):
    """정적 occupancy map 원본 PGM 반환"""
    try:
        image_path = image_path_for_map(map_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        image_path,
        media_type="image/x-portable-graymap",
        filename=image_path.name,
    )


@router.get("/map/layers")
def get_robot_map_layers(map_id: Optional[str] = Query(default=None)):
    """식물, 급수 포인트, row guide 등 semantic layer 반환"""
    try:
        return {"data": read_layers_payload(map_id)}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/commands")
def post_robot_command(command: RobotCommandReq):
    """로봇 제어 명령(긴급 정지, 재개, 수동 이동 등) 발행"""
    return {
        "data": {
            "accepted": True,
            "command_type": command.command_type,
            "published_topic": "agribot/commands/mission",
        }
    }
