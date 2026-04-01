# 이 모듈은 백엔드의 알림 API 라우터를 정의하고, 요청을 서비스 계층과 연결한다.
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.perception.read_service import ObservationReadService

router = APIRouter()


class AlertAckReq(BaseModel):
    # alert ACK 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    acknowledged_by: str


def _get_read_service() -> ObservationReadService:
    # read 서비스를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return ObservationReadService()


@router.get("/")
def get_alerts():
    # alerts를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return {"data": _get_read_service().list_alerts()}


@router.post("/{alert_id}/ack")
def ack_alert(alert_id: str, req: AlertAckReq):
    # ack 알림 정보를 계산해 반환한다.
    service = _get_read_service()
    try:
        return {"data": service.acknowledge_alert(alert_id, req.acknowledged_by)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
