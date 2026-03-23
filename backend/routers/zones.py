from fastapi import APIRouter

router = APIRouter()

@router.get("/")
def get_zones():
    """농장 구역 목록 및 범위 조회"""
    return {"data": [{"id": "zone_A", "name": "A구역"}]}
