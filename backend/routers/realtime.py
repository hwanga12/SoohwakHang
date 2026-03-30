from fastapi import APIRouter, WebSocket

router = APIRouter()

@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    """대시보드 실시간 반영 (웹소켓)"""
    await websocket.accept()
    await websocket.send_json({"message": "Connected to WebSocket"})
    # 연결 유지 및 로직 추후 작성 가능
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")
