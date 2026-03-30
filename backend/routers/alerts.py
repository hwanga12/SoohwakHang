from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.perception.read_service import ObservationReadService

router = APIRouter()


class AlertAckReq(BaseModel):
    acknowledged_by: str


def _get_read_service() -> ObservationReadService:
    return ObservationReadService()


@router.get("/")
def get_alerts():
    """병해 관측 결과에서 생성한 실제 알림 목록 조회"""
    return {"data": _get_read_service().list_alerts()}


@router.post("/{alert_id}/ack")
def ack_alert(alert_id: str, req: AlertAckReq):
    """알림 읽음 처리"""
    service = _get_read_service()
    try:
        return {"data": service.acknowledge_alert(alert_id, req.acknowledged_by)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
