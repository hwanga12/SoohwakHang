from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import json
import os
from pathlib import Path
from typing import Any
import uuid

from services.actuation.dispatcher import TreatmentCommandDispatcher
from services.actuation.rule_engine import DiseaseTreatmentRuleEngine
from services.perception.persistence import ObservationPersistenceService
from services.perception.schemas import (
    BoundingBox,
    ThinInferenceConfirmRequest,
    ThinInferenceConfirmResponse,
)


_DEFAULT_MODEL_RELATIVE_PATH = Path('artifacts/models/tomato_disease/v1/best.pt')
_DEFAULT_RUNTIME_RELATIVE_PATH = Path('artifacts/runtime/backend')
_DEFAULT_IGNORED_CLASSES = 'healthy,normal,normal_leaf,healthy_leaf'


class ModelDependencyError(RuntimeError):
    """Raised when the runtime inference dependency is not installed."""


class ModelFileMissingError(FileNotFoundError):
    """Raised when the shared model path does not exist."""


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    bbox: tuple[float, float, float, float]


class MainInferenceService:
    """Backend confirmation pass that re-runs the shared YOLO weights."""

    def __init__(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        default_model_path = repo_root / _DEFAULT_MODEL_RELATIVE_PATH
        default_runtime_dir = repo_root / _DEFAULT_RUNTIME_RELATIVE_PATH

        self._model_path = Path(
            os.environ.get('AGRIBOT_TOMATO_MODEL_PATH', str(default_model_path))
        ).expanduser()
        self._runtime_dir = Path(
            os.environ.get('AGRIBOT_BACKEND_RUNTIME_DIR', str(default_runtime_dir))
        ).expanduser()
        self._imgsz = int(os.environ.get('AGRIBOT_MAIN_IMGSZ', '960'))
        self._confidence_threshold = float(
            os.environ.get('AGRIBOT_MAIN_CONFIDENCE', '0.25')
        )
        self._ignored_classes = _parse_label_list(
            os.environ.get('AGRIBOT_MAIN_IGNORED_CLASSES', _DEFAULT_IGNORED_CLASSES)
        )
        self._model: Any | None = None
        self._treatment_rule_engine = DiseaseTreatmentRuleEngine()
        self._treatment_dispatcher = TreatmentCommandDispatcher()
        self._persistence_service = ObservationPersistenceService()

    def confirm_detection(
        self,
        request: ThinInferenceConfirmRequest,
    ) -> ThinInferenceConfirmResponse:
        image_bytes = _decode_base64_image(request.image_base64)
        observation_id = request.observation_id or str(uuid.uuid4())
        reviewed_at = datetime.now(timezone.utc)
        suffix = _normalize_image_suffix(request.image_format)

        date_dir = self._runtime_dir / reviewed_at.strftime('%Y%m%d')
        date_dir.mkdir(parents=True, exist_ok=True)
        image_path = date_dir / f'{observation_id}.{suffix}'
        image_path.write_bytes(image_bytes)

        override_label = request.test_override_final_label.strip()
        detections: list[Detection]
        final_detection: Detection | None
        if override_label:
            detections = []
            final_detection = None
        else:
            detections = self._infer(image_path)
            final_detection = _choose_final_detection(
                detections,
                preliminary_label=request.preliminary_label,
                ignored_classes=self._ignored_classes,
            )

        if override_label:
            final_label = override_label
            final_confidence = float(request.test_override_final_confidence)
            decision_source = 'test_override'
            response_bbox = request.bbox
        elif final_detection is None:
            final_label = request.preliminary_label.strip() or 'unknown'
            final_confidence = float(request.preliminary_confidence)
            decision_source = 'preliminary_fallback'
            response_bbox = request.bbox
        else:
            final_label = final_detection.label
            final_confidence = final_detection.confidence
            decision_source = 'backend_model'
            response_bbox = BoundingBox(
                x1=final_detection.bbox[0],
                y1=final_detection.bbox[1],
                x2=final_detection.bbox[2],
                y2=final_detection.bbox[3],
            )

        treatment_plan = self._treatment_rule_engine.evaluate(
            disease_label=final_label,
            zone_id=request.zone_id,
            target_position=request.target_position,
        )
        dispatch_result = self._treatment_dispatcher.dispatch_plan(
            treatment_plan,
            observation_id=observation_id,
            requested_by=request.requested_by,
            auto_execute=bool(request.auto_execute_treatment),
        )
        persistence_refs = self._persistence_service.persist_confirmation(
            request=request,
            reviewed_at=reviewed_at,
            final_label=final_label,
            final_confidence=final_confidence,
            image_path=str(image_path),
            treatment_plan=treatment_plan,
            dispatch_result=dispatch_result,
        )

        metadata_path = image_path.with_suffix('.json')
        metadata_path.write_text(
            json.dumps(
                {
                    'observation_id': observation_id,
                    'reviewed_at': reviewed_at.isoformat(),
                    'request': _model_dump(request),
                    'detections': [asdict_detection(item) for item in detections],
                    'final_label': final_label,
                    'final_confidence': final_confidence,
                    'decision_source': decision_source,
                    'final_bbox': None if response_bbox is None else _model_dump(response_bbox),
                    'treatment_plan': _model_dump(treatment_plan),
                    'dispatch_result': _model_dump(dispatch_result),
                    'database_records': {
                        'robot_row_id': persistence_refs.robot_row_id,
                        'zone_row_id': persistence_refs.zone_row_id,
                        'plant_row_id': persistence_refs.plant_row_id,
                        'crop_observation_row_id': persistence_refs.crop_observation_row_id,
                        'actuation_log_row_id': persistence_refs.actuation_log_row_id,
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding='utf-8',
        )

        return ThinInferenceConfirmResponse(
            observation_id=observation_id,
            preliminary_label=request.preliminary_label.strip(),
            preliminary_confidence=float(request.preliminary_confidence),
            final_label=final_label,
            final_confidence=final_confidence,
            image_path=str(image_path),
            reviewed_at=reviewed_at.isoformat(),
            decision_source=decision_source,
            treatment_plan=treatment_plan,
            dispatch_result=dispatch_result,
        )

    def _infer(self, image_path: Path) -> list[Detection]:
        model = self._load_model()
        results = model.predict(
            source=str(image_path),
            imgsz=self._imgsz,
            conf=self._confidence_threshold,
            verbose=False,
        )
        if not results:
            return []

        result = results[0]
        boxes = getattr(result, 'boxes', None)
        if boxes is None or len(boxes) == 0:
            return []

        names = getattr(result, 'names', None) or getattr(model, 'names', {})
        detections: list[Detection] = []
        for box in boxes:
            confidence = float(box.conf[0].item()) if box.conf is not None else 0.0
            class_index = int(box.cls[0].item()) if box.cls is not None else -1
            label = _resolve_label(names, class_index)
            coords = box.xyxy[0].tolist() if box.xyxy is not None else [0.0, 0.0, 0.0, 0.0]
            detections.append(
                Detection(
                    label=label,
                    confidence=confidence,
                    bbox=(
                        float(coords[0]),
                        float(coords[1]),
                        float(coords[2]),
                        float(coords[3]),
                    ),
                )
            )

        detections.sort(key=lambda item: item.confidence, reverse=True)
        return detections

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not self._model_path.exists():
            raise ModelFileMissingError(
                f'Model file not found at {self._model_path}. '
                'Place best.pt there or set AGRIBOT_TOMATO_MODEL_PATH.'
            )
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ModelDependencyError(
                'ultralytics is required for backend confirmation inference. '
                'Install it in the backend runtime before using /api/v1/inference/confirm.'
            ) from exc

        self._model = YOLO(str(self._model_path))
        return self._model


def asdict_detection(detection: Detection) -> dict[str, Any]:
    return {
        'label': detection.label,
        'confidence': detection.confidence,
        'bbox': {
            'x1': detection.bbox[0],
            'y1': detection.bbox[1],
            'x2': detection.bbox[2],
            'y2': detection.bbox[3],
        },
    }


def _decode_base64_image(payload: str) -> bytes:
    encoded_payload = payload.strip()
    if not encoded_payload:
        raise ValueError('image_base64 is required.')
    if ',' in encoded_payload and encoded_payload.lower().startswith('data:'):
        encoded_payload = encoded_payload.split(',', 1)[1]
    try:
        return base64.b64decode(encoded_payload, validate=True)
    except ValueError as exc:
        raise ValueError('image_base64 is not valid base64 data.') from exc


def _model_dump(model: Any) -> dict[str, Any]:
    if hasattr(model, 'model_dump'):
        return model.model_dump()
    return model.dict()


def _normalize_image_suffix(image_format: str) -> str:
    normalized = image_format.strip().lower().lstrip('.')
    if normalized in {'jpg', 'jpeg', 'png'}:
        return 'jpg' if normalized == 'jpeg' else normalized
    return 'jpg'


def _parse_label_list(raw_value: str) -> set[str]:
    return {
        item.strip().lower()
        for item in raw_value.split(',')
        if item.strip()
    }


def _resolve_label(names: Any, class_index: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_index, class_index))
    if isinstance(names, list) and 0 <= class_index < len(names):
        return str(names[class_index])
    return str(class_index)


def _choose_final_detection(
    detections: list[Detection],
    *,
    preliminary_label: str,
    ignored_classes: set[str],
) -> Detection | None:
    normalized_preliminary = preliminary_label.strip().lower()
    filtered = [
        item for item in detections
        if item.label.strip().lower() not in ignored_classes
    ]
    if not filtered:
        filtered = detections
    if not filtered:
        return None

    if normalized_preliminary:
        for item in filtered:
            if item.label.strip().lower() == normalized_preliminary:
                return item
    return filtered[0]
