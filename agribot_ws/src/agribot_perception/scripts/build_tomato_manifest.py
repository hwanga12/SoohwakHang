#!/usr/bin/env python3

# 이 모듈은 인지와 추론 패키지에서 build tomato manifest 기능을 담당한다.
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from agribot_perception.utils.codebook import (  # noqa: E402
    get_crop_entry,
    get_disease_entry,
    is_detection_target_disease,
    is_negative_sample_disease,
    is_tomato_crop,
    normalize_code,
)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
MANIFEST_FIELDNAMES = [
    "image_path",
    "image_rel_path",
    "json_path",
    "json_rel_path",
    "crop_code",
    "crop_name",
    "disease_code",
    "disease_name_en",
    "disease_name_ko",
    "risk",
    "top_level_bbox_count",
    "is_tomato",
    "is_detection_target",
    "is_negative_sample",
    "use_for_detection",
    "skip_reason",
]


def parse_args() -> argparse.Namespace:
    # args를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    parser = argparse.ArgumentParser(
        description="Build a tomato detection manifest CSV from AI Hub 525 raw labels."
    )
    parser.add_argument(
        "--dataset-root",
        required=True,
        help="Root directory containing raw AI Hub JSON labels and images.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="CSV output path. The file is written as UTF-8 with BOM (utf-8-sig).",
    )
    return parser.parse_args()


def is_present(value: Any) -> bool:
    # present인지 여부를 불리언 값으로 판단한다.
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def load_json(json_path: Path) -> dict[str, Any]:
    # JSON 데이터를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_annotations(data: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    # 원본 데이터에서 annotations만 골라 추출한다.
    if "annotation" in data:
        raw = data.get("annotation")
        key_name = "annotation"
    elif "annotations" in data:
        raw = data.get("annotations")
        key_name = "annotations"
    else:
        return [], "missing"

    if raw is None:
        return [], key_name
    if isinstance(raw, dict):
        return [raw], key_name
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)], key_name
    return [], key_name


def build_image_index(dataset_root: Path) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    # 이미지 index를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    image_by_name: dict[str, list[Path]] = defaultdict(list)
    image_by_stem: dict[str, list[Path]] = defaultdict(list)

    for path in dataset_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        image_by_name[path.name].append(path)
        image_by_stem[path.stem].append(path)

    return image_by_name, image_by_stem


def dedupe_paths(paths: list[Path]) -> list[Path]:
    # dedupe 경로 정보를 계산해 반환한다.
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        unique_paths.append(path)
        seen.add(path)
    return unique_paths


def choose_best_candidate(json_path: Path, candidates: list[Path]) -> tuple[Path | None, bool]:
    # best 후보 가운데 최종 대상을 고른다.
    unique_candidates = dedupe_paths(candidates)
    if not unique_candidates:
        return None, False
    if len(unique_candidates) == 1:
        return unique_candidates[0], False

    same_parent = [path for path in unique_candidates if path.parent.name == json_path.parent.name]
    if len(same_parent) == 1:
        return same_parent[0], True

    exact_stem = [path for path in unique_candidates if path.stem == json_path.stem]
    if len(exact_stem) == 1:
        return exact_stem[0], True

    sorted_candidates = sorted(unique_candidates, key=lambda path: (len(path.parts), str(path)))
    return sorted_candidates[0], True


def resolve_image_path(
    json_path: Path,
    dataset_root: Path,
    description_image: Any,
    image_by_name: dict[str, list[Path]],
    image_by_stem: dict[str, list[Path]],
) -> tuple[Path | None, bool]:
    # 현재 입력 조건을 바탕으로 이미지 경로를 계산하거나 결정한다.
    candidates: list[Path] = []

    if is_present(description_image):
        image_name = str(description_image).strip()
        image_path = Path(image_name)
        direct_candidates = [
            json_path.parent / image_path,
            dataset_root / image_path,
            json_path.parent / image_path.name,
            dataset_root / image_path.name,
        ]
        for candidate in direct_candidates:
            if candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES:
                candidates.append(candidate)

        candidates.extend(image_by_name.get(image_path.name, []))

    candidates.extend(image_by_stem.get(json_path.stem, []))
    return choose_best_candidate(json_path, candidates)


