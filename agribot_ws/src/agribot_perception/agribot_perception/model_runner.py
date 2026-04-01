# 이 모듈은 인지와 추론 패키지에서 model runner 기능을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any


_DEFAULT_MODEL_RELATIVE_PATH = Path('artifacts/models/tomato_disease/v1/best.pt')
_DEFAULT_LABEL_CONTRACT_RELATIVE_PATH = Path(
    'artifacts/models/tomato_disease/v1/label_contract.json'
)
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


@dataclass(frozen=True)
class Detection:
    # 탐지 결과 한 건을 명확한 필드 구조로 담기 위한 데이터 클래스다.
    label: str
    confidence: float
    bbox: tuple[float, float, float, float]


class ModelRunner:
    # 모델 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    def __init__(
        self,
        *,
        model_path: str | None = None,
        imgsz: int = 640,
        confidence_threshold: float = 0.35,
        device: str | None = None,
    ) -> None:
        # ModelRunner 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        repo_root = Path(__file__).resolve().parents[4]
        contract = _load_label_contract(repo_root)
        default_model_path = repo_root / _DEFAULT_MODEL_RELATIVE_PATH
        self._model_path = Path(
            model_path
            or _read_first_env(_MODEL_PATH_ENV_VARS)
            or str(default_model_path)
        ).expanduser()
        self._imgsz = imgsz
        self._confidence_threshold = confidence_threshold
        self._label_aliases = _read_label_aliases(contract)
        self._resolved_device = resolve_inference_device(
            device or _read_first_env(_MODEL_DEVICE_ENV_VARS) or 'auto'
        )
        self._model: Any | None = None

    @property
    def model_path(self) -> Path:
        # 모델 경로 정보를 계산해 반환한다.
        return self._model_path

    @property
    def resolved_device(self) -> str:
        # resolved 장치 정보를 계산해 반환한다.
        return self._resolved_device

    def infer(self, image: Any) -> list[Detection]:
        # 입력 데이터를 바탕으로 데이터를 추론한다.
        model = self._load_model()
        results = model.predict(
            source=image,
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
            coords = box.xyxy[0].tolist() if box.xyxy is not None else [0.0, 0.0, 0.0, 0.0]
            detections.append(
                Detection(
                    label=normalize_detection_label(
                        _resolve_label(names, class_index),
                        label_aliases=self._label_aliases,
                    ),
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
        # 모델를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        if self._model is not None:
            return self._model
        if not self._model_path.exists():
            raise FileNotFoundError(
                f'Shared tomato disease model file not found at {self._model_path}. '
                'Expected artifacts/models/tomato_disease/v1/best.pt or set '
                'AGRIBOT_TOMATO_DISEASE_MODEL_PATH '
                '(legacy AGRIBOT_TOMATO_MODEL_PATH is also supported).'
            )
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                'ultralytics and torch are required for thin inference. '
                'Install them in the ROS runtime before launching thin_inference_node.'
            ) from exc

        self._model = YOLO(str(self._model_path))
        return self._model


def parse_label_list(raw_value: str) -> set[str]:
    # 라벨 list를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    return {
        _normalize_label_key(item)
        for item in raw_value.split(',')
        if item.strip()
    }


def choose_detection(
    detections: list[Detection],
    *,
    allowed_classes: set[str],
    ignored_classes: set[str],
) -> Detection | None:
    # 탐지 결과 가운데 최종 대상을 고른다.
    filtered = detections
    if allowed_classes:
        filtered = [
            item for item in filtered
            if item.label.strip().lower() in allowed_classes
        ]
    if ignored_classes:
        filtered = [
            item for item in filtered
            if item.label.strip().lower() not in ignored_classes
        ]
    return filtered[0] if filtered else None


def _resolve_label(names: Any, class_index: int) -> str:
    # 현재 입력 조건을 바탕으로 라벨를 계산하거나 결정한다.
    if isinstance(names, dict):
        return str(names.get(class_index, class_index))
    if isinstance(names, list) and 0 <= class_index < len(names):
        return str(names[class_index])
    return str(class_index)


def normalize_detection_label(
    raw_label: str,
    *,
    label_aliases: dict[str, str] | None = None,
) -> str:
    # detection 라벨를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
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
    # 현재 입력 조건을 바탕으로 inference 장치를 계산하거나 결정한다.
    normalized_device = raw_device.strip().lower()
    if not normalized_device or normalized_device == 'auto':
        return 'cuda:0' if _cuda_available() else 'cpu'

    if normalized_device.startswith('cuda') and not _cuda_available():
        raise RuntimeError(
            'AGRIBOT_TOMATO_DISEASE_DEVICE requested a CUDA device, '
            'but torch.cuda.is_available() returned False.'
        )
    return raw_device.strip()


def _read_label_aliases(contract: dict[str, Any]) -> dict[str, str]:
    # 라벨 별칭 목록를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    contract_aliases = contract.get('canonical_label_aliases')
    if not isinstance(contract_aliases, dict):
        return dict(_DEFAULT_LABEL_ALIASES)

    aliases = dict(_DEFAULT_LABEL_ALIASES)
    for raw_key, raw_value in contract_aliases.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            continue
        aliases[_normalize_label_key(raw_key)] = raw_value.strip()
    return aliases


def _load_label_contract(repo_root: Path) -> dict[str, Any]:
    # 라벨 계약를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    contract_path = repo_root / _DEFAULT_LABEL_CONTRACT_RELATIVE_PATH
    if not contract_path.exists():
        return {}
    try:
        return json.loads(contract_path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}


def _read_first_env(names: tuple[str, ...]) -> str | None:
    # first ENV를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    for name in names:
        value = os.environ.get(name, '').strip()
        if value:
            return value
    return None


def _normalize_label_key(raw_label: str) -> str:
    # 라벨 KEY를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = raw_label.strip().lower().replace('-', '_')
    normalized = re.sub(r'\s+', '_', normalized)
    normalized = re.sub(r'_+', '_', normalized)
    return normalized


def _cuda_available() -> bool:
    # cuda available 정보를 계산해 반환한다.
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())
