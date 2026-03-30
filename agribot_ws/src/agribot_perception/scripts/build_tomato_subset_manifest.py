#!/usr/bin/env python3
"""Build a subset-aware tomato detection manifest for train + validation.

This builder keeps the original validation-only workflow intact by adding a
dedicated script for the baseline subset stage:

- train positive rows come from the materialized positive subset
- train normal rows come from the source-only normal subset
- validation rows come from the extracted validation root

The output manifest stays compatible with ``json_to_yolo_det.py`` while adding
``source_split`` and ``source_origin`` metadata so later stages do not need to
reconstruct where each row came from.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from build_tomato_manifest import (  # noqa: E402
    IMAGE_SUFFIXES,
    MANIFEST_FIELDNAMES,
    bool_to_text,
    collect_unique_values,
    count_top_level_bbox_items,
    determine_skip_reason,
    extract_annotations,
    join_entry_names,
    join_values,
    load_json,
)

SUBSET_MANIFEST_FIELDNAMES = [
    *MANIFEST_FIELDNAMES,
    "source_split",
    "source_origin",
]


@dataclass(frozen=True, slots=True)
class ImageIndex:
    by_name: dict[str, list[Path]]
    by_name_ci: dict[str, list[Path]]
    by_stem: dict[str, list[Path]]
    by_stem_ci: dict[str, list[Path]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a combined tomato detection manifest from prepared train subsets and validation data."
    )
    parser.add_argument(
        "--train-positive-root",
        required=True,
        help="Materialized train positive subset root.",
    )
    parser.add_argument(
        "--train-normal-root",
        required=True,
        help="Source-only train normal subset root.",
    )
    parser.add_argument(
        "--val-extracted-root",
        required=True,
        help="Validation extracted root containing source/ and label/ trees.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Combined manifest CSV path. Written as UTF-8 with BOM.",
    )
    return parser.parse_args()


def to_prefixed_relative(path: Path, root: Path, prefix: str) -> str:
    return str(Path(prefix) / path.relative_to(root))


def build_image_index(source_root: Path) -> ImageIndex:
    by_name: dict[str, list[Path]] = defaultdict(list)
    by_name_ci: dict[str, list[Path]] = defaultdict(list)
    by_stem: dict[str, list[Path]] = defaultdict(list)
    by_stem_ci: dict[str, list[Path]] = defaultdict(list)

    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        by_name[path.name].append(path)
        by_name_ci[path.name.casefold()].append(path)
        by_stem[path.stem].append(path)
        by_stem_ci[path.stem.casefold()].append(path)

    return ImageIndex(
        by_name=dict(by_name),
        by_name_ci=dict(by_name_ci),
        by_stem=dict(by_stem),
        by_stem_ci=dict(by_stem_ci),
    )


def dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique_paths.append(path)
    return unique_paths


def filter_candidates_by_category(candidates: list[Path], category_name: str) -> list[Path]:
    if not category_name:
        return candidates
    category_matches = [path for path in candidates if category_name in path.parts]
    return category_matches or candidates


def choose_best_candidate(
    candidates: list[Path],
    *,
    label_category: str,
    declared_name: str,
    json_stem: str,
) -> tuple[Path | None, bool]:
    unique_candidates = filter_candidates_by_category(
        dedupe_paths(candidates),
        label_category,
    )
    if not unique_candidates:
        return None, False
    if len(unique_candidates) == 1:
        return unique_candidates[0], False

    declared_path = Path(declared_name).name if declared_name else ""
    declared_stem = Path(declared_path).stem if declared_path else ""

    checks = []
    if declared_path:
        checks.extend(
            [
                lambda path: path.name == declared_path,
                lambda path: path.name.casefold() == declared_path.casefold(),
                lambda path: path.stem == declared_stem,
                lambda path: path.stem.casefold() == declared_stem.casefold(),
            ]
        )
    checks.extend(
        [
            lambda path: path.stem == json_stem,
            lambda path: path.stem.casefold() == json_stem.casefold(),
        ]
    )

    narrowed_candidates = unique_candidates
    for predicate in checks:
        matches = [path for path in narrowed_candidates if predicate(path)]
        if not matches:
            continue
        if len(matches) == 1:
            return matches[0], False
        narrowed_candidates = matches

    sorted_candidates = sorted(
        narrowed_candidates,
        key=lambda path: (len(path.parts), str(path).casefold()),
    )
    return sorted_candidates[0], True


def resolve_image_path(
    *,
    description_image: Any,
    json_path: Path,
    label_category: str,
    image_index: ImageIndex,
) -> tuple[Path | None, bool]:
    declared_name = str(description_image).strip() if description_image is not None else ""
    json_stem = json_path.stem
    candidates: list[Path] = []

    if declared_name:
        declared_path = Path(declared_name)
        candidates.extend(image_index.by_name.get(declared_path.name, []))
        candidates.extend(image_index.by_name_ci.get(declared_path.name.casefold(), []))
        candidates.extend(image_index.by_stem.get(declared_path.stem, []))
        candidates.extend(image_index.by_stem_ci.get(declared_path.stem.casefold(), []))

    candidates.extend(image_index.by_stem.get(json_stem, []))
    candidates.extend(image_index.by_stem_ci.get(json_stem.casefold(), []))

    return choose_best_candidate(
        candidates,
        label_category=label_category,
        declared_name=declared_name,
        json_stem=json_stem,
    )


def build_base_row(
    *,
    json_path: Path | None,
    json_rel_path: str,
    source_split: str,
    source_origin: str,
) -> dict[str, Any]:
    return {
        "image_path": "",
        "image_rel_path": "",
        "json_path": str(json_path.resolve()) if json_path else "",
        "json_rel_path": json_rel_path,
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
        "source_split": source_split,
        "source_origin": source_origin,
    }


def build_label_row(
    *,
    json_path: Path,
    label_root: Path,
    source_root: Path,
    image_index: ImageIndex,
    source_split: str,
    source_origin: str,
) -> dict[str, Any]:
    row = build_base_row(
        json_path=json_path,
        json_rel_path=to_prefixed_relative(json_path, label_root, "label"),
        source_split=source_split,
        source_origin=source_origin,
    )

    try:
        data = load_json(json_path)
    except (OSError, UnicodeDecodeError, ValueError):
        row["skip_reason"] = "malformed_json"
        return row

    annotations, _ = extract_annotations(data)
    description = data.get("description") if isinstance(data.get("description"), dict) else {}
    crop_codes = collect_unique_values(annotations, "crop")
    disease_codes = collect_unique_values(annotations, "disease")
    risk_values = collect_unique_values(annotations, "risk")
    top_level_bbox_count = count_top_level_bbox_items(annotations)
    label_category = json_path.parent.name

    image_path, image_match_ambiguous = resolve_image_path(
        description_image=description.get("image"),
        json_path=json_path,
        label_category=label_category,
        image_index=image_index,
    )

    single_crop_code = crop_codes[0] if len(crop_codes) == 1 else ""
    single_disease_code = disease_codes[0] if len(disease_codes) == 1 else ""
    is_tomato = bool(single_crop_code) and is_tomato_crop(single_crop_code)
    is_detection_target = bool(single_disease_code) and is_detection_target_disease(
        single_disease_code
    )
    is_negative_sample = bool(single_disease_code) and is_negative_sample_disease(
        single_disease_code
    )
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
    effective_top_level_bbox_count = top_level_bbox_count
    if is_negative_sample and skip_reason == "negative_sample_has_top_level_bbox":
        skip_reason = ""
        effective_top_level_bbox_count = 0
    elif is_negative_sample:
        effective_top_level_bbox_count = 0

    row.update(
        {
            "image_path": str(image_path.resolve()) if image_path else "",
            "image_rel_path": to_prefixed_relative(image_path, source_root, "source")
            if image_path
            else "",
            "crop_code": join_values(crop_codes),
            "crop_name": join_entry_names(crop_codes, get_crop_entry, "name_en"),
            "disease_code": join_values(disease_codes),
            "disease_name_en": join_entry_names(
                disease_codes,
                get_disease_entry,
                "name_en",
            ),
            "disease_name_ko": join_entry_names(
                disease_codes,
                get_disease_entry,
                "name_ko",
            ),
            "risk": join_values(risk_values),
            "top_level_bbox_count": effective_top_level_bbox_count,
            "is_tomato": bool_to_text(is_tomato),
            "is_detection_target": bool_to_text(is_detection_target),
            "is_negative_sample": bool_to_text(is_negative_sample),
            "use_for_detection": bool_to_text(skip_reason == ""),
            "skip_reason": skip_reason,
        }
    )
    return row


def build_positive_rows(train_positive_root: Path) -> list[dict[str, Any]]:
    source_root = train_positive_root / "source"
    label_root = train_positive_root / "label"
    image_index = build_image_index(source_root)
    rows: list[dict[str, Any]] = []

    for json_path in sorted(label_root.rglob("*.json")):
        rows.append(
            build_label_row(
                json_path=json_path,
                label_root=label_root,
                source_root=source_root,
                image_index=image_index,
                source_split="train",
                source_origin="train_positive_subset",
            )
        )

    return rows


def build_normal_rows(train_normal_root: Path) -> list[dict[str, Any]]:
    source_root = train_normal_root / "source"
    crop_entry = get_crop_entry("2")
    disease_entry = get_disease_entry("00")
    rows: list[dict[str, Any]] = []

    for image_path in sorted(source_root.rglob("*")):
        if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        row = build_base_row(
            json_path=None,
            json_rel_path="",
            source_split="train",
            source_origin="train_normal_subset",
        )
        row.update(
            {
                "image_path": str(image_path.resolve()),
                "image_rel_path": to_prefixed_relative(image_path, source_root, "source"),
                "crop_code": crop_entry.code if crop_entry else "2",
                "crop_name": crop_entry.name_en if crop_entry else "tomato",
                "disease_code": disease_entry.code if disease_entry else "00",
                "disease_name_en": disease_entry.name_en if disease_entry else "normal",
                "disease_name_ko": disease_entry.name_ko if disease_entry else "정상",
                "risk": "",
                "top_level_bbox_count": 0,
                "is_tomato": "true",
                "is_detection_target": "false",
                "is_negative_sample": "true",
                "use_for_detection": "true",
                "skip_reason": "",
            }
        )
        rows.append(row)

    return rows


def build_validation_rows(val_extracted_root: Path) -> list[dict[str, Any]]:
    source_root = val_extracted_root / "source"
    label_root = val_extracted_root / "label"
    image_index = build_image_index(source_root)
    rows: list[dict[str, Any]] = []

    for json_path in sorted(label_root.rglob("*.json")):
        rows.append(
            build_label_row(
                json_path=json_path,
                label_root=label_root,
                source_root=source_root,
                image_index=image_index,
                source_split="val",
                source_origin="val_extracted",
            )
        )

    return rows


def write_manifest(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUBSET_MANIFEST_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]], output_path: Path) -> None:
    total_rows = len(rows)
    detection_rows = sum(row["use_for_detection"] == "true" for row in rows)
    negative_rows = sum(row["is_negative_sample"] == "true" for row in rows)
    detection_by_split = Counter(
        row["source_split"] for row in rows if row["use_for_detection"] == "true"
    )
    detection_by_origin = Counter(
        row["source_origin"] for row in rows if row["use_for_detection"] == "true"
    )
    detection_by_disease = Counter(
        row["disease_code"] for row in rows if row["use_for_detection"] == "true"
    )

    print(f"Manifest CSV: {output_path}")
    print(f"Total rows: {total_rows}")
    print(f"Rows for detection: {detection_rows}")
    print(f"Negative rows: {negative_rows}")

    for split_name in ("train", "val", "test"):
        if detection_by_split.get(split_name, 0) > 0:
            print(f"Detection split {split_name}: {detection_by_split[split_name]}")

    for origin_name in ("train_positive_subset", "train_normal_subset", "val_extracted"):
        if detection_by_origin.get(origin_name, 0) > 0:
            print(f"Detection origin {origin_name}: {detection_by_origin[origin_name]}")

    for disease_code in sorted(detection_by_disease):
        print(f"Disease {disease_code}: {detection_by_disease[disease_code]}")


def validate_root(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise SystemExit(f"{label} must point to an existing directory: {resolved}")
    return resolved


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    train_positive_root = validate_root(
        Path(args.train_positive_root),
        label="--train-positive-root",
    )
    train_normal_root = validate_root(
        Path(args.train_normal_root),
        label="--train-normal-root",
    )
    val_extracted_root = validate_root(
        Path(args.val_extracted_root),
        label="--val-extracted-root",
    )
    output_path = Path(args.output).expanduser().resolve()

    rows = []
    rows.extend(build_positive_rows(train_positive_root))
    rows.extend(build_normal_rows(train_normal_root))
    rows.extend(build_validation_rows(val_extracted_root))

    write_manifest(rows, output_path)
    print_summary(rows, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
