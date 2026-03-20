#!/usr/bin/env python3
"""Plan a tomato detection baseline subset from AI Hub 525 label JSON files.

This planner reads raw label JSON files under a user-provided root and emits a
CSV that later extractor steps can consume directly.

Selection policy:
- target positives: ``a5``, ``a6``, ``b2``, ``b3``
- target negatives: ``00`` only
- positive classes are selected by a documented stable sort order
- normal samples are sampled with a seeded RNG for reproducibility

The stable order for non-normal classes is:
``(source_split.lower(), json_rel_path.lower(), image_filename.lower(), json_filename.lower())``
Rows beyond a class quota are kept in the CSV as ``is_selected=false`` with
``selected_reason=skipped_over_quota`` so the planning result stays auditable.
If a requested class has fewer eligible candidates than its quota, the planner
adds a ``shortfall_summary`` row with
``selected_reason=skipped_insufficient_candidate``.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from agribot_perception.utils.codebook import (  # noqa: E402
    NORMAL_DISEASE_CODE,
    get_crop_entry,
    get_disease_entry,
    is_tomato_crop,
    normalize_code,
)

TARGET_DISEASE_ORDER = ("a5", "a6", "b2", "b3", NORMAL_DISEASE_CODE)
DEFAULT_QUOTAS = {
    "a5": 1000,
    "a6": 1000,
    "b2": 1000,
    "b3": 1000,
    NORMAL_DISEASE_CODE: 2500,
}
CSV_FIELDNAMES = [
    "row_type",
    "is_selected",
    "selected_reason",
    "crop_code",
    "crop_name",
    "disease_code",
    "disease_name_en",
    "risk",
    "top_level_bbox_count",
    "source_split",
    "image_filename",
    "json_filename",
    "image_declared_path",
    "json_rel_path",
    "json_path",
    "requested_count",
    "available_count",
    "selected_count",
    "shortfall_count",
]
KNOWN_SPLIT_NAMES = {
    "train",
    "training",
    "val",
    "valid",
    "validation",
    "dev",
    "test",
    "testing",
}


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    """One eligible target candidate parsed from a raw JSON label file."""

    crop_code: str
    crop_name: str
    disease_code: str
    disease_name_en: str
    risk: str
    top_level_bbox_count: int
    source_split: str
    image_filename: str
    json_filename: str
    image_declared_path: str
    json_rel_path: str
    json_path: Path

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.source_split.lower(),
            self.json_rel_path.lower(),
            self.image_filename.lower(),
            self.json_filename.lower(),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan a tomato train subset CSV for the initial detection baseline."
    )
    parser.add_argument(
        "--label-root",
        required=True,
        help="Root directory to scan for AI Hub label JSON files.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="CSV output path. Written as UTF-8 with BOM (utf-8-sig).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed used only for normal (00) sampling.",
    )
    parser.add_argument("--quota-a5", type=int, default=DEFAULT_QUOTAS["a5"])
    parser.add_argument("--quota-a6", type=int, default=DEFAULT_QUOTAS["a6"])
    parser.add_argument("--quota-b2", type=int, default=DEFAULT_QUOTAS["b2"])
    parser.add_argument("--quota-b3", type=int, default=DEFAULT_QUOTAS["b3"])
    parser.add_argument("--quota-00", type=int, default=DEFAULT_QUOTAS[NORMAL_DISEASE_CODE])
    return parser.parse_args()


def load_json(json_path: Path) -> dict[str, Any]:
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def collect_unique_values(annotations: list[dict[str, Any]], field_name: str) -> list[str]:
    values = {
        normalize_code(annotation.get(field_name))
        for annotation in annotations
        if normalize_code(annotation.get(field_name))
    }
    return sorted(values)


def count_bbox_items(bbox_value: Any) -> int:
    if bbox_value is None:
        return 0
    if isinstance(bbox_value, dict):
        return 1
    if isinstance(bbox_value, list):
        return sum(1 for item in bbox_value if isinstance(item, dict))
    return 0


def count_top_level_bbox_items(annotations: list[dict[str, Any]]) -> int:
    return sum(count_bbox_items(annotation.get("bbox")) for annotation in annotations)


def join_values(values: list[str]) -> str:
    return "|".join(values)


def to_relative_string(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def infer_source_split(path: Path) -> str:
    for part in path.parts:
        if part.lower() in KNOWN_SPLIT_NAMES:
            return part
    return ""


def build_quotas(args: argparse.Namespace) -> dict[str, int]:
    quotas = {
        "a5": args.quota_a5,
        "a6": args.quota_a6,
        "b2": args.quota_b2,
        "b3": args.quota_b3,
        NORMAL_DISEASE_CODE: args.quota_00,
    }
    for disease_code, quota in quotas.items():
        if quota < 0:
            raise SystemExit(f"Quota must be >= 0 for {disease_code}, got {quota}.")
    return quotas


def extract_candidate_record(json_path: Path, label_root: Path) -> CandidateRecord | None:
    try:
        data = load_json(json_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    annotations = extract_annotations(data)
    if not annotations:
        return None

    crop_codes = collect_unique_values(annotations, "crop")
    disease_codes = collect_unique_values(annotations, "disease")
    risk_values = collect_unique_values(annotations, "risk")
    if len(crop_codes) != 1 or len(disease_codes) != 1:
        return None

    crop_code = crop_codes[0]
    disease_code = disease_codes[0]
    if not is_tomato_crop(crop_code):
        return None
    if disease_code not in TARGET_DISEASE_ORDER:
        return None

    top_level_bbox_count = count_top_level_bbox_items(annotations)
    if disease_code == NORMAL_DISEASE_CODE:
        if top_level_bbox_count > 0:
            return None
    elif top_level_bbox_count <= 0:
        return None

    description = data.get("description") if isinstance(data.get("description"), dict) else {}
    image_declared_path = str(description.get("image", "")).strip()
    image_filename = Path(image_declared_path).name if image_declared_path else ""

    crop_entry = get_crop_entry(crop_code)
    disease_entry = get_disease_entry(disease_code)

    return CandidateRecord(
        crop_code=crop_code,
        crop_name=crop_entry.name_en if crop_entry else "",
        disease_code=disease_code,
        disease_name_en=disease_entry.name_en if disease_entry else "",
        risk=join_values(risk_values),
        top_level_bbox_count=top_level_bbox_count,
        source_split=infer_source_split(json_path.resolve()),
        image_filename=image_filename,
        json_filename=json_path.name,
        image_declared_path=image_declared_path,
        json_rel_path=to_relative_string(json_path.resolve(), label_root.resolve()),
        json_path=json_path.resolve(),
    )


def gather_candidates(label_root: Path) -> tuple[dict[str, list[CandidateRecord]], Counter[str]]:
    candidates_by_disease: dict[str, list[CandidateRecord]] = defaultdict(list)
    stats: Counter[str] = Counter()

    for json_path in sorted(label_root.rglob("*.json")):
        stats["json_files_scanned"] += 1
        candidate = extract_candidate_record(json_path, label_root)
        if candidate is None:
            stats["json_files_skipped"] += 1
            continue

        candidates_by_disease[candidate.disease_code].append(candidate)
        stats["eligible_candidates"] += 1

    return candidates_by_disease, stats


def select_row_indices(
    disease_code: str,
    candidates: list[CandidateRecord],
    quota: int,
    seed: int,
) -> set[int]:
    selected_count = min(quota, len(candidates))
    if selected_count <= 0:
        return set()

    if disease_code != NORMAL_DISEASE_CODE:
        return set(range(selected_count))

    rng = random.Random(seed)
    sampled_indices = rng.sample(range(len(candidates)), k=selected_count)
    return set(sampled_indices)


def bool_to_text(value: bool) -> str:
    return "true" if value else "false"


def build_candidate_row(
    record: CandidateRecord,
    *,
    is_selected: bool,
    selected_reason: str,
    requested_count: int,
    available_count: int,
    selected_count: int,
    shortfall_count: int,
) -> dict[str, str]:
    return {
        "row_type": "candidate",
        "is_selected": bool_to_text(is_selected),
        "selected_reason": selected_reason,
        "crop_code": record.crop_code,
        "crop_name": record.crop_name,
        "disease_code": record.disease_code,
        "disease_name_en": record.disease_name_en,
        "risk": record.risk,
        "top_level_bbox_count": str(record.top_level_bbox_count),
        "source_split": record.source_split,
        "image_filename": record.image_filename,
        "json_filename": record.json_filename,
        "image_declared_path": record.image_declared_path,
        "json_rel_path": record.json_rel_path,
        "json_path": str(record.json_path),
        "requested_count": str(requested_count),
        "available_count": str(available_count),
        "selected_count": str(selected_count),
        "shortfall_count": str(shortfall_count),
    }


def build_shortfall_summary_row(
    disease_code: str,
    *,
    requested_count: int,
    available_count: int,
    selected_count: int,
    shortfall_count: int,
) -> dict[str, str]:
    crop_entry = get_crop_entry("2")
    disease_entry = get_disease_entry(disease_code)
    return {
        "row_type": "shortfall_summary",
        "is_selected": "false",
        "selected_reason": "skipped_insufficient_candidate",
        "crop_code": "2",
        "crop_name": crop_entry.name_en if crop_entry else "",
        "disease_code": disease_code,
        "disease_name_en": disease_entry.name_en if disease_entry else "",
        "risk": "",
        "top_level_bbox_count": "",
        "source_split": "",
        "image_filename": "",
        "json_filename": "",
        "image_declared_path": "",
        "json_rel_path": "",
        "json_path": "",
        "requested_count": str(requested_count),
        "available_count": str(available_count),
        "selected_count": str(selected_count),
        "shortfall_count": str(shortfall_count),
    }


def build_plan_rows(
    candidates_by_disease: dict[str, list[CandidateRecord]],
    quotas: dict[str, int],
    seed: int,
) -> tuple[list[dict[str, str]], dict[str, dict[str, int]]]:
    rows: list[dict[str, str]] = []
    summary: dict[str, dict[str, int]] = {}

    for disease_code in TARGET_DISEASE_ORDER:
        candidates = sorted(candidates_by_disease.get(disease_code, []), key=lambda item: item.sort_key)
        requested_count = quotas[disease_code]
        available_count = len(candidates)
        selected_indices = select_row_indices(disease_code, candidates, requested_count, seed)
        selected_count = len(selected_indices)
        shortfall_count = max(0, requested_count - selected_count)

        summary[disease_code] = {
            "requested_count": requested_count,
            "available_count": available_count,
            "selected_count": selected_count,
            "shortfall_count": shortfall_count,
        }

        for index, record in enumerate(candidates):
            is_selected = index in selected_indices
            if is_selected:
                selected_reason = (
                    "target_negative"
                    if disease_code == NORMAL_DISEASE_CODE
                    else "target_positive"
                )
            else:
                selected_reason = "skipped_over_quota"

            rows.append(
                build_candidate_row(
                    record,
                    is_selected=is_selected,
                    selected_reason=selected_reason,
                    requested_count=requested_count,
                    available_count=available_count,
                    selected_count=selected_count,
                    shortfall_count=shortfall_count,
                )
            )

        if shortfall_count > 0:
            rows.append(
                build_shortfall_summary_row(
                    disease_code,
                    requested_count=requested_count,
                    available_count=available_count,
                    selected_count=selected_count,
                    shortfall_count=shortfall_count,
                )
            )

    return rows, summary


def write_plan_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(
    output_path: Path,
    summary: dict[str, dict[str, int]],
    stats: Counter[str],
) -> None:
    print(f"Subset plan CSV: {output_path}")
    print(f"JSON files scanned: {stats.get('json_files_scanned', 0)}")
    print(f"Eligible candidates: {stats.get('eligible_candidates', 0)}")

    total_selected = sum(item["selected_count"] for item in summary.values())
    print(f"Selected rows: {total_selected}")

    shortage_codes = [
        disease_code
        for disease_code in TARGET_DISEASE_ORDER
        if summary[disease_code]["shortfall_count"] > 0
    ]

    for disease_code in TARGET_DISEASE_ORDER:
        item = summary[disease_code]
        print(
            f"{disease_code}: requested={item['requested_count']} "
            f"available={item['available_count']} selected={item['selected_count']} "
            f"shortfall={item['shortfall_count']}"
        )

    if shortage_codes:
        joined_codes = ", ".join(shortage_codes)
        print(f"Shortfall classes: {joined_codes}")
    else:
        print("Shortfall classes: none")


def main() -> int:
    args = parse_args()
    label_root = Path(args.label_root).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not label_root.exists() or not label_root.is_dir():
        raise SystemExit(f"--label-root must point to an existing directory: {label_root}")

    quotas = build_quotas(args)
    candidates_by_disease, stats = gather_candidates(label_root)
    rows, summary = build_plan_rows(candidates_by_disease, quotas, args.seed)
    write_plan_csv(rows, output_path)
    print_summary(output_path, summary, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
