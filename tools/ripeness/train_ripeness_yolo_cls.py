#!/usr/bin/env python3

# Ultralytics YOLO 분류 모드로 토마토 익음도 분류기를 학습하고 추론 보조 함수를 제공한다.
#
# 사용 예시:
# python tools/ripeness/train_ripeness_yolo_cls.py --data /path/to/ripeness_cls
# python tools/ripeness/train_ripeness_yolo_cls.py --data /path/to/ripeness_cls --epochs 50 --batch 32 --imgsz 224 --device 0
# python tools/ripeness/train_ripeness_yolo_cls.py --data /path/to/ripeness_cls --export-onnx
# python - <<'PY'
# from tools.ripeness.train_ripeness_yolo_cls import predict_ripeness_result, build_ripeness_judgment
# prediction = predict_ripeness_result('/path/to/best.pt', '/path/to/image.jpg')
# payload = build_ripeness_judgment(
# raw_label=prediction['raw_label'],
# confidence=prediction['confidence'],
# plant_id='plant_01',
# fruit_id='fruit_01',
# zone_id='farm_01',
# image_url='/images/fruit_01.jpg',
# model_checkpoint_path='/path/to/best.pt',
# )
# print(prediction)
# print(payload)
# PY
#
# 예상 데이터셋 구조:
# - train/unripe
# - train/turning
# - train/ripe
# - val/unripe
# - val/turning
# - val/ripe
# - test/unripe
# - test/turning
# - test/ripe

from __future__ import annotations

import argparse
import json
import warnings
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "yolo26n-cls.pt"
DEFAULT_IMGSZ = 224
DEFAULT_BATCH = 32
DEFAULT_EPOCHS = 100
DEFAULT_WORKERS = 8
DEFAULT_SEED = 42
DEFAULT_PROJECT = "runs/ripeness_cls"
DEFAULT_NAME = "yolo26n_cls_ripeness"
DEFAULT_CLASSES = ["unripe", "turning", "ripe"]
DEFAULT_MODEL_NAME = "ripeness_classifier_v1"
SUMMARY_FILENAME = "training_summary.json"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
RIPENESS_ACTIONS = {
    "unripe": "HOLD_HARVEST",
    "turning": "REOBSERVE",
    "ripe": "HARVEST",
}
RIPENESS_LABEL_KO = {
    "unripe": "미숙",
    "turning": "착색 진행",
    "ripe": "수확 가능",
}
RIPENESS_SUMMARY_TEXT = {
    "unripe": "아직 충분히 익지 않아 수확 보류가 필요해.",
    "turning": "착색이 진행 중이어서 재관찰이 필요해.",
    "ripe": "익음 상태가 확인되어 수확 후보로 판단했어.",
}


def parse_args() -> argparse.Namespace:
    # args를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    parser = argparse.ArgumentParser(
        description="Train a YOLO26 classification model for tomato ripeness."
    )
    parser.add_argument("--data", required=True, help="ImageFolder-style dataset root.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ultralytics classification model checkpoint.")
    parser.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ, help="Input image size. Default: 224")
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS, help="Training epochs. Default: 100")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH, help="Batch size. Default: 32")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="Training project directory.")
    parser.add_argument("--name", default=DEFAULT_NAME, help="Training run name.")
    parser.add_argument("--device", default="", help="Training device, e.g. cpu, 0, 0,1. Empty means auto.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Dataloader workers. Default: 8")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed. Default: 42")
    parser.add_argument(
        "--export-onnx",
        action="store_true",
        help="Export the best checkpoint to ONNX after training.",
    )
    return parser.parse_args()


