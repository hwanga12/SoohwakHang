from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class AlertAckReq(BaseModel):
    acknowledged_by: str

@router.get("/")
def get_alerts():
    """알림 목록 조회"""
    return {"message": "List of alerts"}

@router.post("/{alert_id}/ack")
def ack_alert(alert_id: str, req: AlertAckReq):
    """알림 읽음 처리"""
    return {
        "data": {
            "id": alert_id,
            "acknowledged_by": req.acknowledged_by
        }
    }
