from fastapi import APIRouter

from services.operations_service import OperationsService

router = APIRouter()
_service = OperationsService()


@router.get("/devices")
def get_iot_devices():
    """장치 현재 상태 단일화 목록 조회"""
    return {"data": _service.list_iot_devices()}
