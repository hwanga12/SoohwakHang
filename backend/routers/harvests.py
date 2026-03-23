from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_harvests():
    """수확 이력 조회"""
    return {"message": "Harvest history list"}

@router.get("/stats")
def get_harvest_stats():
    """일별/주별 수확 통계 조회"""
    return {"message": "Harvest statistics"}
