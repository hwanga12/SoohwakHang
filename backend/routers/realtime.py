# 이 모듈은 백엔드의 실시간 API 라우터를 정의하고, 요청을 서비스 계층과 연결한다.
from fastapi import APIRouter, WebSocket

router = APIRouter()

@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    # websocket endpoint 정보를 계산해 반환한다.
    await websocket.accept()
    await websocket.send_json({"message": "Connected to WebSocket"})
    # 연결 유지 및 로직 추후 작성 가능
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")
