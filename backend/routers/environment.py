from fastapi import APIRouter

from services.operations_service import OperationsService

router = APIRouter()
_service = OperationsService()


@router.get("/latest")
def get_latest_environment():
    """구역별 최신 환경값 조회"""
    return {"data": _service.get_latest_environment()}


@router.get("/history")
def get_environment_history():
    """상세 환경 시계열 기록 조회"""
    return {"data": _service.get_environment_history()}