def count_bbox_items(bbox_value: Any) -> int:
    # 개수 경계 상자 items 정보를 계산해 반환한다.
    if bbox_value is None:
        return 0
    if isinstance(bbox_value, dict):
        return 1
    if isinstance(bbox_value, list):
        return sum(1 for item in bbox_value if isinstance(item, dict))
    return 0


def count_top_level_bbox_items(annotations: list[dict[str, Any]]) -> int:
    # 개수 top level 경계 상자 items 정보를 계산해 반환한다.
    return sum(count_bbox_items(annotation.get("bbox")) for annotation in annotations)


def collect_unique_values(annotations: list[dict[str, Any]], field_name: str) -> list[str]:
    # unique values를 모아 순회하기 쉬운 형태로 정리한다.
    values = {
        normalize_code(annotation.get(field_name))
        for annotation in annotations
        if normalize_code(annotation.get(field_name))
    }
    return sorted(values)


def join_values(values: list[str]) -> str:
    # join 값 정보를 계산해 반환한다.
    return "|".join(values)


def join_entry_names(
    codes: list[str],
    getter: Callable[[Any], Any],
    attribute_name: str,
) -> str:
    # join 항목 names 정보를 계산해 반환한다.
    names: list[str] = []
    seen: set[str] = set()
    for code in codes:
        entry = getter(code)
        if entry is None:
            continue
        name = getattr(entry, attribute_name, "")
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return "|".join(names)


def to_relative_string(path: Path | None, dataset_root: Path) -> str:
    # 현재 값을 relative string 형식으로 변환한다.
    if path is None:
        return ""
    try:
        return str(path.relative_to(dataset_root))
    except ValueError:
        return str(path)


def bool_to_text(value: bool) -> str:
    # bool 텍스트 정보를 계산해 반환한다.
    return "true" if value else "false"


def determine_skip_reason(
    annotations: list[dict[str, Any]],
    crop_codes: list[str],
    disease_codes: list[str],
    *,
    is_tomato: bool,
    is_detection_target: bool,
    is_negative_sample: bool,
    image_path: Path | None,
    image_match_ambiguous: bool,
    top_level_bbox_count: int,
) -> str:
    # determine skip reason 정보를 계산해 반환한다.
    if not annotations:
        return "missing_annotation"
    if len(crop_codes) > 1:
        return "multiple_crop_codes"
    if len(disease_codes) > 1:
        return "multiple_disease_codes"
    if not crop_codes:
        return "missing_crop_code"
    if not disease_codes:
        return "missing_disease_code"
    if not is_tomato:
        return "non_tomato_crop"
    if image_path is None:
        return "missing_image_path"
    if image_match_ambiguous:
        return "ambiguous_image_match"
    if is_detection_target:
        if top_level_bbox_count <= 0:
            return "missing_top_level_bbox"
        return ""
    if is_negative_sample:
        if top_level_bbox_count > 0:
            return "negative_sample_has_top_level_bbox"
        return ""
    return "non_target_non_negative_disease"


def build_base_row(json_path: Path, dataset_root: Path) -> dict[str, Any]:
    # base ROW를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return {
        "image_path": "",
        "image_rel_path": "",
        "json_path": str(json_path.resolve()),
        "json_rel_path": to_relative_string(json_path.resolve(), dataset_root.resolve()),
        "crop_code": "",
        "crop_name": "",
        "disease_code": "",
        "disease_name_en": "",
        "disease_name_ko": "",
        "risk": "",
        "top_level_bbox_count": 0,
        "is_tomato": "false",
        "is_detection_target": "false",
        "is_negative_sample": "false",
        "use_for_detection": "false",
        "skip_reason": "",
    }


