# 이 모듈은 백엔드의 구역 API 라우터를 정의하고, 요청을 서비스 계층과 연결한다.
from fastapi import APIRouter

from services.operations_service import OperationsService

router = APIRouter()
_service = OperationsService()


@router.get("/")
def get_zones():
    # 구역 목록를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return {"data": _service.list_zones()}
