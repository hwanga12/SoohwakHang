from fastapi import APIRouter

router = APIRouter()

@router.get("/devices")
def get_iot_devices():
    """장치 현재 상태 단일화 목록 조회"""
    return {"message": "List of all IoT Devices"}
