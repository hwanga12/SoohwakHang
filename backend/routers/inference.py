from fastapi import APIRouter, HTTPException

from services.perception.inference_service import (
    ModelDependencyError,
    ModelFileMissingError,
    MainInferenceService,
)
from services.perception.schemas import (
    ThinInferenceConfirmRequest,
    ThinInferenceConfirmResponse,
)

router = APIRouter()
_service = MainInferenceService()


@router.post("/confirm", response_model=ThinInferenceConfirmResponse)
def confirm_thin_inference(
    request: ThinInferenceConfirmRequest,
) -> ThinInferenceConfirmResponse:
    """Run the backend-grade confirmation pass for a thin robot detection."""
    try:
        return _service.confirm_detection(request)
    except ModelFileMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelDependencyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
