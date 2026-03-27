from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from services.ai_judgments.schemas import (
    AiJudgmentHistoryOut,
    AiJudgmentRecordOut,
    BulkHarvestDecisionRequest,
    BulkHarvestDecisionResponse,
    HarvestDecisionActionOut,
    HarvestDecisionActionRequest,
    RipenessJudgmentCreateRequest,
    RipenessJudgmentCreateResponse,
)
from services.ai_judgments.service import AiJudgmentService
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
_ai_judgment_service = AiJudgmentService()
JudgmentTypeParam = Literal["DISEASE", "RIPENESS", "HARVEST_DECISION"]


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


@router.post("/ripeness", response_model=RipenessJudgmentCreateResponse)
def store_ripeness_judgment(
    request: RipenessJudgmentCreateRequest,
) -> RipenessJudgmentCreateResponse:
    """Persist ripeness classification output and create a harvest decision if possible."""
    try:
        return _ai_judgment_service.create_ripeness_and_fuse(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/judgments/latest", response_model=AiJudgmentRecordOut | None)
def get_latest_ai_judgment(
    plant_id: str = Query(default=""),
    fruit_id: str = Query(default=""),
    judgment_type: JudgmentTypeParam | None = Query(default=None),
) -> AiJudgmentRecordOut | None:
    """Return the latest AI judgment for a plant/fruit target."""
    try:
        return _ai_judgment_service.get_latest_judgment(
            plant_id=plant_id,
            fruit_id=fruit_id,
            judgment_type=judgment_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/judgments/history", response_model=AiJudgmentHistoryOut)
def get_ai_judgment_history(
    plant_id: str = Query(default=""),
    fruit_id: str = Query(default=""),
    judgment_type: JudgmentTypeParam | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
) -> AiJudgmentHistoryOut:
    """Return recent AI judgments for frontend and debugging."""
    try:
        return _ai_judgment_service.get_judgment_history(
            plant_id=plant_id,
            fruit_id=fruit_id,
            judgment_type=judgment_type,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/harvest/individual", response_model=HarvestDecisionActionOut)
def create_individual_harvest_action(
    request: HarvestDecisionActionRequest,
) -> HarvestDecisionActionOut:
    """Run validity-aware harvest fusion for one plant/fruit target."""
    try:
        return _ai_judgment_service.create_individual_harvest_action(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/harvest/bulk", response_model=BulkHarvestDecisionResponse)
def create_bulk_harvest_action(
    request: BulkHarvestDecisionRequest,
) -> BulkHarvestDecisionResponse:
    """Run validity-aware harvest fusion sequentially for multiple targets."""
    try:
        return _ai_judgment_service.create_bulk_harvest_action(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
