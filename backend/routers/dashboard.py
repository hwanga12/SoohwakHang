from fastapi import APIRouter

from services.operations_service import OperationsService

router = APIRouter()
_service = OperationsService()


@router.get("/summary")
def get_dashboard_summary():
    """메인 화면 요약 데이터를 제공합니다."""
    return {"data": _service.get_dashboard_summary()}
