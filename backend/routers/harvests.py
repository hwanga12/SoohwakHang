from fastapi import APIRouter

from harvest_runtime_service import read_harvest_history_payload, read_harvest_stats_payload

router = APIRouter()


@router.get("/")
def get_harvests():
    """HarvestTomato 액션과 basket state 기준 실제 수확 이력 조회"""
    return {"data": read_harvest_history_payload()}


@router.get("/stats")
def get_harvest_stats():
    """바구니 상태, 남은 ready fruit, 최근 수확 결과 통계 조회"""
    return {"data": read_harvest_stats_payload()}
