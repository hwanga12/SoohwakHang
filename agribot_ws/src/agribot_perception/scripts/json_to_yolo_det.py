#!/usr/bin/env python3

# 이 모듈은 인지와 추론 패키지에서 json to yolo det 기능을 담당한다.
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import shutil
import struct
import sys
from collections import Counter
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

SKIPPED_FIELDNAMES = [
    "line_number",
    "split",
    "image_path",
    "json_path",
    "disease_code",
    "issue_type",
    "detail",
    "annotation_index",
    "bbox_index",
    "bbox_raw",
]


@dataclass(frozen=True, slots=True)
class ManifestRecord:
    # manifest 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    line_number: int
    image_path: Path
    image_rel_path: str
    json_path: Path | None
    json_rel_path: str
    disease_code: str
    is_negative_sample: bool
    top_level_bbox_count: int
    source_split: str


@dataclass(frozen=True, slots=True)
class LabelBuildResult:
    # 라벨 build 처리 결과를 한 번에 전달하기 위한 클래스를 정의한다.
    label_lines: list[str]
    raw_bbox_count: int
    clipped_bbox_count: int
    collapsed_bbox_count: int
    skipped_entries: list[dict[str, str]]
    row_skip_reason: str | None


def parse_args() -> argparse.Namespace:
    # args를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
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
    # bool text를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def parse_int_text(value: Any, *, default: int = 0) -> int:
    # INT text를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    text = str(value).strip()
    if not text:
        return default
    return int(text)


def resolve_manifest_path(path_text: str, manifest_path: Path) -> Path:
    # 현재 입력 조건을 바탕으로 manifest 경로를 계산하거나 결정한다.
    raw_path = Path(path_text).expanduser()
    if raw_path.is_absolute():
        return raw_path
    return (manifest_path.parent / raw_path).resolve()


def extract_annotations(data: dict[str, Any]) -> list[dict[str, Any]]:
    # 원본 데이터에서 annotations만 골라 추출한다.
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
    # JSON 데이터를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_manifest_records(manifest_path: Path) -> tuple[list[ManifestRecord], int]:
    # manifest 기록 목록를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
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
            is_negative_sample = parse_bool_text(row.get("is_negative_sample", "")) or (
                is_negative_sample_disease(disease_code)
            )

            if not image_path_text:
                raise SystemExit(f"Manifest row {line_number} has an empty image_path.")
            if not disease_code:
                raise SystemExit(f"Manifest row {line_number} has an empty disease_code.")
            if not is_negative_sample and not json_path_text:
                raise SystemExit(
                    f"Manifest row {line_number} has an empty json_path for a positive sample."
                )

            selected_records.append(
                ManifestRecord(
                    line_number=line_number,
                    image_path=resolve_manifest_path(image_path_text, manifest_path),
                    image_rel_path=str(row.get("image_rel_path", "")).strip(),
                    json_path=resolve_manifest_path(json_path_text, manifest_path)
                    if json_path_text
                    else None,
                    json_rel_path=str(row.get("json_rel_path", "")).strip(),
                    disease_code=disease_code,
                    is_negative_sample=is_negative_sample,
                    top_level_bbox_count=parse_int_text(
                        row.get("top_level_bbox_count", ""),
                        default=0,
                    ),
                    source_split=str(row.get("source_split", "")).strip(),
                )
            )

    return selected_records, total_rows


def normalize_split_name(value: str) -> str | None:
    # split 이름를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    return SPLIT_ALIASES.get(value.strip().lower())


def path_parts(path_text: str) -> list[str]:
    # 경로 parts 정보를 계산해 반환한다.
    raw_path = Path(path_text)
    return [part for part in raw_path.parts if part not in {"", raw_path.anchor}]


def relative_tail_from_path(path_text: str, fallback_name: str) -> Path:
    # relative tail 경로 정보를 계산해 반환한다.
    if not path_text:
        return Path(fallback_name)

    parts = path_parts(path_text)
    if not parts:
        return Path(fallback_name)

    normalized_first = normalize_split_name(parts[0])
    if normalized_first is not None:
        parts = parts[1:] or [fallback_name]

    return Path(*parts) if parts else Path(fallback_name)


