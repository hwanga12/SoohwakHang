from fastapi import APIRouter
from typing import Optional

router = APIRouter()

@router.get("/")
def get_plants():
    """식물 목록/필터 조회"""
    return {"message": "Plant list and filters"}

@router.get("/{plant_id}")
def get_plant_detail(plant_id: str):
    """특정 식물 상세 조회"""
    return {"message": f"Plant {plant_id} details"}

@router.get("/{plant_id}/observations")
def get_plant_observations(plant_id: str):
    """식물 관측 이력 조회"""
    return {"message": f"Observations for plant {plant_id}"}