def main() -> int:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    args = parse_args()
    data_root = Path(args.data).expanduser().resolve()

    try:
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover - depends on local runtime
        raise SystemExit(
            "Ultralytics is required. Install it with `pip install ultralytics`."
        ) from exc

    validate_dataset_root(data_root)
    class_names = resolve_class_names(data_root)

    model = YOLO(args.model)
    train_results = model.train(
        data=str(data_root),
        imgsz=args.imgsz,
        epochs=args.epochs,
        batch=args.batch,
        project=args.project,
        name=args.name,
        device=args.device or None,
        workers=args.workers,
        seed=args.seed,
    )

    save_dir = resolve_save_dir(
        train_results=train_results,
        model=model,
        project=args.project,
        name=args.name,
    )
    best_checkpoint = resolve_best_checkpoint(save_dir)

    best_model = YOLO(str(best_checkpoint))
    val_metrics = best_model.val(
        data=str(data_root),
        split="val",
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device or None,
        workers=args.workers,
        project=args.project,
        name=f"{args.name}_val",
    )

    test_metrics: Any | None = None
    if split_has_images(data_root, "test"):
        test_metrics = best_model.val(
            data=str(data_root),
            split="test",
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device or None,
            workers=args.workers,
            project=args.project,
            name=f"{args.name}_test",
        )
    else:
        warnings.warn(
            f"Test split not found or empty under {data_root / 'test'}. Skipping test evaluation.",
            stacklevel=1,
        )

    onnx_export_path: str | None = None
    if args.export_onnx:
        export_result = best_model.export(
            format="onnx",
            imgsz=args.imgsz,
        )
        exported_onnx_path = resolve_exported_onnx_path(
            export_result=export_result,
            best_checkpoint=best_checkpoint,
            save_dir=save_dir,
        )
        onnx_export_path = str(exported_onnx_path.resolve())
        print(f"ONNX export: {onnx_export_path}")

    summary = {
        "best_checkpoint_path": str(best_checkpoint.resolve()),
        "dataset_path": str(data_root),
        "class_names": class_names,
        "validation_metrics": metrics_to_dict(val_metrics),
        "test_metrics": None if test_metrics is None else metrics_to_dict(test_metrics),
        "onnx_export_path": onnx_export_path,
    }
    summary_path = save_dir / SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"Best checkpoint: {best_checkpoint.resolve()}")
    print(f"Summary saved to: {summary_path.resolve()}")
    return 0


def validate_dataset_root(data_root: Path) -> None:
    # dataset root가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
    if not data_root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {data_root}")
    if not data_root.is_dir():
        raise NotADirectoryError(f"Dataset root is not a directory: {data_root}")

    for split_name in ("train", "val"):
        split_dir = data_root / split_name
        if not split_dir.is_dir():
            raise FileNotFoundError(f"Required split directory is missing: {split_dir}")
        if not split_has_images(data_root, split_name):
            raise FileNotFoundError(f"Required split has no images: {split_dir}")


def split_has_images(data_root: Path, split_name: str) -> bool:
    # split has 이미지 정보를 계산해 반환한다.
    split_dir = data_root / split_name
    if not split_dir.is_dir():
        return False
    for path in split_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            return True
    return False


def resolve_class_names(data_root: Path) -> list[str]:
    # 현재 입력 조건을 바탕으로 class 이름 목록를 계산하거나 결정한다.
    train_dir = data_root / "train"
    if not train_dir.is_dir():
        return list(DEFAULT_CLASSES)

    discovered = sorted(path.name for path in train_dir.iterdir() if path.is_dir())
    if all(class_name in discovered for class_name in DEFAULT_CLASSES):
        return list(DEFAULT_CLASSES)
    return discovered or list(DEFAULT_CLASSES)


def resolve_save_dir(
    *,
    train_results: Any,
    model: Any,
    project: str,
    name: str,
) -> Path:
    # 현재 입력 조건을 바탕으로 save 디렉터리를 계산하거나 결정한다.
    candidate_values = [
        getattr(train_results, "save_dir", None),
        getattr(getattr(model, "trainer", None), "save_dir", None),
    ]
    for value in candidate_values:
        if value:
            return Path(value).expanduser().resolve()
    return (Path(project).expanduser() / name).resolve()


def resolve_best_checkpoint(save_dir: Path) -> Path:
    # 현재 입력 조건을 바탕으로 best checkpoint를 계산하거나 결정한다.
    best_checkpoint = save_dir / "weights" / "best.pt"
    if best_checkpoint.is_file():
        return best_checkpoint

    last_checkpoint = save_dir / "weights" / "last.pt"
    if last_checkpoint.is_file():
        warnings.warn(
            f"best.pt was not found under {save_dir / 'weights'}. Falling back to last.pt.",
            stacklevel=1,
        )
        return last_checkpoint

    raise FileNotFoundError(f"No best.pt or last.pt found under {save_dir / 'weights'}")


def resolve_exported_onnx_path(
    *,
    export_result: Any,
    best_checkpoint: Path,
    save_dir: Path,
) -> Path:
    # 현재 입력 조건을 바탕으로 exported onnx 경로를 계산하거나 결정한다.
    candidate_paths: list[Path] = []

    for candidate in flatten_export_result(export_result):
        try:
            path = Path(candidate).expanduser()
        except TypeError:
            continue
        candidate_paths.append(path)
        if not path.is_absolute():
            candidate_paths.append(save_dir / path)
            candidate_paths.append(best_checkpoint.parent / path)

    candidate_paths.extend(
        [
            best_checkpoint.with_suffix(".onnx"),
            best_checkpoint.parent / f"{best_checkpoint.stem}.onnx",
            save_dir / f"{best_checkpoint.stem}.onnx",
            save_dir / "weights" / f"{best_checkpoint.stem}.onnx",
        ]
    )
    candidate_paths.extend(sorted(save_dir.rglob("*.onnx")))

    seen: set[Path] = set()
    for candidate in candidate_paths:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved

    raise FileNotFoundError(
        f"ONNX export was requested, but no exported .onnx file was found near {save_dir}."
    )


