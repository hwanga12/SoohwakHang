from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from robot_command_bridge_service import (
    DuplicateCommandIdError,
    RobotCommandConflictError,
    RobotCommandUnavailableError,
    RobotCommandValidationError,
    publish_robot_command,
    read_latest_command_status_payload,
)
from robot_navigation_preview_service import read_navigation_preview_payload
from robot_map_service import (
    image_path_for_map,
    read_layers_payload,
    read_map_payload,
    read_pose_payload,
    read_status_payload,
)
from robot_runtime_state_service import RobotRuntimeStateError, read_control_state_payload

router = APIRouter()

TARGET_POSE_EXAMPLE = {
    "target_pose": {
        "x": 0.0,
        "y": -8.6,
        "yaw": 1.5708,
        "frame_id": "map",
    }
}


class RobotCommandReq(BaseModel):
    command_id: Optional[str] = Field(
        default=None,
        description="중복 실행 방지를 위한 선택적 command id. 비워두면 backend가 생성합니다.",
        examples=["robot-cmd-1742879830000-a1b2c3d4"],
    )
    robot_id: str = Field(..., description="대상 로봇 ID", examples=["AGR-02"])
    command_type: Literal[
        "emergency_stop",
        "navigate_to_pose",
        "pause",
        "pause_motion",
        "pause_patrol",
        "resume",
        "resume_motion",
        "resume_patrol",
        "return_home",
        "move_to_zone",
    ] = Field(..., description="웹 또는 제어 패널에서 요청한 로봇 명령 타입")
    requested_by: str = Field(..., description="명령 요청 주체", examples=["frontend-operator"])
    target_zone_id: Optional[str] = Field(
        default=None,
        description="move_to_zone 에서 사용할 대상 zone id",
        examples=["farm_01"],
    )
    map_id: Optional[str] = Field(
        default=None,
        description="bounds 검증과 zone representative pose 계산에 사용할 map id",
        examples=["farm_map"],
    )
    target_pose: Optional[dict[str, Any]] = Field(
        default=None,
        description="navigate_to_pose 에서 바로 전달할 목표 pose. payload.target_pose 와 동일 계약입니다.",
        examples=[TARGET_POSE_EXAMPLE["target_pose"]],
    )
    payload: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "navigate_to_pose 에서는 payload.target_pose {x, y, yaw, frame_id} 를 사용합니다. "
            "return_home 에서는 선택적으로 payload.home_waypoint_id 를 지원합니다."
        ),
        examples=[TARGET_POSE_EXAMPLE, {"home_waypoint_id": "farm_01_home"}],
    )
    preempt_current_navigation: Optional[bool] = Field(
        default=None,
        description=(
            "true 이면 현재 주행 중인 patrol/manual NavigateToPose 를 선점합니다. "
            "생략 시 navigate_to_pose, move_to_zone, return_home 은 기본 true 입니다."
        ),
        examples=[True],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "robot_id": "AGR-02",
                    "requested_by": "frontend-operator",
                    "command_type": "emergency_stop",
                },
                {
                    "robot_id": "AGR-02",
                    "requested_by": "frontend-operator",
                    "command_type": "pause",
                },
                {
                    "robot_id": "AGR-02",
                    "requested_by": "frontend-operator",
                    "command_type": "move_to_zone",
                    "target_zone_id": "farm_01",
                },
                {
                    "robot_id": "AGR-02",
                    "requested_by": "frontend-operator",
                    "command_type": "navigate_to_pose",
                    "target_pose": TARGET_POSE_EXAMPLE["target_pose"],
                    "preempt_current_navigation": True,
                },
            ]
        }
    }


class RobotControlReq(BaseModel):
    command_id: Optional[str] = Field(
        default=None,
        description="중복 실행 방지를 위한 선택적 command id. 비워두면 backend가 생성합니다.",
    )
    robot_id: str = Field(..., description="대상 로봇 ID", examples=["AGR-02"])
    requested_by: str = Field(..., description="명령 요청 주체", examples=["frontend-operator"])


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


def _publish_command_or_raise(**kwargs: Any) -> dict[str, Any]:
    try:
        return publish_robot_command(**kwargs)
    except Exception as exc:  # pragma: no cover - status mapping helper
        _raise_robot_command_http_error(exc)


@router.get("/status")
def get_robot_status(map_id: Optional[str] = Query(default=None)):
    """현재 로봇 상태 카드와 실시간 상태 화면용 authoritative 상태 조회"""
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


@router.get("/navigation-preview")
def get_robot_navigation_preview(map_id: Optional[str] = Query(default=None)):
    """현재 로봇 기준으로 짧게 잘라낸 예상 주행 경로를 반환"""
    try:
        return {"data": read_navigation_preview_payload(map_id)}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/control/status")
def get_robot_control_status():
    """agribot_ws runtime executor가 기록한 현재 제어 상태 조회"""
    try:
        return {"data": read_control_state_payload()}
    except RobotRuntimeStateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/control/emergency-stop")
def post_robot_emergency_stop(command: RobotControlReq):
    """비상 정지 버튼 전용 endpoint"""
    payload = _publish_command_or_raise(
        command_id=command.command_id,
        robot_id=command.robot_id,
        command_type="emergency_stop",
        requested_by=command.requested_by,
    )
    return {"data": payload}


@router.post("/control/pause")
def post_robot_pause(command: RobotControlReq):
    """일시정지 버튼 전용 endpoint"""
    payload = _publish_command_or_raise(
        command_id=command.command_id,
        robot_id=command.robot_id,
        command_type="pause",
        requested_by=command.requested_by,
    )
    return {"data": payload}


@router.post("/control/resume")
def post_robot_resume(command: RobotControlReq):
    """재개 버튼 전용 endpoint"""
    payload = _publish_command_or_raise(
        command_id=command.command_id,
        robot_id=command.robot_id,
        command_type="resume",
        requested_by=command.requested_by,
    )
    return {"data": payload}


@router.post("/commands")
def post_robot_command(command: RobotCommandReq):
    """파일 브리지 기반으로 로봇 수동/제어 명령을 runtime executor에 전달합니다."""
    payload = _publish_command_or_raise(
        command_id=command.command_id,
        robot_id=command.robot_id,
        command_type=command.command_type,
        requested_by=command.requested_by,
        target_zone_id=command.target_zone_id,
        map_id=command.map_id,
        payload=command.payload,
        target_pose=command.target_pose,
        preempt_current_navigation=command.preempt_current_navigation,
    )
    return {"data": payload}


@router.get("/commands/latest")
def get_latest_robot_command_status():
    """runtime executor가 마지막으로 기록한 명령 상태와 현재 control state를 함께 조회합니다."""
    try:
        return {"data": read_latest_command_status_payload()}
    except RobotRuntimeStateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
