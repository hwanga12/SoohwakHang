# 이 모듈은 백엔드의 실시간 API 라우터를 정의하고, 요청을 서비스 계층과 연결한다.
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mission_bridge_service import read_latest_mission_status_payload
from robot_command_bridge_service import read_latest_command_status_payload
from robot_map_service import read_status_payload
from robot_runtime_state_service import read_control_state_payload
from ros_protocol_bridge import get_ros_protocol_bridge

router = APIRouter()

@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    # websocket endpoint 정보를 계산해 반환한다.
    await websocket.accept()
    await websocket.send_json({"type": "connected", "message": "Connected to AgriBot live stream"})
    while True:
        try:
            payload = {
                "type": "live_snapshot",
                "data": {
                    "transport": get_ros_protocol_bridge().get_live_snapshot(),
                    "robot_command_status": read_latest_command_status_payload(),
                    "control_state": read_control_state_payload(),
                    "mission_bridge_status": read_latest_mission_status_payload(),
                },
            }
            try:
                payload["data"]["robot_status"] = read_status_payload()
            except Exception:
                payload["data"]["robot_status"] = None

            await websocket.send_json(payload)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except TimeoutError:
                continue
        except WebSocketDisconnect:
            break
