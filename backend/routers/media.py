from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.perception.read_service import ObservationReadService

router = APIRouter()


def _get_read_service() -> ObservationReadService:
    return ObservationReadService()


@router.get("/{asset_id}")
def get_media(asset_id: str):
    """병해 관측 이미지 파일 반환"""
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
