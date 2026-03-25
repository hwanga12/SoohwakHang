from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from zone_service import ZoneResolutionError, read_zones_payload

router = APIRouter()


@router.get("/")
def get_zones(
    map_id: Optional[str] = Query(
        default=None,
        description="구역 representative pose를 계산할 기준 map_id. 기본값은 현재 운영 맵입니다.",
        examples=["farm_map"],
    )
):
    """현재 맵 구조와 patrol waypoint 기준으로 구역 목록과 대표 pose를 반환합니다."""
    try:
        return {"data": read_zones_payload(map_id)}
    except (FileNotFoundError, ValueError, ZoneResolutionError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
