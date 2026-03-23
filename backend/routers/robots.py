from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class RobotCommandReq(BaseModel):
    robot_id: str
    command_type: str
    requested_by: str
    target_zone_id: Optional[str] = None
    payload: Optional[dict] = None

@router.get("/status")
def get_robot_status():
    """현재 로봇 상태 카드와 실시간 상태 화면용 데이터 조회"""
    return {"message": "Robot Status"}

@router.get("/pose")
def get_robot_pose():
    """지도 위에 로봇 위치와 방향 표기 용도 데이터"""
    return {"message": "Robot Pose Data"}

@router.post("/commands")
def post_robot_command(command: RobotCommandReq):
    """로봇 제어 명령(긴급 정지, 재개, 수동 이동 등) 발행"""
    return {
        "data": {
            "accepted": True,
            "command_type": command.command_type,
            "published_topic": "agribot/commands/mission"
        }
    }