def build_manifest_rows(dataset_root: Path) -> list[dict[str, Any]]:
    # manifest rows를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    image_by_name, image_by_stem = build_image_index(dataset_root)
    json_paths = sorted(
        path for path in dataset_root.rglob("*") if path.is_file() and path.suffix.lower() == ".json"
    )

    rows: list[dict[str, Any]] = []
    resolved_dataset_root = dataset_root.resolve()

    for json_path in json_paths:
        row = build_base_row(json_path, resolved_dataset_root)

        try:
            data = load_json(json_path)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            row["skip_reason"] = "malformed_json"
            rows.append(row)
            continue

        annotations, _ = extract_annotations(data)
        description = data.get("description") if isinstance(data.get("description"), dict) else {}

        crop_codes = collect_unique_values(annotations, "crop")
        disease_codes = collect_unique_values(annotations, "disease")
        risk_values = collect_unique_values(annotations, "risk")
        top_level_bbox_count = count_top_level_bbox_items(annotations)

        image_path, image_match_ambiguous = resolve_image_path(
            json_path=json_path,
            dataset_root=resolved_dataset_root,
            description_image=description.get("image"),
            image_by_name=image_by_name,
            image_by_stem=image_by_stem,
        )

        single_crop_code = crop_codes[0] if len(crop_codes) == 1 else ""
        single_disease_code = disease_codes[0] if len(disease_codes) == 1 else ""

        is_tomato = bool(single_crop_code) and is_tomato_crop(single_crop_code)
        is_detection_target = bool(single_disease_code) and is_detection_target_disease(single_disease_code)
        is_negative_sample = bool(single_disease_code) and is_negative_sample_disease(single_disease_code)

        skip_reason = determine_skip_reason(
            annotations,
            crop_codes,
            disease_codes,
            is_tomato=is_tomato,
            is_detection_target=is_detection_target,
            is_negative_sample=is_negative_sample,
            image_path=image_path,
            image_match_ambiguous=image_match_ambiguous,
            top_level_bbox_count=top_level_bbox_count,
        )

        row.update(
            {
                "image_path": str(image_path.resolve()) if image_path else "",
                "image_rel_path": to_relative_string(image_path.resolve(), resolved_dataset_root)
                if image_path
                else "",
                "crop_code": join_values(crop_codes),
                "crop_name": join_entry_names(crop_codes, get_crop_entry, "name_en"),
                "disease_code": join_values(disease_codes),
                "disease_name_en": join_entry_names(disease_codes, get_disease_entry, "name_en"),
                "disease_name_ko": join_entry_names(disease_codes, get_disease_entry, "name_ko"),
                "risk": join_values(risk_values),
                "top_level_bbox_count": top_level_bbox_count,
                "is_tomato": bool_to_text(is_tomato),
                "is_detection_target": bool_to_text(is_detection_target),
                "is_negative_sample": bool_to_text(is_negative_sample),
                "use_for_detection": bool_to_text(skip_reason == ""),
                "skip_reason": skip_reason,
            }
        )
        rows.append(row)

    return rows


def write_manifest(rows: list[dict[str, Any]], output_path: Path) -> None:
    # manifest를 파일이나 저장소에 기록한다.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]], output_path: Path) -> None:
    # print 요약 정보를 계산해 반환한다.
    total_samples = len(rows)
    tomato_samples = sum(row["is_tomato"] == "true" for row in rows)
    detection_target_samples = sum(row["is_detection_target"] == "true" for row in rows)
    negative_samples = sum(row["is_negative_sample"] == "true" for row in rows)
    excluded_samples = sum(row["use_for_detection"] != "true" for row in rows)

    print(f"Manifest CSV: {output_path}")
    print(f"Total samples: {total_samples}")
    print(f"Tomato samples: {tomato_samples}")
    print(f"Detection target samples: {detection_target_samples}")
    print(f"Negative samples: {negative_samples}")
    print(f"Excluded samples: {excluded_samples}")


def main() -> int:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    args = parse_args()
    dataset_root = Path(args.dataset_root).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not dataset_root.exists() or not dataset_root.is_dir():
        raise SystemExit(f"--dataset-root must point to an existing directory: {dataset_root}")

    rows = build_manifest_rows(dataset_root)
    write_manifest(rows, output_path)
    print_summary(rows, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
