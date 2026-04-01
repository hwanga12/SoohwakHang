# 이 모듈은 백엔드의 작물 API 라우터를 정의하고, 요청을 서비스 계층과 연결한다.
from fastapi import APIRouter, HTTPException

from services.perception.read_service import ObservationReadService

router = APIRouter()


def _get_read_service() -> ObservationReadService:
    # read 서비스를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return ObservationReadService()


@router.get("/")
def get_plants():
    # 작물 개체 목록를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return {"data": _get_read_service().list_plants()}


@router.get("/{plant_id}")
def get_plant_detail(plant_id: str):
    # 작물 개체 detail를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    try:
        return {"data": _get_read_service().get_plant_detail(plant_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{plant_id}/observations")
def get_plant_observations(plant_id: str):
    # 작물 개체 observations를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    try:
        return {"data": _get_read_service().get_plant_observations(plant_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
