from fastapi import APIRouter

router = APIRouter()

@router.get("/latest")
def get_latest_environment():
    """구역별 최신 환경값 조회"""
    return {"message": "Latest environment metrics"}

@router.get("/history")
def get_environment_history():
    """상세 환경 시계열 대략적인 기록 조회"""
    return {"message": "Environment History data"}
