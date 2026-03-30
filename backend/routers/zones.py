from fastapi import APIRouter

from services.operations_service import OperationsService

router = APIRouter()
_service = OperationsService()


@router.get("/")
def get_zones():
    """현재 운영 구역 목록과 대표 pose를 반환합니다."""
    return {"data": _service.list_zones()}