def flatten_export_result(export_result: Any) -> list[Any]:
    # flatten 내보내기 결과 정보를 계산해 반환한다.
    if export_result is None:
        return []
    if isinstance(export_result, (list, tuple)):
        flattened: list[Any] = []
        for item in export_result:
            flattened.extend(flatten_export_result(item))
        return flattened
    return [export_result]


def metrics_to_dict(metrics: Any) -> dict[str, Any]:
    # metrics dict 정보를 계산해 반환한다.
    serialized: dict[str, Any] = {}

    for attr_name in ("top1", "top5", "fitness"):
        value = getattr(metrics, attr_name, None)
        if value is not None:
            serialized[attr_name] = to_jsonable(value)

    speed = getattr(metrics, "speed", None)
    if isinstance(speed, dict):
        serialized["speed"] = {str(key): to_jsonable(value) for key, value in speed.items()}

    results_dict = getattr(metrics, "results_dict", None)
    if isinstance(results_dict, dict):
        serialized["results_dict"] = {
            str(key): to_jsonable(value)
            for key, value in results_dict.items()
        }

    summary_method = getattr(metrics, "summary", None)
    if callable(summary_method):
        try:
            serialized["summary"] = to_jsonable(summary_method())
        except Exception:
            pass

    return serialized


def to_jsonable(value: Any) -> Any:
    # 현재 값을 jsonable 형식으로 변환한다.
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return item_method()
        except Exception:
            return str(value)

    return str(value)


def predict_ripeness_result(model_path: str | Path, image_path: str | Path) -> dict[str, Any]:
    # 입력 데이터를 바탕으로 ripeness 결과를 추론한다.
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    results = model(str(image_path))
    if not results:
        return {"raw_label": "", "canonical_code": "", "confidence": 0.0}

    probs = getattr(results[0], "probs", None)
    if probs is None:
        return {"raw_label": "", "canonical_code": "", "confidence": 0.0}

    top1_index = int(getattr(probs, "top1", -1))
    names = getattr(results[0], "names", {}) or {}
    top1_conf = getattr(probs, "top1conf", None)
    predicted_name = normalize_ripeness_class_name(names.get(top1_index, str(top1_index)))
    confidence = float(to_jsonable(top1_conf) or 0.0)
    return {
        "raw_label": predicted_name,
        "canonical_code": predicted_name,
        "confidence": confidence,
    }


def build_ripeness_judgment(
    *,
    raw_label: str,
    confidence: float,
    plant_id: str = "",
    fruit_id: str = "",
    zone_id: str = "",
    image_url: str = "",
    model_name: str = DEFAULT_MODEL_NAME,
    model_version: str | None = None,
    model_checkpoint_path: str | Path | None = None,
    requires_approval: bool = True,
    risk_level: str | None = None,
) -> dict[str, Any]:
    # ripeness 판정 결과를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    canonical_code = normalize_ripeness_class_name(raw_label)
    resolved_model_version = resolve_model_version(
        model_version=model_version,
        model_checkpoint_path=model_checkpoint_path,
    )
    label_ko = RIPENESS_LABEL_KO[canonical_code]
    summary_text = RIPENESS_SUMMARY_TEXT[canonical_code]
    evidence = [f"숙도 분류 결과 {canonical_code}"]

    return {
        "plant_id": plant_id,
        "fruit_id": fruit_id,
        "zone_id": zone_id,
        "judgment_type": "RIPENESS",
        "model_name": model_name,
        "model_version": resolved_model_version,
        "raw_label": canonical_code,
        "canonical_code": canonical_code,
        "confidence": float(confidence),
        "risk_level": risk_level,
        "recommended_action_code": RIPENESS_ACTIONS[canonical_code],
        "requires_approval": requires_approval,
        "payload_json": {
            "label_ko": label_ko,
            "summary_text": summary_text,
            "evidence": evidence,
            "decision_scope": "RIPENESS_ONLY_PROVISIONAL",
            "is_final_harvest_decision": False,
        },
        "image_url": image_url,
    }


def normalize_ripeness_class_name(raw_label: str) -> str:
    # ripeness class 이름를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(raw_label).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in DEFAULT_CLASSES:
        raise ValueError(
            f"Unsupported ripeness class '{raw_label}'. Expected one of: {', '.join(DEFAULT_CLASSES)}"
        )
    return normalized


def resolve_model_version(
    *,
    model_version: str | None,
    model_checkpoint_path: str | Path | None,
) -> str:
    # 현재 입력 조건을 바탕으로 모델 version를 계산하거나 결정한다.
    if model_version:
        return model_version
    if model_checkpoint_path:
        return Path(model_checkpoint_path).name
    return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
