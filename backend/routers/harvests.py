from fastapi import APIRouter

from harvest_runtime_service import read_harvest_history_payload, read_harvest_stats_payload
from robot_runtime_state_service import (
    harvest_action_status_file_path,
    harvest_basket_state_file_path,
    harvest_latest_event_file_path,
    runtime_dir_from_env,
)
from services.operations_service import OperationsService

router = APIRouter()
_service = OperationsService()


def _has_runtime_harvest_state() -> bool:
    if harvest_action_status_file_path().exists():
        return True
    if harvest_basket_state_file_path().exists():
        return True
    if harvest_latest_event_file_path().exists():
        return True
    event_dir = runtime_dir_from_env() / "harvest_events"
    return any(event_dir.glob("*.json"))


@router.get("/")
def get_harvests():
    """수확 이력 조회"""
    if _has_runtime_harvest_state():
        return {"data": read_harvest_history_payload()}
    return {"data": _service.list_harvest_history()}


@router.get("/stats")
def get_harvest_stats():
    """일별/주별 수확 통계 조회"""
    if _has_runtime_harvest_state():
        return {"data": read_harvest_stats_payload()}
    return {"data": _service.get_harvest_stats()}
