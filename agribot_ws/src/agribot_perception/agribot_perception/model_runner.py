from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


_DEFAULT_MODEL_RELATIVE_PATH = Path('artifacts/models/tomato_disease/v1/best.pt')


@dataclass(frozen=True)
class Detection:
    label: str
    confidence: float
    bbox: tuple[float, float, float, float]


class ModelRunner:
    """Lazy YOLO wrapper used by the thin inference node."""

    def __init__(
        self,
        *,
        model_path: str | None = None,
        imgsz: int = 640,
        confidence_threshold: float = 0.35,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        default_model_path = repo_root / _DEFAULT_MODEL_RELATIVE_PATH
        self._model_path = Path(
            model_path or os.environ.get('AGRIBOT_TOMATO_MODEL_PATH', str(default_model_path))
        ).expanduser()
        self._imgsz = imgsz
        self._confidence_threshold = confidence_threshold
        self._model: Any | None = None

    @property
    def model_path(self) -> Path:
        return self._model_path

    def infer(self, image: Any) -> list[Detection]:
        model = self._load_model()
        results = model.predict(
            source=image,
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
            coords = box.xyxy[0].tolist() if box.xyxy is not None else [0.0, 0.0, 0.0, 0.0]
            detections.append(
                Detection(
                    label=_resolve_label(names, class_index),
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
            raise FileNotFoundError(
                f'Model file not found at {self._model_path}. '
                'Place best.pt there or set AGRIBOT_TOMATO_MODEL_PATH.'
            )
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                'ultralytics is required for thin inference. '
                'Install it in the ROS runtime before launching thin_inference_node.'
            ) from exc

        self._model = YOLO(str(self._model_path))
        return self._model


def parse_label_list(raw_value: str) -> set[str]:
    return {
        item.strip().lower()
        for item in raw_value.split(',')
        if item.strip()
    }


def choose_detection(
    detections: list[Detection],
    *,
    allowed_classes: set[str],
    ignored_classes: set[str],
) -> Detection | None:
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
    if isinstance(names, dict):
        return str(names.get(class_index, class_index))
    if isinstance(names, list) and 0 <= class_index < len(names):
        return str(names[class_index])
    return str(class_index)
