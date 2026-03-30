from __future__ import annotations

from functools import lru_cache
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import json
import os
from pathlib import Path
import re
from typing import Any
import uuid

from robot_map_service import _load_crop_instances
from services.actuation.dispatcher import TreatmentCommandDispatcher
from services.actuation.schemas import Point3D
from services.actuation.rule_engine import DiseaseTreatmentRuleEngine
from services.perception.persistence import ObservationPersistenceService
from services.perception.schemas import (
    BoundingBox,
    ThinInferenceConfirmRequest,
    ThinInferenceConfirmResponse,
)


_DEFAULT_MODEL_RELATIVE_PATH = Path('artifacts/models/tomato_disease/v1/best.pt')
_DEFAULT_LABEL_CONTRACT_RELATIVE_PATH = Path(
    'artifacts/models/tomato_disease/v1/label_contract.json'
)
_DEFAULT_RUNTIME_RELATIVE_PATH = Path('artifacts/runtime/backend')
_DEFAULT_IGNORED_CLASSES = 'healthy,normal,normal_leaf,healthy_leaf'
_DEFAULT_LABEL_ALIASES = {
    'gray_mold': 'tomato_gray_mold_disease',
    'gray mold': 'tomato_gray_mold_disease',
    'tomato_gray_mold': 'tomato_gray_mold_disease',
    'response_gray_mold': 'tomato_gray_mold_disease',
    'powdery_mildew': 'tomato_powdery_mildew_disease',
    'powdery mildew': 'tomato_powdery_mildew_disease',
    'tomato_powdery_mildew': 'tomato_powdery_mildew_disease',
    'response_powdery_mildew': 'tomato_powdery_mildew_disease',
    'macro_npk_deficiency': 'tomato_macro_npk_deficiency_disease',
    'macro npk deficiency': 'tomato_macro_npk_deficiency_disease',
    'fruit_cracking': 'tomato_fruit_cracking_disease',
    'fruit cracking': 'tomato_fruit_cracking_disease',
    'fruit_crack': 'tomato_fruit_cracking_disease',
    'tomato_crack': 'tomato_fruit_cracking_disease',
    'calcium_deficiency': 'tomato_calcium_deficiency_disease',
    'calcium deficiency': 'tomato_calcium_deficiency_disease',
    'tomato_calcium_deficiency': 'tomato_calcium_deficiency_disease',
    'blossom_end_rot': 'tomato_calcium_deficiency_disease',
}
_MODEL_PATH_ENV_VARS = (
    'AGRIBOT_TOMATO_DISEASE_MODEL_PATH',
    'AGRIBOT_TOMATO_MODEL_PATH',
)
_MODEL_DEVICE_ENV_VARS = (
    'AGRIBOT_TOMATO_DISEASE_DEVICE',
    'AGRIBOT_TOMATO_MODEL_DEVICE',
)


@lru_cache(maxsize=1)
def _canonical_plant_positions() -> dict[str, Point3D]:
    crop_instances = _load_crop_instances()
    positions: dict[str, Point3D] = {}

    for plant in crop_instances.get('plants', []):
        plant_id = str(plant.get('plant_id') or '').strip()
        pose = plant.get('pose')
        if not plant_id or not isinstance(pose, dict):
            continue
        positions[plant_id] = Point3D(
            x=float(pose.get('x', 0.0)),
            y=float(pose.get('y', 0.0)),
            z=float(pose.get('z', 0.0)),
        )

    return positions


