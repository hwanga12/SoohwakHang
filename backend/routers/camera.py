from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.perception.read_service import ObservationReadService

router = APIRouter()


def _get_read_service() -> ObservationReadService:
    return ObservationReadService()


@router.get("/latest")
def get_latest_camera_snapshot():
    """Gazebo 카메라의 최신 전체 프레임 메타데이터 조회"""
    return {"data": _get_read_service().get_live_camera_snapshot()}


@router.get("/latest/frame")
def get_latest_camera_frame():
    """Gazebo 카메라의 최신 전체 프레임 이미지 반환"""
    service = _get_read_service()
    try:
        image_path = service.resolve_live_camera_path()
        metadata = service.live_camera_response_meta()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return FileResponse(
        image_path,
        media_type=metadata["media_type"],
        filename=metadata["filename"],
    )