def infer_split_and_tail(record: ManifestRecord, default_split: str) -> tuple[str, Path]:
    # 입력 데이터를 바탕으로 split AND tail를 추론한다.
    explicit_split = normalize_split_name(record.source_split)
    if explicit_split is not None:
        return explicit_split, relative_tail_from_path(record.image_rel_path, record.image_path.name)

    source_candidates = [
        record.image_rel_path,
        record.json_rel_path,
        str(record.image_path),
        str(record.json_path) if record.json_path else "",
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
    # existing 파일를 정리하거나 제거한다.
    if path.is_symlink() or path.exists():
        path.unlink()


def materialize_image(source_path: Path, destination_path: Path, image_mode: str) -> None:
    # materialize 이미지 정보를 계산해 반환한다.
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
    # PNG size를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    with image_path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG file.")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def read_gif_size(image_path: Path) -> tuple[int, int]:
    # GIF size를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    with image_path.open("rb") as handle:
        header = handle.read(10)
    if header[:6] not in {b"GIF87a", b"GIF89a"}:
        raise ValueError("Not a GIF file.")
    width, height = struct.unpack("<HH", header[6:10])
    return width, height


def read_bmp_size(image_path: Path) -> tuple[int, int]:
    # BMP size를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    with image_path.open("rb") as handle:
        header = handle.read(26)
    if header[:2] != b"BM":
        raise ValueError("Not a BMP file.")
    width, height = struct.unpack("<II", header[18:26])
    return width, abs(height)


def read_jpeg_size(image_path: Path) -> tuple[int, int]:
    # jpeg size를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
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
    # 이미지 size를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
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
    # 현재 값을 float 형식으로 변환한다.
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid bbox field {field_name!r}: {value!r}") from exc


def xywh_from_point_list(points: list[Any]) -> tuple[float, float, float, float] | None:
    # xywh point 목록 정보를 계산해 반환한다.
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
    # 바운딩 박스 dict를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
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
    # iter 경계 상자 items 정보를 계산해 반환한다.
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
) -> tuple[tuple[float, float, float, float] | None, bool]:
    # clip 경계 상자 이미지 정보를 계산해 반환한다.
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image size must be positive.")

    x1 = max(0.0, min(x, float(image_width)))
    y1 = max(0.0, min(y, float(image_height)))
    x2 = max(0.0, min(x + width, float(image_width)))
    y2 = max(0.0, min(y + height, float(image_height)))

    clipped = any(
        abs(before - after) > 1e-9
        for before, after in ((x, x1), (y, y1), (x + width, x2), (y + height, y2))
    )
    clipped_width = x2 - x1
    clipped_height = y2 - y1
    if clipped_width <= 0 or clipped_height <= 0:
        return None, clipped

    return (x1, y1, clipped_width, clipped_height), clipped


