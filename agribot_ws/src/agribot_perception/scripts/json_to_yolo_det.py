#!/usr/bin/env python3
"""Convert a tomato detection manifest into a YOLO-style dataset tree.

The converter consumes the CSV produced by ``build_tomato_manifest.py`` and
only processes rows where ``use_for_detection`` is true.

Positive samples are converted from top-level raw JSON bbox annotations into
YOLO ``.txt`` labels. Normal images (disease code ``00``) remain negative
samples and receive an empty label file.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from agribot_perception.utils.codebook import (  # noqa: E402
    DETECTION_TARGETS,
    get_detection_class_index,
    is_negative_sample_disease,
    normalize_code,
)

MANIFEST_REQUIRED_COLUMNS = {
    "image_path",
    "image_rel_path",
    "json_path",
    "json_rel_path",
    "disease_code",
    "is_negative_sample",
    "use_for_detection",
    "top_level_bbox_count",
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
SPLIT_ALIASES = {
    "train": "train",
    "training": "train",
    "val": "val",
    "valid": "val",
    "validation": "val",
    "dev": "val",
    "test": "test",
    "testing": "test",
}

JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


@dataclass(frozen=True, slots=True)
class ManifestRecord:
    """Normalized manifest row used by the converter."""

    line_number: int
    image_path: Path
    image_rel_path: str
    json_path: Path
    json_rel_path: str
    disease_code: str
    is_negative_sample: bool
    top_level_bbox_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a tomato detection manifest CSV into a YOLO dataset."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the manifest CSV produced by build_tomato_manifest.py.",
    )
    parser.add_argument(
        "--output-root",
        required=True,
        help="YOLO dataset output root, for example ~/datasets/.../tomato_det_v1.",
    )
    parser.add_argument(
        "--image-mode",
        choices=("copy", "symlink", "hardlink"),
        default="copy",
        help="How to materialize images into the YOLO dataset tree.",
    )
    parser.add_argument(
        "--default-split",
        choices=("train", "val", "test"),
        default="train",
        help="Fallback split when it cannot be inferred from the manifest paths.",
    )
    return parser.parse_args()


def parse_bool_text(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def parse_int_text(value: Any, *, default: int = 0) -> int:
    text = str(value).strip()
    if not text:
        return default
    return int(text)


def resolve_manifest_path(path_text: str, manifest_path: Path) -> Path:
    raw_path = Path(path_text).expanduser()
    if raw_path.is_absolute():
        return raw_path
    return (manifest_path.parent / raw_path).resolve()


def extract_annotations(data: dict[str, Any]) -> list[dict[str, Any]]:
    if "annotation" in data:
        raw = data.get("annotation")
    elif "annotations" in data:
        raw = data.get("annotations")
    else:
        return []

    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def load_json(json_path: Path) -> dict[str, Any]:
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_manifest_records(manifest_path: Path) -> tuple[list[ManifestRecord], int]:
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing_columns = sorted(MANIFEST_REQUIRED_COLUMNS - headers)
        if missing_columns:
            raise SystemExit(
                "Manifest is missing required columns: " + ", ".join(missing_columns)
            )

        total_rows = 0
        selected_records: list[ManifestRecord] = []
        for line_number, row in enumerate(reader, start=2):
            total_rows += 1
            if not parse_bool_text(row.get("use_for_detection", "")):
                continue

            image_path_text = str(row.get("image_path", "")).strip()
            json_path_text = str(row.get("json_path", "")).strip()
            disease_code = normalize_code(row.get("disease_code"))
            if not image_path_text:
                raise SystemExit(f"Manifest row {line_number} has an empty image_path.")
            if not json_path_text:
                raise SystemExit(f"Manifest row {line_number} has an empty json_path.")
            if not disease_code:
                raise SystemExit(f"Manifest row {line_number} has an empty disease_code.")

            selected_records.append(
                ManifestRecord(
                    line_number=line_number,
                    image_path=resolve_manifest_path(image_path_text, manifest_path),
                    image_rel_path=str(row.get("image_rel_path", "")).strip(),
                    json_path=resolve_manifest_path(json_path_text, manifest_path),
                    json_rel_path=str(row.get("json_rel_path", "")).strip(),
                    disease_code=disease_code,
                    is_negative_sample=parse_bool_text(row.get("is_negative_sample", ""))
                    or is_negative_sample_disease(disease_code),
                    top_level_bbox_count=parse_int_text(
                        row.get("top_level_bbox_count", ""), default=0
                    ),
                )
            )

    return selected_records, total_rows


def normalize_split_name(value: str) -> str | None:
    return SPLIT_ALIASES.get(value.strip().lower())


def path_parts(path_text: str) -> list[str]:
    raw_path = Path(path_text)
    return [part for part in raw_path.parts if part not in {"", raw_path.anchor}]


def infer_split_and_tail(record: ManifestRecord, default_split: str) -> tuple[str, Path]:
    source_candidates = [
        record.image_rel_path,
        record.json_rel_path,
        str(record.image_path),
        str(record.json_path),
    ]

    for candidate in source_candidates:
        if not candidate:
            continue
        parts = path_parts(candidate)
        for index, part in enumerate(parts):
            normalized_split = normalize_split_name(part)
            if normalized_split is None:
                continue
            tail_parts = parts[index + 1 :] or [record.image_path.name]
            return normalized_split, Path(*tail_parts)

    return default_split, Path(record.image_path.name)


def remove_existing_file(path: Path) -> None:
    if path.is_symlink() or path.exists():
        path.unlink()


def materialize_image(source_path: Path, destination_path: Path, image_mode: str) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    remove_existing_file(destination_path)

    if image_mode == "copy":
        shutil.copy2(source_path, destination_path)
        return
    if image_mode == "symlink":
        destination_path.symlink_to(source_path)
        return
    if image_mode == "hardlink":
        os.link(source_path, destination_path)
        return

    raise ValueError(f"Unsupported image mode: {image_mode}")


def read_png_size(image_path: Path) -> tuple[int, int]:
    with image_path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file.")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def read_gif_size(image_path: Path) -> tuple[int, int]:
    with image_path.open("rb") as handle:
        header = handle.read(10)
    if header[:6] not in {b"GIF87a", b"GIF89a"}:
        raise ValueError("Not a GIF file.")
    width, height = struct.unpack("<HH", header[6:10])
    return width, height


def read_bmp_size(image_path: Path) -> tuple[int, int]:
    with image_path.open("rb") as handle:
        header = handle.read(26)
    if header[:2] != b"BM":
        raise ValueError("Not a BMP file.")
    width, height = struct.unpack("<II", header[18:26])
    return width, abs(height)


def read_jpeg_size(image_path: Path) -> tuple[int, int]:
    with image_path.open("rb") as handle:
        if handle.read(2) != b"\xff\xd8":
            raise ValueError("Not a JPEG file.")

        while True:
            marker_prefix = handle.read(1)
            if not marker_prefix:
                break
            if marker_prefix != b"\xff":
                continue

            marker_code = handle.read(1)
            while marker_code == b"\xff":
                marker_code = handle.read(1)
            if not marker_code:
                break

            marker = marker_code[0]
            if marker in {0xD8, 0xD9}:
                continue

            segment_length_bytes = handle.read(2)
            if len(segment_length_bytes) != 2:
                break
            segment_length = struct.unpack(">H", segment_length_bytes)[0]
            if segment_length < 2:
                raise ValueError(f"Invalid JPEG segment length in {image_path}.")

            if marker in JPEG_SOF_MARKERS:
                frame_header = handle.read(5)
                if len(frame_header) != 5:
                    break
                height, width = struct.unpack(">HH", frame_header[1:5])
                return width, height

            handle.seek(segment_length - 2, 1)

    raise ValueError(f"Could not read JPEG dimensions from {image_path}.")


def read_image_size(image_path: Path) -> tuple[int, int]:
    try:
        from PIL import Image
    except ImportError:
        Image = None

    if Image is not None:
        with Image.open(image_path) as image:
            return image.size

    suffix = image_path.suffix.lower()
    if suffix == ".png":
        return read_png_size(image_path)
    if suffix in {".jpg", ".jpeg"}:
        return read_jpeg_size(image_path)
    if suffix == ".bmp":
        return read_bmp_size(image_path)
    if suffix == ".gif":
        return read_gif_size(image_path)

    raise ValueError(
        "Pillow is not installed and the image format is unsupported by the "
        f"built-in reader: {image_path}"
    )


def to_float(value: Any, *, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid bbox field {field_name!r}: {value!r}") from exc


def xywh_from_point_list(points: list[Any]) -> tuple[float, float, float, float] | None:
    if not points:
        return None

    x_values: list[float] = []
    y_values: list[float] = []
    for point in points:
        if isinstance(point, dict):
            x_value = point.get("x")
            y_value = point.get("y")
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            x_value = point[0]
            y_value = point[1]
        else:
            return None

        x_values.append(to_float(x_value, field_name="point.x"))
        y_values.append(to_float(y_value, field_name="point.y"))

    x_min = min(x_values)
    y_min = min(y_values)
    x_max = max(x_values)
    y_max = max(y_values)
    return x_min, y_min, x_max - x_min, y_max - y_min


def parse_bbox_dict(bbox: dict[str, Any]) -> tuple[float, float, float, float]:
    normalized = {str(key).lower(): value for key, value in bbox.items()}

    if {"x", "y", "w", "h"} <= normalized.keys():
        return (
            to_float(normalized["x"], field_name="x"),
            to_float(normalized["y"], field_name="y"),
            to_float(normalized["w"], field_name="w"),
            to_float(normalized["h"], field_name="h"),
        )

    if {"x", "y", "width", "height"} <= normalized.keys():
        return (
            to_float(normalized["x"], field_name="x"),
            to_float(normalized["y"], field_name="y"),
            to_float(normalized["width"], field_name="width"),
            to_float(normalized["height"], field_name="height"),
        )

    if {"left", "top", "width", "height"} <= normalized.keys():
        return (
            to_float(normalized["left"], field_name="left"),
            to_float(normalized["top"], field_name="top"),
            to_float(normalized["width"], field_name="width"),
            to_float(normalized["height"], field_name="height"),
        )

    if {"xmin", "ymin", "xmax", "ymax"} <= normalized.keys():
        x_min = to_float(normalized["xmin"], field_name="xmin")
        y_min = to_float(normalized["ymin"], field_name="ymin")
        x_max = to_float(normalized["xmax"], field_name="xmax")
        y_max = to_float(normalized["ymax"], field_name="ymax")
        return x_min, y_min, x_max - x_min, y_max - y_min

    if {"x1", "y1", "x2", "y2"} <= normalized.keys():
        x_min = to_float(normalized["x1"], field_name="x1")
        y_min = to_float(normalized["y1"], field_name="y1")
        x_max = to_float(normalized["x2"], field_name="x2")
        y_max = to_float(normalized["y2"], field_name="y2")
        return x_min, y_min, x_max - x_min, y_max - y_min

    if "xywh" in normalized and isinstance(normalized["xywh"], (list, tuple)):
        values = normalized["xywh"]
        if len(values) >= 4:
            return (
                to_float(values[0], field_name="xywh[0]"),
                to_float(values[1], field_name="xywh[1]"),
                to_float(values[2], field_name="xywh[2]"),
                to_float(values[3], field_name="xywh[3]"),
            )

    for key in ("points", "vertices"):
        if key in normalized and isinstance(normalized[key], list):
            parsed = xywh_from_point_list(normalized[key])
            if parsed is not None:
                return parsed

    for key in ("bbox", "rect", "rectangle"):
        nested_value = normalized.get(key)
        if isinstance(nested_value, dict):
            return parse_bbox_dict(nested_value)

    raise ValueError(f"Unsupported bbox schema: {bbox}")


def iter_bbox_items(bbox_value: Any) -> list[dict[str, Any]]:
    if isinstance(bbox_value, dict):
        return [bbox_value]
    if isinstance(bbox_value, list):
        return [item for item in bbox_value if isinstance(item, dict)]
    return []


def clip_bbox_to_image(
    x: float,
    y: float,
    width: float,
    height: float,
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image size must be positive.")

    x1 = max(0.0, min(x, float(image_width)))
    y1 = max(0.0, min(y, float(image_height)))
    x2 = max(0.0, min(x + width, float(image_width)))
    y2 = max(0.0, min(y + height, float(image_height)))

    clipped_width = x2 - x1
    clipped_height = y2 - y1
    if clipped_width <= 0 or clipped_height <= 0:
        raise ValueError(
            f"BBox collapses outside the image: {(x, y, width, height)} for "
            f"{image_width}x{image_height}"
        )

    return x1, y1, clipped_width, clipped_height


def to_yolo_line(
    class_index: int,
    bbox: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> str:
    x, y, width, height = clip_bbox_to_image(
        bbox[0], bbox[1], bbox[2], bbox[3], image_width, image_height
    )
    center_x = (x + (width / 2.0)) / image_width
    center_y = (y + (height / 2.0)) / image_height
    norm_width = width / image_width
    norm_height = height / image_height
    return (
        f"{class_index} "
        f"{center_x:.6f} {center_y:.6f} {norm_width:.6f} {norm_height:.6f}"
    )


def build_positive_label_lines(
    record: ManifestRecord,
    image_width: int,
    image_height: int,
) -> list[str]:
    class_index = get_detection_class_index(record.disease_code)
    if class_index is None:
        raise ValueError(
            f"Manifest row {record.line_number} has non-target disease code "
            f"{record.disease_code!r} marked for detection."
        )

    data = load_json(record.json_path)
    annotations = extract_annotations(data)
    if not annotations:
        raise ValueError(f"No annotations found in {record.json_path}.")

    label_lines: list[str] = []
    for annotation in annotations:
        annotation_disease = normalize_code(annotation.get("disease"))
        if annotation_disease and annotation_disease != record.disease_code:
            raise ValueError(
                f"Mixed disease codes in {record.json_path}: manifest has "
                f"{record.disease_code!r}, annotation has {annotation_disease!r}."
            )

        for bbox_item in iter_bbox_items(annotation.get("bbox")):
            parsed_bbox = parse_bbox_dict(bbox_item)
            label_lines.append(
                to_yolo_line(class_index, parsed_bbox, image_width, image_height)
            )

    if not label_lines:
        raise ValueError(f"No top-level bbox entries found in {record.json_path}.")

    if record.top_level_bbox_count > 0 and len(label_lines) != record.top_level_bbox_count:
        raise ValueError(
            f"Manifest row {record.line_number} expected {record.top_level_bbox_count} "
            f"bbox entries but converted {len(label_lines)}."
        )

    return label_lines


def write_label_file(label_path: Path, label_lines: list[str]) -> None:
    label_path.parent.mkdir(parents=True, exist_ok=True)
    with label_path.open("w", encoding="utf-8", newline="\n") as handle:
        if label_lines:
            handle.write("\n".join(label_lines))
            handle.write("\n")


def write_dataset_yaml(output_root: Path, split_counts: dict[str, int]) -> Path:
    dataset_yaml_path = output_root / "dataset.yaml"
    lines = [
        f"path: {output_root}",
        f"nc: {len(DETECTION_TARGETS)}",
    ]

    for split_name in ("train", "val", "test"):
        if split_counts.get(split_name, 0) > 0:
            lines.append(f"{split_name}: images/{split_name}")

    lines.append("names:")
    for target in DETECTION_TARGETS:
        lines.append(f"  - {target.class_name}")

    dataset_yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dataset_yaml_path


def print_summary(
    output_root: Path,
    dataset_yaml_path: Path,
    *,
    total_rows: int,
    selected_rows: int,
    positive_samples: int,
    negative_samples: int,
    boxes_written: int,
    split_counts: dict[str, int],
) -> None:
    print(f"Output root: {output_root}")
    print(f"Dataset YAML: {dataset_yaml_path}")
    print(f"Manifest rows read: {total_rows}")
    print(f"Rows converted: {selected_rows}")
    print(f"Positive samples: {positive_samples}")
    print(f"Negative samples: {negative_samples}")
    print(f"BBox labels written: {boxes_written}")

    for split_name in ("train", "val", "test"):
        count = split_counts.get(split_name, 0)
        if count > 0:
            print(f"Split {split_name}: {count}")

    if split_counts.get("train", 0) == 0:
        print("Warning: no train split detected in the manifest.", file=sys.stderr)
    if split_counts.get("val", 0) == 0:
        print("Warning: no val split detected in the manifest.", file=sys.stderr)


def convert_manifest(
    manifest_path: Path,
    output_root: Path,
    *,
    image_mode: str,
    default_split: str,
) -> int:
    records, total_rows = load_manifest_records(manifest_path)
    if not records:
        raise SystemExit("No manifest rows with use_for_detection=true were found.")

    output_root.mkdir(parents=True, exist_ok=True)
    split_counts = {"train": 0, "val": 0, "test": 0}
    positive_samples = 0
    negative_samples = 0
    boxes_written = 0
    destination_sources: dict[Path, Path] = {}

    for record in records:
        if not record.image_path.exists():
            raise SystemExit(
                f"Manifest row {record.line_number} points to a missing image: "
                f"{record.image_path}"
            )

        split_name, relative_tail = infer_split_and_tail(record, default_split)
        if record.image_path.suffix.lower() not in IMAGE_SUFFIXES:
            raise SystemExit(
                f"Manifest row {record.line_number} uses an unsupported image suffix: "
                f"{record.image_path}"
            )

        destination_image_path = output_root / "images" / split_name / relative_tail
        destination_label_path = (
            output_root / "labels" / split_name / relative_tail.with_suffix(".txt")
        )

        previous_source = destination_sources.get(destination_image_path)
        if previous_source is not None and previous_source != record.image_path:
            raise SystemExit(
                f"Multiple source images map to the same output path: "
                f"{destination_image_path}"
            )
        destination_sources[destination_image_path] = record.image_path

        materialize_image(record.image_path, destination_image_path, image_mode)
        image_width, image_height = read_image_size(record.image_path)

        if record.is_negative_sample:
            label_lines: list[str] = []
            negative_samples += 1
        else:
            if not record.json_path.exists():
                raise SystemExit(
                    f"Manifest row {record.line_number} points to a missing JSON label: "
                    f"{record.json_path}"
                )
            label_lines = build_positive_label_lines(record, image_width, image_height)
            positive_samples += 1
            boxes_written += len(label_lines)

        write_label_file(destination_label_path, label_lines)
        split_counts[split_name] = split_counts.get(split_name, 0) + 1

    dataset_yaml_path = write_dataset_yaml(output_root, split_counts)
    print_summary(
        output_root,
        dataset_yaml_path,
        total_rows=total_rows,
        selected_rows=len(records),
        positive_samples=positive_samples,
        negative_samples=negative_samples,
        boxes_written=boxes_written,
        split_counts=split_counts,
    )
    return 0


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()

    if not manifest_path.exists() or not manifest_path.is_file():
        raise SystemExit(f"--manifest must point to an existing CSV file: {manifest_path}")

    return convert_manifest(
        manifest_path,
        output_root,
        image_mode=args.image_mode,
        default_split=args.default_split,
    )


if __name__ == "__main__":
    raise SystemExit(main())
