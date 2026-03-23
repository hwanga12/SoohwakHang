from fastapi import APIRouter

router = APIRouter()

@router.get("/summary")
def get_dashboard_summary():
    """메인 화면 요약 데이터를 제공합니다."""
    return {"message": "Dashboard Summary Array"}
