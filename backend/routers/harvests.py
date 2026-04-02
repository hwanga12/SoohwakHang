# 이 모듈은 백엔드의 수확 API 라우터를 정의하고, 요청을 서비스 계층과 연결한다.
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
    # 런타임 데이터 harvest 상태가 포함되어 있는지 여부를 판단한다.
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
    # harvests를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    if _has_runtime_harvest_state():
        return {"data": read_harvest_history_payload()}
    return {"data": _service.list_harvest_history()}


@router.get("/stats")
def get_harvest_stats():
    # harvest stats를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    if _has_runtime_harvest_state():
        return {"data": read_harvest_stats_payload()}
    return {"data": _service.get_harvest_stats()}
