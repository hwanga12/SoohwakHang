# 이 모듈은 백엔드의 미디어 API 라우터를 정의하고, 요청을 서비스 계층과 연결한다.
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.perception.read_service import ObservationReadService

router = APIRouter()


def _get_read_service() -> ObservationReadService:
    # read 서비스를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return ObservationReadService()


@router.get("/{asset_id}")
def get_media(asset_id: str):
    # media를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    service = _get_read_service()
    try:
        image_path = service.resolve_media_path(asset_id)
        metadata = service.media_response_meta(asset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        image_path,
        media_type=metadata["media_type"],
        filename=metadata["filename"],
    )