def to_yolo_line(
    class_index: int,
    bbox: tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> str:
    # 현재 값을 yolo line 형식으로 변환한다.
    x, y, width, height = bbox
    center_x = (x + (width / 2.0)) / image_width
    center_y = (y + (height / 2.0)) / image_height
    norm_width = width / image_width
    norm_height = height / image_height
    return (
        f"{class_index} "
        f"{center_x:.6f} {center_y:.6f} {norm_width:.6f} {norm_height:.6f}"
    )


def make_skipped_entry(
    record: ManifestRecord,
    split_name: str,
    *,
    issue_type: str,
    detail: str,
    annotation_index: int | None = None,
    bbox_index: int | None = None,
    bbox_raw: str = "",
) -> dict[str, str]:
    # skipped entry를 새로 만들어 다음 처리 단계로 넘긴다.
    return {
        "line_number": str(record.line_number),
        "split": split_name,
        "image_path": str(record.image_path),
        "json_path": str(record.json_path) if record.json_path else "",
        "disease_code": record.disease_code,
        "issue_type": issue_type,
        "detail": detail,
        "annotation_index": "" if annotation_index is None else str(annotation_index),
        "bbox_index": "" if bbox_index is None else str(bbox_index),
        "bbox_raw": bbox_raw,
    }


def build_positive_label_lines(
    record: ManifestRecord,
    image_width: int,
    image_height: int,
    split_name: str,
) -> LabelBuildResult:
    # positive 라벨 lines를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    class_index = get_detection_class_index(record.disease_code)
    if class_index is None:
        raise ValueError(
            f"Manifest row {record.line_number} has non-target disease code "
            f"{record.disease_code!r} marked for detection."
        )
    if record.json_path is None:
        raise ValueError(f"Manifest row {record.line_number} is missing json_path.")

    data = load_json(record.json_path)
    annotations = extract_annotations(data)
    if not annotations:
        raise ValueError(f"No annotations found in {record.json_path}.")

    label_lines: list[str] = []
    raw_bbox_count = 0
    clipped_bbox_count = 0
    collapsed_bbox_count = 0
    skipped_entries: list[dict[str, str]] = []

    for annotation_index, annotation in enumerate(annotations):
        annotation_disease = normalize_code(annotation.get("disease"))
        if annotation_disease and annotation_disease != record.disease_code:
            raise ValueError(
                f"Mixed disease codes in {record.json_path}: manifest has "
                f"{record.disease_code!r}, annotation has {annotation_disease!r}."
            )

        for bbox_index, bbox_item in enumerate(iter_bbox_items(annotation.get("bbox"))):
            raw_bbox_count += 1
            parsed_bbox = parse_bbox_dict(bbox_item)
            clipped_bbox, was_clipped = clip_bbox_to_image(
                parsed_bbox[0],
                parsed_bbox[1],
                parsed_bbox[2],
                parsed_bbox[3],
                image_width,
                image_height,
            )
            if clipped_bbox is None:
                collapsed_bbox_count += 1
                bbox_raw = json.dumps(bbox_item, ensure_ascii=False, sort_keys=True)
                logging.warning(
                    "Skipped collapsed bbox for row %s (%s).",
                    record.line_number,
                    record.image_path.name,
                )
                skipped_entries.append(
                    make_skipped_entry(
                        record,
                        split_name,
                        issue_type="collapsed_bbox",
                        detail="bbox_collapsed_after_clipping",
                        annotation_index=annotation_index,
                        bbox_index=bbox_index,
                        bbox_raw=bbox_raw,
                    )
                )
                continue

            if was_clipped:
                clipped_bbox_count += 1
                logging.warning(
                    "Clipped bbox for row %s (%s) to image bounds.",
                    record.line_number,
                    record.image_path.name,
                )

            label_lines.append(
                to_yolo_line(class_index, clipped_bbox, image_width, image_height)
            )

    if raw_bbox_count == 0:
        raise ValueError(f"No top-level bbox entries found in {record.json_path}.")

    if record.top_level_bbox_count > 0 and raw_bbox_count != record.top_level_bbox_count:
        raise ValueError(
            f"Manifest row {record.line_number} expected {record.top_level_bbox_count} "
            f"bbox entries but parsed {raw_bbox_count}."
        )

    row_skip_reason = None if label_lines else "no_valid_bbox_after_clipping"
    return LabelBuildResult(
        label_lines=label_lines,
        raw_bbox_count=raw_bbox_count,
        clipped_bbox_count=clipped_bbox_count,
        collapsed_bbox_count=collapsed_bbox_count,
        skipped_entries=skipped_entries,
        row_skip_reason=row_skip_reason,
    )


def write_label_file(label_path: Path, label_lines: list[str]) -> None:
    # 라벨 파일를 파일이나 저장소에 기록한다.
    label_path.parent.mkdir(parents=True, exist_ok=True)
    with label_path.open("w", encoding="utf-8", newline="\n") as handle:
        if label_lines:
            handle.write("\n".join(label_lines))
            handle.write("\n")


def write_dataset_yaml(output_root: Path, split_counts: dict[str, int]) -> Path:
    # dataset YAML 데이터를 파일이나 저장소에 기록한다.
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


def write_skipped_csv(skipped_entries: list[dict[str, str]], output_path: Path) -> Path:
    # skipped CSV를 파일이나 저장소에 기록한다.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SKIPPED_FIELDNAMES)
        writer.writeheader()
        writer.writerows(skipped_entries)
    return output_path


def write_stats_json(output_path: Path, payload: dict[str, Any]) -> Path:
    # stats JSON 데이터를 파일이나 저장소에 기록한다.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def print_summary(
    output_root: Path,
    dataset_yaml_path: Path,
    stats_path: Path,
    skipped_csv_path: Path,
    *,
    total_rows: int,
    selected_rows: int,
    converted_rows: int,
    skipped_rows: int,
    positive_samples: int,
    negative_samples: int,
    boxes_written: int,
    clipped_bbox_count: int,
    collapsed_bbox_count: int,
    split_counts: dict[str, int],
) -> None:
    # print 요약 정보를 계산해 반환한다.
    print(f"Output root: {output_root}")
    print(f"Dataset YAML: {dataset_yaml_path}")
    print(f"Stats JSON: {stats_path}")
    print(f"Skipped CSV: {skipped_csv_path}")
    print(f"Manifest rows read: {total_rows}")
    print(f"Rows selected: {selected_rows}")
    print(f"Rows converted: {converted_rows}")
    print(f"Rows skipped: {skipped_rows}")
    print(f"Positive samples: {positive_samples}")
    print(f"Negative samples: {negative_samples}")
    print(f"BBox labels written: {boxes_written}")
    print(f"Clipped bboxes: {clipped_bbox_count}")
    print(f"Collapsed bboxes skipped: {collapsed_bbox_count}")

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
    # manifest를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    records, total_rows = load_manifest_records(manifest_path)
    if not records:
        raise SystemExit("No manifest rows with use_for_detection=true were found.")

    output_root.mkdir(parents=True, exist_ok=True)
    split_counts = {"train": 0, "val": 0, "test": 0}
    selected_by_disease = Counter(record.disease_code for record in records)
    converted_by_disease: Counter[str] = Counter()
    skipped_by_reason: Counter[str] = Counter()
    positive_samples = 0
    negative_samples = 0
    boxes_written = 0
    clipped_bbox_count = 0
    collapsed_bbox_count = 0
    skipped_rows = 0
    skipped_entries: list[dict[str, str]] = []
    destination_sources: dict[Path, Path] = {}

    for record in records:
        if not record.image_path.exists():
            raise SystemExit(
                f"Manifest row {record.line_number} points to a missing image: "
                f"{record.image_path}"
            )
        if record.image_path.suffix.lower() not in IMAGE_SUFFIXES:
            raise SystemExit(
                f"Manifest row {record.line_number} uses an unsupported image suffix: "
                f"{record.image_path}"
            )
        if not record.is_negative_sample:
            if record.json_path is None:
                raise SystemExit(
                    f"Manifest row {record.line_number} is missing json_path for a positive sample."
                )
            if not record.json_path.exists():
                raise SystemExit(
                    f"Manifest row {record.line_number} points to a missing JSON: "
                    f"{record.json_path}"
                )

        split_name, relative_tail = infer_split_and_tail(record, default_split)
        destination_image_path = output_root / "images" / split_name / relative_tail
        destination_label_path = (
            output_root / "labels" / split_name / relative_tail.with_suffix(".txt")
        )
        image_width, image_height = read_image_size(record.image_path)

        label_lines: list[str]
        if record.is_negative_sample:
            label_lines = []
        else:
            try:
                label_result = build_positive_label_lines(
                    record,
                    image_width,
                    image_height,
                    split_name,
                )
            except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
                raise SystemExit(str(exc)) from exc

            boxes_written += len(label_result.label_lines)
            clipped_bbox_count += label_result.clipped_bbox_count
            collapsed_bbox_count += label_result.collapsed_bbox_count
            skipped_entries.extend(label_result.skipped_entries)
            if label_result.row_skip_reason is not None:
                skipped_rows += 1
                skipped_by_reason[label_result.row_skip_reason] += 1
                skipped_entries.append(
                    make_skipped_entry(
                        record,
                        split_name,
                        issue_type="row_skipped",
                        detail=label_result.row_skip_reason,
                    )
                )
                logging.warning(
                    "Skipped row %s (%s) because no valid bbox remained after clipping.",
                    record.line_number,
                    record.image_path.name,
                )
                continue

            label_lines = label_result.label_lines

        existing_source = destination_sources.get(destination_image_path)
        if existing_source is not None and existing_source != record.image_path:
            raise SystemExit(
                f"Destination collision at {destination_image_path}: "
                f"{existing_source} vs {record.image_path}"
            )

        materialize_image(record.image_path, destination_image_path, image_mode)
        write_label_file(destination_label_path, label_lines)
        destination_sources[destination_image_path] = record.image_path

        split_counts[split_name] = split_counts.get(split_name, 0) + 1
        converted_by_disease[record.disease_code] += 1
        if record.is_negative_sample:
            negative_samples += 1
        else:
            positive_samples += 1

    dataset_yaml_path = write_dataset_yaml(output_root, split_counts)
    skipped_csv_path = write_skipped_csv(skipped_entries, output_root / "skipped.csv")
    stats_payload = {
        "manifest_path": str(manifest_path),
        "output_root": str(output_root),
        "total_rows": total_rows,
        "selected_rows": len(records),
        "converted_rows": positive_samples + negative_samples,
        "skipped_rows": skipped_rows,
        "positive_samples": positive_samples,
        "negative_samples": negative_samples,
        "boxes_written": boxes_written,
        "clipped_bbox_count": clipped_bbox_count,
        "collapsed_bbox_count": collapsed_bbox_count,
        "split_counts": split_counts,
        "selected_by_disease_code": dict(sorted(selected_by_disease.items())),
        "converted_by_disease_code": dict(sorted(converted_by_disease.items())),
        "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
        "class_names": [target.class_name for target in DETECTION_TARGETS],
    }
    stats_path = write_stats_json(output_root / "stats.json", stats_payload)

    print_summary(
        output_root,
        dataset_yaml_path,
        stats_path,
        skipped_csv_path,
        total_rows=total_rows,
        selected_rows=len(records),
        converted_rows=positive_samples + negative_samples,
        skipped_rows=skipped_rows,
        positive_samples=positive_samples,
        negative_samples=negative_samples,
        boxes_written=boxes_written,
        clipped_bbox_count=clipped_bbox_count,
        collapsed_bbox_count=collapsed_bbox_count,
        split_counts=split_counts,
    )
    return 0


def main() -> int:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
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
