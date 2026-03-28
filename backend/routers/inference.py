import base64
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.actuation.schemas import Point3D
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
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_INPUT_ROOT = _REPO_ROOT / "artifacts" / "demo_inputs"
_DEMO_MANIFEST_PATH = _DEMO_INPUT_ROOT / "diagnosis_demo_manifest.json"


class DemoDiagnosisRequest(BaseModel):
    plant_id: str = Field(..., description="시연용 기준 이미지를 덮어쓸 대상 plant id")
    fruit_id: str = Field(default="", description="대상 fruit id. 비우면 manifest 기본값을 사용합니다.")
    robot_id: str = Field(default="AGR-02", description="시연 대상 로봇 ID")
    zone_id: str = Field(default="farm_01", description="시연 대상 zone id")
    requested_by: str = Field(default="frontend-demo", description="시연 요청 주체")
    target_position: Point3D | None = Field(
        default=None,
        description="질병 처리 계획 계산에 사용할 대상 좌표",
    )
    auto_execute_treatment: bool = Field(
        default=True,
        description="가능한 경우 IoT 처치 명령까지 함께 발행할지 여부",
    )


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


@router.post("/demo/confirm", response_model=ThinInferenceConfirmResponse)
def confirm_demo_diagnosis(
    request: DemoDiagnosisRequest,
) -> ThinInferenceConfirmResponse:
    """Run backend confirmation using a demo input image mapped to the selected plant."""
    try:
        demo_input = _resolve_demo_input(request.plant_id)
        image_path = demo_input["image_path"]
        raw_bytes = image_path.read_bytes()
        confirm_request = ThinInferenceConfirmRequest(
            robot_id=request.robot_id,
            zone_id=request.zone_id,
            plant_id=request.plant_id,
            fruit_id=request.fruit_id or demo_input["fruit_id"],
            frame_id="demo-input",
            target_position=request.target_position,
            requested_by=request.requested_by,
            auto_execute_treatment=request.auto_execute_treatment,
            preliminary_label=demo_input["preliminary_label"],
            preliminary_confidence=demo_input["preliminary_confidence"],
            image_base64=base64.b64encode(raw_bytes).decode("ascii"),
            image_format=image_path.suffix.lstrip(".") or "jpg",
        )
        return _service.confirm_detection(confirm_request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelFileMissingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelDependencyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_demo_input(plant_id: str) -> dict[str, object]:
    manifest = _load_demo_manifest()
    key = plant_id.strip()
    entry = manifest.get(key)
    if not isinstance(entry, dict):
        raise FileNotFoundError(f"시연용 demo input 매핑이 없습니다: {key}")

    image_path_text = str(entry.get("image_path", "")).strip()
    if not image_path_text:
        raise FileNotFoundError(f"시연용 demo input image_path 가 비어 있습니다: {key}")

    image_path = Path(image_path_text)
    if not image_path.is_absolute():
        image_path = (_DEMO_INPUT_ROOT / image_path).resolve()

    if not image_path.exists():
        raise FileNotFoundError(f"시연용 demo input 이미지를 찾지 못했습니다: {image_path}")

    fruit_id = str(entry.get("fruit_id", "")).strip()
    preliminary_label = str(
        entry.get("preliminary_label")
        or entry.get("expected_label")
        or ""
    ).strip()
    preliminary_confidence = float(entry.get("preliminary_confidence") or 0.95)
    return {
        "image_path": image_path,
        "fruit_id": fruit_id,
        "preliminary_label": preliminary_label,
        "preliminary_confidence": preliminary_confidence,
    }


def _load_demo_manifest() -> dict[str, object]:
    if not _DEMO_MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"시연용 demo manifest 파일이 없습니다: {_DEMO_MANIFEST_PATH}"
        )

    payload = json.loads(_DEMO_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("시연용 demo manifest 형식이 올바르지 않습니다.")
    return payload