def _treatment_target_position(
    plant_id: str,
    fallback: Point3D | None,
) -> Point3D | None:
    canonical = _canonical_plant_positions().get(str(plant_id).strip())
    if canonical is not None:
        return canonical
    return fallback


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
        contract = _load_label_contract(repo_root)
        default_model_path = repo_root / _DEFAULT_MODEL_RELATIVE_PATH
        default_runtime_dir = repo_root / _DEFAULT_RUNTIME_RELATIVE_PATH

        self._model_path = Path(
            _read_first_env(_MODEL_PATH_ENV_VARS) or str(default_model_path)
        ).expanduser()
        self._runtime_dir = Path(
            os.environ.get('AGRIBOT_BACKEND_RUNTIME_DIR', str(default_runtime_dir))
        ).expanduser()
        self._model_name = os.environ.get('AGRIBOT_MAIN_MODEL_NAME', 'tomato_disease_detector')
        self._model_version = os.environ.get(
            'AGRIBOT_MAIN_MODEL_VERSION',
            self._model_path.parent.name or 'v1',
        )
        self._resolved_device = resolve_inference_device(
            _read_first_env(_MODEL_DEVICE_ENV_VARS) or 'auto'
        )
        self._imgsz = int(os.environ.get('AGRIBOT_MAIN_IMGSZ', '960'))
        self._confidence_threshold = float(
            os.environ.get('AGRIBOT_MAIN_CONFIDENCE', '0.25')
        )
        self._ignored_classes = _parse_label_list(
            os.environ.get('AGRIBOT_MAIN_IGNORED_CLASSES', _DEFAULT_IGNORED_CLASSES)
        )
        self._label_aliases = _read_label_aliases(contract)
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

        preliminary_label = normalize_detection_label(
            request.preliminary_label,
            label_aliases=self._label_aliases,
        )
        override_label = normalize_detection_label(
            request.test_override_final_label,
            label_aliases=self._label_aliases,
        )
        detections: list[Detection]
        final_detection: Detection | None
        if override_label:
            detections = []
            final_detection = None
        else:
            detections = [
                Detection(
                    label=normalize_detection_label(
                        item.label,
                        label_aliases=self._label_aliases,
                    ),
                    confidence=item.confidence,
                    bbox=item.bbox,
                )
                for item in self._infer(image_path)
            ]
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
            final_label = preliminary_label or 'unknown'
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

        treatment_target_position = _treatment_target_position(
            request.plant_id,
            request.target_position,
        )

        treatment_plan = self._treatment_rule_engine.evaluate(
            disease_label=final_label,
            zone_id=request.zone_id,
            target_position=treatment_target_position,
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
            model_name=self._model_name,
            model_version=self._model_version,
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
                    'model_name': self._model_name,
                    'model_version': self._model_version,
                    'model_device': self._resolved_device,
                    'final_bbox': None if response_bbox is None else _model_dump(response_bbox),
                    'treatment_plan': _model_dump(treatment_plan),
                    'dispatch_result': _model_dump(dispatch_result),
                    'database_records': {
                        'robot_row_id': persistence_refs.robot_row_id,
                        'zone_row_id': persistence_refs.zone_row_id,
                        'plant_row_id': persistence_refs.plant_row_id,
                        'crop_observation_row_id': persistence_refs.crop_observation_row_id,
                        'disease_judgment_row_id': getattr(
                            persistence_refs,
                            'disease_judgment_row_id',
                            None,
                        ),
                        'harvest_decision_row_id': getattr(
                            persistence_refs,
                            'harvest_decision_row_id',
                            None,
                        ),
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
            preliminary_label=preliminary_label,
            preliminary_confidence=float(request.preliminary_confidence),
            final_label=final_label,
            final_confidence=final_confidence,
            image_path=str(image_path),
            reviewed_at=reviewed_at.isoformat(),
            decision_source=decision_source,
            treatment_plan=treatment_plan,
            dispatch_result=dispatch_result,
            disease_judgment_id=getattr(persistence_refs, 'disease_judgment_row_id', None),
            harvest_decision_id=getattr(persistence_refs, 'harvest_decision_row_id', None),
        )

    def _infer(self, image_path: Path) -> list[Detection]:
        model = self._load_model()
        results = model.predict(
            source=str(image_path),
            imgsz=self._imgsz,
            conf=self._confidence_threshold,
            device=self._resolved_device,
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
            label = normalize_detection_label(
                _resolve_label(names, class_index),
                label_aliases=self._label_aliases,
            )
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
                f'Shared tomato disease model file not found at {self._model_path}. '
                'Expected artifacts/models/tomato_disease/v1/best.pt or set '
                'AGRIBOT_TOMATO_DISEASE_MODEL_PATH '
                '(legacy AGRIBOT_TOMATO_MODEL_PATH is also supported).'
            )
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ModelDependencyError(
                'ultralytics and torch are required for backend confirmation inference. '
                'Install them in the backend runtime before using /api/v1/inference/confirm.'
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
        _normalize_label_key(item)
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
    normalized_preliminary = _normalize_label_key(preliminary_label)
    filtered = [
        item for item in detections
        if _normalize_label_key(item.label) not in ignored_classes
    ]
    if not filtered:
        filtered = detections
    if not filtered:
        return None

    if normalized_preliminary:
        for item in filtered:
            if _normalize_label_key(item.label) == normalized_preliminary:
                return item
    return filtered[0]


def normalize_detection_label(
    raw_label: str,
    *,
    label_aliases: dict[str, str] | None = None,
) -> str:
    normalized_label = raw_label.strip()
    if not normalized_label:
        return ''

    aliases = label_aliases or _DEFAULT_LABEL_ALIASES
    alias_key = _normalize_label_key(normalized_label)
    canonical = aliases.get(alias_key)
    if canonical:
        return canonical
    return alias_key


def resolve_inference_device(raw_device: str) -> str:
    normalized_device = raw_device.strip().lower()
    if not normalized_device or normalized_device == 'auto':
        return 'cuda:0' if _cuda_available() else 'cpu'

    if normalized_device.startswith('cuda') and not _cuda_available():
        raise ModelDependencyError(
            'AGRIBOT_TOMATO_DISEASE_DEVICE requested a CUDA device, '
            'but torch.cuda.is_available() returned False.'
        )
    return raw_device.strip()


def _load_label_contract(repo_root: Path) -> dict[str, Any]:
    contract_path = repo_root / _DEFAULT_LABEL_CONTRACT_RELATIVE_PATH
    if not contract_path.exists():
        return {}
    try:
        return json.loads(contract_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}


def _read_label_aliases(contract: dict[str, Any]) -> dict[str, str]:
    contract_aliases = contract.get('canonical_label_aliases')
    if not isinstance(contract_aliases, dict):
        return dict(_DEFAULT_LABEL_ALIASES)

    aliases = dict(_DEFAULT_LABEL_ALIASES)
    for raw_key, raw_value in contract_aliases.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            continue
        aliases[_normalize_label_key(raw_key)] = raw_value.strip()
    return aliases


def _read_first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name, '').strip()
        if value:
            return value
    return None


def _normalize_label_key(raw_label: str) -> str:
    normalized = raw_label.strip().lower().replace('-', '_')
    normalized = re.sub(r'\s+', '_', normalized)
    normalized = re.sub(r'_+', '_', normalized)
    return normalized


def _cuda_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())
