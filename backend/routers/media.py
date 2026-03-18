from fastapi import APIRouter

router = APIRouter()

@router.get("/{asset_id}")
def get_media(asset_id: str):
    """이미지 메타데이터 또는 다운로드 URL 조회"""
    return {"message": f"Media data for {asset_id}"}
