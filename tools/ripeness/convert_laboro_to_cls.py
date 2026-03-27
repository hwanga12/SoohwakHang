#!/usr/bin/env python3
# Usage examples:
#   python tools/ripeness/convert_laboro_to_cls.py --input /path/to/LaboroTomato --output /path/to/output_cls
#   python tools/ripeness/convert_laboro_to_cls.py --input /path/to/LaboroTomato --output /path/to/output_cls --val-ratio 0.1 --seed 7
"""Convert LaboroTomato detection annotations into a ripeness classification dataset.

The script reads COCO-style detection annotations from an extracted LaboroTomato
dataset and materializes bbox crops into this layout:

- train/unripe
- train/turning
- train/ripe
- val/unripe
- val/turning
- val/ripe
- test/unripe
- test/turning
- test/ripe

Rules:
- original test stays as final test
- validation is sampled only from the original train split
- splitting happens by source image, never by crop
- crops from the same source image never appear across both train and val
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - depends on local runtime
    raise SystemExit(
        "Pillow is required to crop images. Install it with `pip install pillow`."
    ) from exc


SOURCE_SPLITS = ("train", "test")
OUTPUT_SPLITS = ("train", "val", "test")
CLASS_NAMES = ("unripe", "turning", "ripe")
CLASS_SUFFIX_MAP = {
    "_green": "unripe",
    "_half_ripened": "turning",
    "_fully_ripened": "ripe",
}
ANNOTATION_FILENAMES = (
    "annotations.json",
    "annotation.json",
    "instances_default.json",
    "instances.json",
    "coco.json",
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
MIN_CROP_SIZE = 4
DEFAULT_VAL_RATIO = 0.2
DEFAULT_SEED = 42
MANIFEST_FILENAME = "crop_manifest.csv"
DEBUG_SAMPLE_LIMIT = 5
MANIFEST_FIELDNAMES = [
    "subset",
    "source_split",
    "class_name",
    "source_image_key",
    "source_image_id",
    "source_file_name",
    "source_image_path",
    "annotation_id",
    "category_id",
    "category_name",
    "crop_path",
    "status",
    "skip_reason",
    "bbox_x",
    "bbox_y",
    "bbox_width",
    "bbox_height",
    "crop_x1",
    "crop_y1",
    "crop_x2",
    "crop_y2",
    "crop_width",
    "crop_height",
]


@dataclass(frozen=True, slots=True)
class SplitSource:
    input_split: str
    input_root: Path
    split_root: Path
    annotation_path: Path


@dataclass(frozen=True, slots=True)
class ImageRecord:
    source_split: str
    image_id: str
    image_key: str
    file_name: str
    image_path: Path | None
    annotations: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class LoadedSplit:
    split_source: SplitSource
    images: list[ImageRecord]
    category_name_by_id: dict[Any, str]
    class_name_by_id: dict[Any, str]


@dataclass(slots=True)
class ImageResolutionStats:
    indexed_images_total: int
    resolved_images: int = 0
    unresolved_images: int = 0
    ambiguous_images: int = 0
    sample_resolved_paths: list[str] = field(default_factory=list)
    sample_unresolved_names: list[str] = field(default_factory=list)
    sample_ambiguous_names: list[str] = field(default_factory=list)

    def record_resolved(self, image_path: Path) -> None:
        self.resolved_images += 1
        if len(self.sample_resolved_paths) < DEBUG_SAMPLE_LIMIT:
            self.sample_resolved_paths.append(str(image_path))

    def record_unresolved(self, file_name: str) -> None:
        self.unresolved_images += 1
        if file_name and len(self.sample_unresolved_names) < DEBUG_SAMPLE_LIMIT:
            self.sample_unresolved_names.append(file_name)

    def record_ambiguous(self, file_name: str) -> None:
        self.ambiguous_images += 1
        if file_name and len(self.sample_ambiguous_names) < DEBUG_SAMPLE_LIMIT:
            self.sample_ambiguous_names.append(file_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert LaboroTomato detection annotations into ripeness classification crops."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Extracted LaboroTomato dataset root.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Classification dataset output root.",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=DEFAULT_VAL_RATIO,
        help="Validation ratio sampled only from the original train split. Default: 0.2",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Random seed used for the train/val image split. Default: 42",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_root = Path(args.input).expanduser().resolve()
    output_root = Path(args.output).expanduser().resolve()

    try:
        validate_val_ratio(args.val_ratio)
        (
            source_image_counts,
            crop_counts,
            skipped,
            manifest_path,
        ) = convert_dataset(
            input_root=input_root,
            output_root=output_root,
            val_ratio=args.val_ratio,
            seed=args.seed,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"\nManifest written to: {manifest_path}")
    print("\nSource image counts per subset/class:")
    for subset in OUTPUT_SPLITS:
        for class_name in CLASS_NAMES:
            print(f"  {subset}/{class_name}: {source_image_counts[(subset, class_name)]}")

    print("\nGenerated crop counts per subset/class:")
    for subset in OUTPUT_SPLITS:
        for class_name in CLASS_NAMES:
            print(f"  {subset}/{class_name}: {crop_counts[(subset, class_name)]}")

    if skipped:
        print("\nSkipped items:")
        for key in sorted(skipped):
            print(f"  {key}: {skipped[key]}")

    return 0


def validate_val_ratio(value: float) -> None:
    if not 0.0 <= value < 1.0:
        raise ValueError("--val-ratio must be in the range [0.0, 1.0).")


def convert_dataset(
    *,
    input_root: Path,
    output_root: Path,
    val_ratio: float,
    seed: int,
) -> tuple[Counter[tuple[str, str]], Counter[tuple[str, str]], Counter[str], Path]:
    if not input_root.exists():
        raise FileNotFoundError(f"Input dataset root does not exist: {input_root}")
    if not input_root.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_root}")

    ensure_output_tree(output_root)

    skipped: Counter[str] = Counter()
    image_index, indexed_images_total = build_image_index(input_root)
    loaded_splits: dict[str, LoadedSplit] = {}
    for source_split in SOURCE_SPLITS:
        split_source = discover_split_source(input_root, source_split)
        if split_source is None:
            print(
                f"[WARN] Could not find a COCO annotation file for split '{source_split}'. Skipping.",
                file=sys.stderr,
            )
            continue
        loaded_splits[source_split] = load_split(
            split_source,
            image_index=image_index,
            indexed_images_total=indexed_images_total,
            skipped=skipped,
        )

    if not loaded_splits:
        raise FileNotFoundError(
            "Could not locate any LaboroTomato annotation JSON for train/test splits."
        )

    manifest_rows: list[dict[str, str]] = []
    source_image_sets: dict[tuple[str, str], set[str]] = defaultdict(set)
    crop_counts: Counter[tuple[str, str]] = Counter()

    train_assignments: dict[str, str] = {}
    train_split = loaded_splits.get("train")
    if train_split is not None:
        train_assignments = assign_train_val_subsets(
            train_split.images,
            val_ratio=val_ratio,
            seed=seed,
        )
        process_loaded_split(
            loaded_split=train_split,
            subset_for_image_key=train_assignments,
            output_root=output_root,
            manifest_rows=manifest_rows,
            source_image_sets=source_image_sets,
            crop_counts=crop_counts,
            skipped=skipped,
        )

    test_split = loaded_splits.get("test")
    if test_split is not None:
        process_loaded_split(
            loaded_split=test_split,
            subset_for_image_key={record.image_key: "test" for record in test_split.images},
            output_root=output_root,
            manifest_rows=manifest_rows,
            source_image_sets=source_image_sets,
            crop_counts=crop_counts,
            skipped=skipped,
        )

    manifest_path = write_manifest(output_root=output_root, rows=manifest_rows)
    source_image_counts: Counter[tuple[str, str]] = Counter(
        {key: len(value) for key, value in source_image_sets.items()}
    )
    return source_image_counts, crop_counts, skipped, manifest_path


def ensure_output_tree(output_root: Path) -> None:
    for subset in OUTPUT_SPLITS:
        for class_name in CLASS_NAMES:
            (output_root / subset / class_name).mkdir(parents=True, exist_ok=True)

def discover_split_source(input_root: Path, source_split: str) -> SplitSource | None:
    print(f"[DEBUG] discover_split_source split={source_split} input_root={input_root}")

    direct_candidates = [
        input_root / "annotations" / f"{source_split}.json",
        input_root / f"{source_split}.json",
    ]

    candidate_paths: list[Path] = []
    seen: set[Path] = set()

    def add_candidate(path: Path) -> None:
        try:
            resolved = path.expanduser().resolve()
        except Exception:
            resolved = path
        if resolved in seen:
            return
        seen.add(resolved)
        candidate_paths.append(resolved)

    for candidate in direct_candidates:
        print(f"[DEBUG] direct candidate: {candidate} exists={candidate.exists()}")
        add_candidate(candidate)

    for path in input_root.rglob("*.json"):
        if path.name.lower() == f"{source_split}.json":
            add_candidate(path)

    print(f"[DEBUG] candidate count for split={source_split}: {len(candidate_paths)}")

    for resolved in candidate_paths:
        print(f"[DEBUG] checking candidate: {resolved}")
        if not resolved.exists() or not resolved.is_file():
            continue
        if looks_like_coco_annotation(resolved):
            split_dir = input_root / source_split
            if not split_dir.exists():
                split_dir = input_root
            print(f"[DEBUG] selected annotation json for split={source_split}: {resolved}")
            return SplitSource(
                input_split=source_split,
                input_root=input_root,
                split_root=split_dir,
                annotation_path=resolved,
            )

    print(f"[DEBUG] no valid annotation json found for split={source_split}")
    return None

def looks_like_coco_annotation(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False

    return (
        isinstance(data, dict)
        and isinstance(data.get("images"), list)
        and isinstance(data.get("annotations"), list)
        and isinstance(data.get("categories"), list)
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Annotation file must contain a JSON object: {path}")
    return data


def load_split(
    split_source: SplitSource,
    *,
    image_index: dict[str, list[Path]],
    indexed_images_total: int,
    skipped: Counter[str],
) -> LoadedSplit:
    data = load_json(split_source.annotation_path)
    raw_category_name_by_id = build_raw_category_name_map(data.get("categories", []), skipped)
    class_name_by_id = build_category_map(data.get("categories", []), skipped)

    annotations_by_image: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for annotation in data.get("annotations", []):
        if not isinstance(annotation, dict):
            skipped["invalid_annotation_record"] += 1
            continue
        annotations_by_image[annotation.get("image_id")].append(annotation)

    resolution_stats = ImageResolutionStats(indexed_images_total=indexed_images_total)
    image_records: list[ImageRecord] = []
    for image_info in data.get("images", []):
        if not isinstance(image_info, dict):
            skipped["invalid_image_record"] += 1
            continue

        file_name = str(image_info.get("file_name", "")).strip()
        image_id = str(image_info.get("id", "")).strip()
        image_key = build_image_key(image_id, file_name)
        if not image_key:
            skipped["image_missing_identity"] += 1
            continue

        image_records.append(
            ImageRecord(
                source_split=split_source.input_split,
                image_id=image_id,
                image_key=image_key,
                file_name=file_name,
                image_path=resolve_image_path(
                    image_info,
                    split_source,
                    image_index,
                    resolution_stats,
                    skipped,
                ),
                annotations=annotations_by_image.get(image_info.get("id"), []),
            )
        )

    print_image_resolution_debug(split_source, resolution_stats)
    return LoadedSplit(
        split_source=split_source,
        images=image_records,
        category_name_by_id=raw_category_name_by_id,
        class_name_by_id=class_name_by_id,
    )


def build_raw_category_name_map(
    categories: list[Any],
    skipped: Counter[str],
) -> dict[Any, str]:
    mapping: dict[Any, str] = {}
    for category in categories:
        if not isinstance(category, dict):
            skipped["invalid_category_record"] += 1
            continue
        category_id = category.get("id")
        if category_id is None:
            skipped["category_missing_id"] += 1
            continue
        mapping[category_id] = str(category.get("name", "")).strip()
    return mapping


def build_category_map(
    categories: list[Any],
    skipped: Counter[str],
) -> dict[Any, str]:
    mapped: dict[Any, str] = {}
    for category in categories:
        if not isinstance(category, dict):
            skipped["invalid_category_record"] += 1
            continue
        category_id = category.get("id")
        raw_name = str(category.get("name", "")).strip()
        class_name = map_category_name(raw_name)
        if category_id is None:
            skipped["category_missing_id"] += 1
            continue
        if class_name is None:
            skipped["ignored_category_label"] += 1
            continue
        mapped[category_id] = class_name
    return mapped


def assign_train_val_subsets(
    image_records: list[ImageRecord],
    *,
    val_ratio: float,
    seed: int,
) -> dict[str, str]:
    image_keys = sorted({record.image_key for record in image_records})
    if not image_keys:
        return {}

    shuffled = list(image_keys)
    random.Random(seed).shuffle(shuffled)
    val_count = compute_val_image_count(len(shuffled), val_ratio)
    val_keys = set(shuffled[:val_count])
    return {
        image_key: ("val" if image_key in val_keys else "train")
        for image_key in image_keys
    }


def compute_val_image_count(total_images: int, val_ratio: float) -> int:
    if total_images < 2 or val_ratio <= 0.0:
        return 0

    proposed = int(round(total_images * val_ratio))
    proposed = max(1, proposed)
    return min(total_images - 1, proposed)


def process_loaded_split(
    *,
    loaded_split: LoadedSplit,
    subset_for_image_key: dict[str, str],
    output_root: Path,
    manifest_rows: list[dict[str, str]],
    source_image_sets: dict[tuple[str, str], set[str]],
    crop_counts: Counter[tuple[str, str]],
    skipped: Counter[str],
) -> None:
    for record in loaded_split.images:
        subset = subset_for_image_key.get(record.image_key)
        if subset is None:
            skipped["missing_subset_assignment"] += 1
            continue

        if record.image_path is None:
            append_missing_image_rows(
                record=record,
                subset=subset,
                loaded_split=loaded_split,
                manifest_rows=manifest_rows,
                skipped=skipped,
            )
            continue

        try:
            with Image.open(record.image_path) as image_handle:
                image = image_handle.convert("RGB")
                width, height = image.size
                process_image_annotations(
                    record=record,
                    subset=subset,
                    image=image,
                    width=width,
                    height=height,
                    loaded_split=loaded_split,
                    output_root=output_root,
                    manifest_rows=manifest_rows,
                    source_image_sets=source_image_sets,
                    crop_counts=crop_counts,
                    skipped=skipped,
                )
        except OSError:
            append_image_open_error_rows(
                record=record,
                subset=subset,
                loaded_split=loaded_split,
                manifest_rows=manifest_rows,
                skipped=skipped,
            )


def process_image_annotations(
    *,
    record: ImageRecord,
    subset: str,
    image: Image.Image,
    width: int,
    height: int,
    loaded_split: LoadedSplit,
    output_root: Path,
    manifest_rows: list[dict[str, str]],
    source_image_sets: dict[tuple[str, str], set[str]],
    crop_counts: Counter[tuple[str, str]],
    skipped: Counter[str],
) -> None:
    for ann_index, annotation in enumerate(record.annotations):
        category_id = annotation.get("category_id")
        category_name = loaded_split.category_name_by_id.get(category_id, "")
        class_name = loaded_split.class_name_by_id.get(category_id)
        annotation_id = annotation_identifier(annotation, ann_index)
        bbox = parse_bbox(annotation.get("bbox"))

        if class_name is None:
            skipped["unknown_or_ignored_category"] += 1
            manifest_rows.append(
                build_manifest_row(
                    subset=subset,
                    record=record,
                    annotation_id=annotation_id,
                    category_id=category_id,
                    category_name=category_name,
                    class_name="",
                    status="skipped",
                    skip_reason="unknown_or_ignored_category",
                    bbox=bbox,
                )
            )
            continue

        crop_box = normalize_bbox_to_crop_box(
            annotation.get("bbox"),
            width=width,
            height=height,
        )
        if crop_box is None:
            skipped["invalid_bbox"] += 1
            manifest_rows.append(
                build_manifest_row(
                    subset=subset,
                    record=record,
                    annotation_id=annotation_id,
                    category_id=category_id,
                    category_name=category_name,
                    class_name=class_name,
                    status="skipped",
                    skip_reason="invalid_bbox",
                    bbox=bbox,
                )
            )
            continue

        crop_width = crop_box[2] - crop_box[0]
        crop_height = crop_box[3] - crop_box[1]
        if crop_width < MIN_CROP_SIZE or crop_height < MIN_CROP_SIZE:
            skipped["tiny_bbox"] += 1
            manifest_rows.append(
                build_manifest_row(
                    subset=subset,
                    record=record,
                    annotation_id=annotation_id,
                    category_id=category_id,
                    category_name=category_name,
                    class_name=class_name,
                    status="skipped",
                    skip_reason="tiny_bbox",
                    bbox=bbox,
                    crop_box=crop_box,
                    crop_width=crop_width,
                    crop_height=crop_height,
                )
            )
            continue

        crop = image.crop(crop_box)
        output_dir = output_root / subset / class_name
        output_path = build_output_path(
            output_dir=output_dir,
            subset=subset,
            class_name=class_name,
            image_path=record.image_path,
            image_id=record.image_id,
            annotation_id=annotation_id,
        )
        crop.save(output_path, format="JPEG", quality=95)

        source_image_sets[(subset, class_name)].add(record.image_key)
        crop_counts[(subset, class_name)] += 1
        manifest_rows.append(
            build_manifest_row(
                subset=subset,
                record=record,
                annotation_id=annotation_id,
                category_id=category_id,
                category_name=category_name,
                class_name=class_name,
                status="saved",
                skip_reason="",
                bbox=bbox,
                crop_box=crop_box,
                crop_width=crop_width,
                crop_height=crop_height,
                crop_path=output_path,
            )
        )


def append_missing_image_rows(
    *,
    record: ImageRecord,
    subset: str,
    loaded_split: LoadedSplit,
    manifest_rows: list[dict[str, str]],
    skipped: Counter[str],
) -> None:
    if not record.annotations:
        skipped["missing_image"] += 1
        manifest_rows.append(
            build_manifest_row(
                subset=subset,
                record=record,
                annotation_id="",
                category_id="",
                category_name="",
                class_name="",
                status="skipped",
                skip_reason="missing_image",
                bbox=None,
            )
        )
        return

    for ann_index, annotation in enumerate(record.annotations):
        category_id = annotation.get("category_id")
        category_name = loaded_split.category_name_by_id.get(category_id, "")
        class_name = loaded_split.class_name_by_id.get(category_id, "")
        skipped["missing_image"] += 1
        manifest_rows.append(
            build_manifest_row(
                subset=subset,
                record=record,
                annotation_id=annotation_identifier(annotation, ann_index),
                category_id=category_id,
                category_name=category_name,
                class_name=class_name,
                status="skipped",
                skip_reason="missing_image",
                bbox=parse_bbox(annotation.get("bbox")),
            )
        )


def append_image_open_error_rows(
    *,
    record: ImageRecord,
    subset: str,
    loaded_split: LoadedSplit,
    manifest_rows: list[dict[str, str]],
    skipped: Counter[str],
) -> None:
    if not record.annotations:
        skipped["image_open_error"] += 1
        manifest_rows.append(
            build_manifest_row(
                subset=subset,
                record=record,
                annotation_id="",
                category_id="",
                category_name="",
                class_name="",
                status="skipped",
                skip_reason="image_open_error",
                bbox=None,
            )
        )
        return

    for ann_index, annotation in enumerate(record.annotations):
        category_id = annotation.get("category_id")
        category_name = loaded_split.category_name_by_id.get(category_id, "")
        class_name = loaded_split.class_name_by_id.get(category_id, "")
        skipped["image_open_error"] += 1
        manifest_rows.append(
            build_manifest_row(
                subset=subset,
                record=record,
                annotation_id=annotation_identifier(annotation, ann_index),
                category_id=category_id,
                category_name=category_name,
                class_name=class_name,
                status="skipped",
                skip_reason="image_open_error",
                bbox=parse_bbox(annotation.get("bbox")),
            )
        )


def build_manifest_row(
    *,
    subset: str,
    record: ImageRecord,
    annotation_id: Any,
    category_id: Any,
    category_name: str,
    class_name: str,
    status: str,
    skip_reason: str,
    bbox: tuple[float, float, float, float] | None,
    crop_box: tuple[int, int, int, int] | None = None,
    crop_width: int | None = None,
    crop_height: int | None = None,
    crop_path: Path | None = None,
) -> dict[str, str]:
    return {
        "subset": subset,
        "source_split": record.source_split,
        "class_name": class_name,
        "source_image_key": record.image_key,
        "source_image_id": record.image_id,
        "source_file_name": record.file_name,
        "source_image_path": "" if record.image_path is None else str(record.image_path),
        "annotation_id": "" if annotation_id is None else str(annotation_id),
        "category_id": "" if category_id is None else str(category_id),
        "category_name": category_name,
        "crop_path": "" if crop_path is None else str(crop_path),
        "status": status,
        "skip_reason": skip_reason,
        "bbox_x": format_optional_number(None if bbox is None else bbox[0]),
        "bbox_y": format_optional_number(None if bbox is None else bbox[1]),
        "bbox_width": format_optional_number(None if bbox is None else bbox[2]),
        "bbox_height": format_optional_number(None if bbox is None else bbox[3]),
        "crop_x1": format_optional_number(None if crop_box is None else crop_box[0]),
        "crop_y1": format_optional_number(None if crop_box is None else crop_box[1]),
        "crop_x2": format_optional_number(None if crop_box is None else crop_box[2]),
        "crop_y2": format_optional_number(None if crop_box is None else crop_box[3]),
        "crop_width": format_optional_number(crop_width),
        "crop_height": format_optional_number(crop_height),
    }


def format_optional_number(value: float | int | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4f}"


def write_manifest(output_root: Path, rows: list[dict[str, str]]) -> Path:
    manifest_path = output_root / MANIFEST_FILENAME
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return manifest_path


def annotation_identifier(annotation: dict[str, Any], ann_index: int) -> str:
    annotation_id = annotation.get("id")
    if annotation_id is None:
        return f"ann_{ann_index:06d}"
    return str(annotation_id)


def map_category_name(raw_name: str) -> str | None:
    normalized = raw_name.strip().lower().replace("-", "_").replace(" ", "_")
    for suffix, class_name in CLASS_SUFFIX_MAP.items():
        if normalized.endswith(suffix):
            return class_name
    return None


def build_image_index(root: Path) -> tuple[dict[str, list[Path]], int]:
    index: dict[str, list[Path]] = defaultdict(list)
    seen_paths: set[Path] = set()
    if root.exists() and root.is_dir():
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            index[path.name].append(resolved)
    return index, len(seen_paths)


def resolve_image_path(
    image_info: dict[str, Any],
    split_source: SplitSource,
    image_index: dict[str, list[Path]],
    resolution_stats: ImageResolutionStats,
    skipped: Counter[str],
) -> Path | None:
    file_name = str(image_info.get("file_name", "")).strip()
    if not file_name:
        resolution_stats.record_unresolved("<empty_file_name>")
        return None

    seen_candidates: set[Path] = set()
    candidate_paths = [
        split_source.split_root / file_name,
        split_source.annotation_path.parent / file_name,
        split_source.input_root / file_name,
        split_source.split_root / "images" / Path(file_name).name,
        split_source.annotation_path.parent / "images" / Path(file_name).name,
        split_source.input_root / "images" / Path(file_name).name,
    ]
    for path in candidate_paths:
        resolved = path.resolve()
        if resolved in seen_candidates:
            continue
        seen_candidates.add(resolved)
        if resolved.is_file():
            resolution_stats.record_resolved(resolved)
            return resolved

    basename = Path(file_name).name
    basename_matches = image_index.get(basename, [])
    if len(basename_matches) == 1:
        resolution_stats.record_resolved(basename_matches[0])
        return basename_matches[0]
    if len(basename_matches) > 1:
        resolution_stats.record_ambiguous(basename)
        skipped["ambiguous_image_basename"] += 1
        sample_paths = ", ".join(str(path) for path in basename_matches[:3])
        print(
            f"[WARN] Ambiguous image basename '{basename}' in split "
            f"'{split_source.input_split}'. Candidates: {sample_paths}",
            file=sys.stderr,
        )
        return None

    resolution_stats.record_unresolved(basename or file_name)
    return None


def print_image_resolution_debug(
    split_source: SplitSource,
    resolution_stats: ImageResolutionStats,
) -> None:
    print(
        f"\n[DEBUG] Image resolution summary for split '{split_source.input_split}':"
    )
    print(f"  total indexed images under input root: {resolution_stats.indexed_images_total}")
    print(f"  resolved images: {resolution_stats.resolved_images}")
    print(f"  unresolved images: {resolution_stats.unresolved_images}")
    print(f"  ambiguous basenames: {resolution_stats.ambiguous_images}")

    if resolution_stats.sample_resolved_paths:
        print("  sample resolved paths:")
        for path in resolution_stats.sample_resolved_paths:
            print(f"    - {path}")

    if resolution_stats.sample_unresolved_names:
        print("  sample unresolved file names:")
        for file_name in resolution_stats.sample_unresolved_names:
            print(f"    - {file_name}")

    if resolution_stats.sample_ambiguous_names:
        print("  sample ambiguous file names:")
        for file_name in resolution_stats.sample_ambiguous_names:
            print(f"    - {file_name}")


def normalize_bbox_to_crop_box(
    raw_bbox: Any,
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int] | None:
    bbox = parse_bbox(raw_bbox)
    if bbox is None:
        return None

    x, y, bbox_width, bbox_height = bbox
    x1 = max(0, min(width, int(round(x))))
    y1 = max(0, min(height, int(round(y))))
    x2 = max(0, min(width, int(round(x + bbox_width))))
    y2 = max(0, min(height, int(round(y + bbox_height))))
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def parse_bbox(raw_bbox: Any) -> tuple[float, float, float, float] | None:
    if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) >= 4:
        try:
            x = float(raw_bbox[0])
            y = float(raw_bbox[1])
            width = float(raw_bbox[2])
            height = float(raw_bbox[3])
        except (TypeError, ValueError):
            return None
        return (x, y, width, height)

    if isinstance(raw_bbox, dict):
        if all(key in raw_bbox for key in ("x", "y", "width", "height")):
            try:
                return (
                    float(raw_bbox["x"]),
                    float(raw_bbox["y"]),
                    float(raw_bbox["width"]),
                    float(raw_bbox["height"]),
                )
            except (TypeError, ValueError):
                return None
        if all(key in raw_bbox for key in ("xmin", "ymin", "xmax", "ymax")):
            try:
                xmin = float(raw_bbox["xmin"])
                ymin = float(raw_bbox["ymin"])
                xmax = float(raw_bbox["xmax"])
                ymax = float(raw_bbox["ymax"])
            except (TypeError, ValueError):
                return None
            return (xmin, ymin, xmax - xmin, ymax - ymin)
    return None


def build_image_key(image_id: str, file_name: str) -> str:
    normalized_file_name = file_name.strip()
    normalized_image_id = image_id.strip()
    if normalized_image_id and normalized_file_name:
        return f"{normalized_image_id}::{normalized_file_name}"
    if normalized_image_id:
        return normalized_image_id
    return normalized_file_name


def build_output_path(
    *,
    output_dir: Path,
    subset: str,
    class_name: str,
    image_path: Path,
    image_id: str,
    annotation_id: str,
) -> Path:
    stem = sanitize_stem(image_path.stem)
    annotation_token = sanitize_stem(annotation_id or "ann")
    image_token = sanitize_stem(image_id or image_path.stem)
    base_name = f"{subset}_{class_name}_{image_token}_{annotation_token}_{stem}"
    candidate = output_dir / f"{base_name}.jpg"
    suffix = 1
    while candidate.exists():
        candidate = output_dir / f"{base_name}_{suffix:03d}.jpg"
        suffix += 1
    return candidate


def sanitize_stem(value: str) -> str:
    cleaned = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in value
    )
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return collapsed or "crop"


if __name__ == "__main__":
    raise SystemExit(main())
