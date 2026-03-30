from fastapi import APIRouter, HTTPException

from services.perception.read_service import ObservationReadService

router = APIRouter()


def _get_read_service() -> ObservationReadService:
    return ObservationReadService()


@router.get("/")
def get_plants():
    """식물 목록과 최신 병해 관측 요약 조회"""
    return {"data": _get_read_service().list_plants()}


@router.get("/{plant_id}")
def get_plant_detail(plant_id: str):
    """특정 식물 상세 조회"""
    try:
        return {"data": _get_read_service().get_plant_detail(plant_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{plant_id}/observations")
def get_plant_observations(plant_id: str):
    """식물 관측 이력 조회"""
    try:
        return {"data": _get_read_service().get_plant_observations(plant_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
