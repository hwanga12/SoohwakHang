#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
ANNOTATION_FIELDS = ("crop", "disease", "risk", "area", "grow", "bbox", "part")
DESCRIPTION_FIELDS = ("image", "task")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit AI Hub tomato dataset JSON structure and image-label matching."
    )
    parser.add_argument(
        "--dataset-root",
        required=True,
        help="Root directory containing AI Hub JSON labels and images.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to save the audit summary JSON.",
    )
    parser.add_argument(
        "--focus-crop",
        default="2",
        help="Crop code to highlight in focused distributions. Use 'none' to disable.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Maximum number of sample issue paths to keep in the saved report.",
    )
    return parser.parse_args()


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def normalize_value(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def load_json(json_path: Path) -> dict[str, Any]:
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def extract_annotations(data: dict[str, Any]) -> tuple[list[dict[str, Any]], str, str, int]:
    if "annotation" in data:
        raw = data.get("annotation")
        key_name = "annotation"
    elif "annotations" in data:
        raw = data.get("annotations")
        key_name = "annotations"
    else:
        return [], "missing", "missing", 0

    if raw is None:
        return [], key_name, "none", 0
    if isinstance(raw, dict):
        return [raw], key_name, "dict", 0
    if isinstance(raw, list):
        valid_items = [item for item in raw if isinstance(item, dict)]
        invalid_items = len(raw) - len(valid_items)
        return valid_items, key_name, "list", invalid_items
    return [], key_name, type(raw).__name__, 0


def build_image_index(dataset_root: Path) -> tuple[list[Path], dict[str, list[Path]], dict[str, list[Path]]]:
    image_paths = [
        path
        for path in dataset_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]

    by_name: dict[str, list[Path]] = defaultdict(list)
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for image_path in image_paths:
        by_name[image_path.name].append(image_path)
        by_stem[image_path.stem].append(image_path)

    return image_paths, by_name, by_stem


def dedupe_paths(paths: list[Path]) -> list[Path]:
    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path not in seen:
            unique_paths.append(path)
            seen.add(path)
    return unique_paths


def choose_best_candidate(json_path: Path, candidates: list[Path]) -> tuple[Path | None, bool]:
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
    candidates: list[Path] = []

    if is_present(description_image):
        image_name = str(description_image)
        image_path = Path(image_name)
        direct_candidates = [
            json_path.parent / image_path,
            dataset_root / image_path,
            json_path.parent / image_path.name,
            dataset_root / image_path.name,
        ]
        for candidate in direct_candidates:
            if candidate.exists() and candidate.is_file() and candidate.suffix.lower() in IMAGE_SUFFIXES:
                candidates.append(candidate)

        candidates.extend(image_by_name.get(image_path.name, []))

    candidates.extend(image_by_stem.get(json_path.stem, []))
    return choose_best_candidate(json_path, candidates)


def counter_to_sorted_dict(counter: Counter[str]) -> dict[str, int]:
    items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return {key: value for key, value in items}


def relative_sample_paths(paths: list[Path], dataset_root: Path, limit: int) -> list[str]:
    samples: list[str] = []
    for path in paths[:limit]:
        try:
            samples.append(str(path.relative_to(dataset_root)))
        except ValueError:
            samples.append(str(path))
    return samples


def append_issue(store: list[Path], path: Path, limit: int) -> None:
    if len(store) < limit:
        store.append(path)


def format_counter_lines(title: str, counts: dict[str, int]) -> list[str]:
    lines = [title]
    if not counts:
        lines.append("  - none")
        return lines

    for key, value in counts.items():
        lines.append(f"  - {key}: {value}")
    return lines


def audit_dataset(
    dataset_root: Path,
    focus_crop: str | None,
    sample_limit: int,
    skip_json_paths: set[Path] | None = None,
) -> dict[str, Any]:
    image_paths, image_by_name, image_by_stem = build_image_index(dataset_root)
    skip_json_paths = skip_json_paths or set()
    json_paths = sorted(
        path for path in dataset_root.rglob("*.json") if path.resolve() not in skip_json_paths
    )

    annotation_key_usage: Counter[str] = Counter()
    annotation_container_usage: Counter[str] = Counter()
    annotation_field_presence: Counter[str] = Counter()
    description_field_presence: Counter[str] = Counter()
    distribution_counters = {
        "crop": Counter(),
        "disease": Counter(),
        "risk": Counter(),
        "area": Counter(),
        "grow": Counter(),
    }
    focused_distribution_counters = {
        "disease": Counter(),
        "risk": Counter(),
        "area": Counter(),
        "grow": Counter(),
    }

    malformed_json_paths: list[Path] = []
    missing_annotation_paths: list[Path] = []
    missing_image_paths: list[Path] = []
    ambiguous_match_paths: list[Path] = []
    invalid_annotation_item_paths: list[Path] = []
    images_with_labels: set[Path] = set()

    total_annotations = 0
    json_with_annotations = 0
    json_with_images = 0
    malformed_json_count = 0
    missing_annotation_count = 0
    missing_image_count = 0
    ambiguous_match_count = 0
    invalid_annotation_item_count = 0

    for json_path in json_paths:
        try:
            data = load_json(json_path)
        except (json.JSONDecodeError, UnicodeDecodeError):
            malformed_json_count += 1
            append_issue(malformed_json_paths, json_path, sample_limit)
            continue

        description = data.get("description") if isinstance(data.get("description"), dict) else {}
        for field_name in DESCRIPTION_FIELDS:
            if is_present(description.get(field_name)):
                description_field_presence[field_name] += 1

        annotations, key_name, container_name, invalid_items = extract_annotations(data)
        annotation_key_usage[key_name] += 1
        annotation_container_usage[container_name] += 1

        if invalid_items > 0:
            invalid_annotation_item_count += 1
            append_issue(invalid_annotation_item_paths, json_path, sample_limit)

        if not annotations:
            missing_annotation_count += 1
            append_issue(missing_annotation_paths, json_path, sample_limit)
            continue

        json_with_annotations += 1
        image_path, is_ambiguous = resolve_image_path(
            json_path=json_path,
            dataset_root=dataset_root,
            description_image=description.get("image"),
            image_by_name=image_by_name,
            image_by_stem=image_by_stem,
        )

        if image_path is None:
            missing_image_count += 1
            append_issue(missing_image_paths, json_path, sample_limit)
        else:
            json_with_images += 1
            images_with_labels.add(image_path)
            if is_ambiguous:
                ambiguous_match_count += 1
                append_issue(ambiguous_match_paths, json_path, sample_limit)

        for annotation in annotations:
            total_annotations += 1

            for field_name in ANNOTATION_FIELDS:
                if is_present(annotation.get(field_name)):
                    annotation_field_presence[field_name] += 1

            crop_value = normalize_value(annotation.get("crop"))
            distribution_counters["crop"][crop_value] += 1

            for field_name in ("disease", "risk", "area", "grow"):
                distribution_counters[field_name][normalize_value(annotation.get(field_name))] += 1

            if focus_crop is not None and crop_value == focus_crop:
                for field_name in ("disease", "risk", "area", "grow"):
                    focused_distribution_counters[field_name][
                        normalize_value(annotation.get(field_name))
                    ] += 1

    images_without_labels = sorted(set(image_paths) - images_with_labels)

    return {
        "dataset_root": str(dataset_root),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "focus_crop": focus_crop,
        "totals": {
            "json_files": len(json_paths),
            "image_files": len(image_paths),
            "json_with_annotations": json_with_annotations,
            "json_with_matched_images": json_with_images,
            "total_annotations": total_annotations,
            "malformed_json_files": malformed_json_count,
            "json_missing_annotations": missing_annotation_count,
            "json_missing_images": missing_image_count,
            "ambiguous_image_matches": ambiguous_match_count,
            "invalid_annotation_item_files": invalid_annotation_item_count,
            "images_without_labels": len(images_without_labels),
        },
        "schema": {
            "annotation_key_usage": counter_to_sorted_dict(annotation_key_usage),
            "annotation_container_usage": counter_to_sorted_dict(annotation_container_usage),
            "annotation_field_presence": counter_to_sorted_dict(annotation_field_presence),
            "description_field_presence": counter_to_sorted_dict(description_field_presence),
        },
        "distributions": {
            "all_annotations": {
                field_name: counter_to_sorted_dict(counter)
                for field_name, counter in distribution_counters.items()
            },
            "focus_crop_annotations": (
                {
                    field_name: counter_to_sorted_dict(counter)
                    for field_name, counter in focused_distribution_counters.items()
                }
                if focus_crop is not None
                else {}
            ),
        },
        "image_label_matching": {
            "matched_images": len(images_with_labels),
            "images_without_labels_samples": relative_sample_paths(
                images_without_labels, dataset_root, sample_limit
            ),
            "missing_image_for_label_samples": relative_sample_paths(
                missing_image_paths, dataset_root, sample_limit
            ),
            "ambiguous_image_match_samples": relative_sample_paths(
                ambiguous_match_paths, dataset_root, sample_limit
            ),
        },
        "issues": {
            "malformed_json_samples": relative_sample_paths(
                malformed_json_paths, dataset_root, sample_limit
            ),
            "missing_annotation_samples": relative_sample_paths(
                missing_annotation_paths, dataset_root, sample_limit
            ),
            "invalid_annotation_item_samples": relative_sample_paths(
                invalid_annotation_item_paths, dataset_root, sample_limit
            ),
        },
    }


def render_summary(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    schema = summary["schema"]
    distributions = summary["distributions"]
    focus_crop = summary["focus_crop"]

    lines = [
        "=== Dataset Audit Summary ===",
        f"dataset_root: {summary['dataset_root']}",
        f"generated_at_utc: {summary['generated_at_utc']}",
        f"focus_crop: {focus_crop if focus_crop is not None else 'disabled'}",
        "",
        "Totals",
        f"  - json_files: {totals['json_files']}",
        f"  - image_files: {totals['image_files']}",
        f"  - json_with_annotations: {totals['json_with_annotations']}",
        f"  - json_with_matched_images: {totals['json_with_matched_images']}",
        f"  - total_annotations: {totals['total_annotations']}",
        f"  - malformed_json_files: {totals['malformed_json_files']}",
        f"  - json_missing_annotations: {totals['json_missing_annotations']}",
        f"  - json_missing_images: {totals['json_missing_images']}",
        f"  - ambiguous_image_matches: {totals['ambiguous_image_matches']}",
        f"  - invalid_annotation_item_files: {totals['invalid_annotation_item_files']}",
        f"  - images_without_labels: {totals['images_without_labels']}",
        "",
        "Schema checks",
    ]
    lines.extend(format_counter_lines("  annotation key usage", schema["annotation_key_usage"]))
    lines.extend(
        format_counter_lines(
            "  annotation container usage", schema["annotation_container_usage"]
        )
    )
    lines.extend(
        format_counter_lines("  annotation field presence", schema["annotation_field_presence"])
    )
    lines.extend(
        format_counter_lines("  description field presence", schema["description_field_presence"])
    )
    lines.append("")
    lines.append("Distributions - all annotations")
    for field_name in ("crop", "disease", "risk", "area", "grow"):
        lines.extend(
            format_counter_lines(f"  {field_name}", distributions["all_annotations"][field_name])
        )

    if focus_crop is not None:
        lines.append("")
        lines.append(f"Distributions - focus crop ({focus_crop})")
        focus_counts = distributions["focus_crop_annotations"]
        for field_name in ("disease", "risk", "area", "grow"):
            lines.extend(format_counter_lines(f"  {field_name}", focus_counts[field_name]))

    lines.append("")
    lines.append("Image-label matching")
    lines.append(
        f"  - matched_images: {summary['image_label_matching']['matched_images']}"
    )
    lines.extend(
        format_counter_lines(
            "  images without labels",
            {sample: 1 for sample in summary["image_label_matching"]["images_without_labels_samples"]},
        )
    )
    lines.extend(
        format_counter_lines(
            "  missing image for label",
            {sample: 1 for sample in summary["image_label_matching"]["missing_image_for_label_samples"]},
        )
    )
    lines.extend(
        format_counter_lines(
            "  ambiguous image match",
            {sample: 1 for sample in summary["image_label_matching"]["ambiguous_image_match_samples"]},
        )
    )

    lines.append("")
    lines.append("Issue samples")
    lines.extend(
        format_counter_lines(
            "  malformed json",
            {sample: 1 for sample in summary["issues"]["malformed_json_samples"]},
        )
    )
    lines.extend(
        format_counter_lines(
            "  missing annotation",
            {sample: 1 for sample in summary["issues"]["missing_annotation_samples"]},
        )
    )
    lines.extend(
        format_counter_lines(
            "  invalid annotation item",
            {sample: 1 for sample in summary["issues"]["invalid_annotation_item_samples"]},
        )
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    dataset_root = Path(args.dataset_root).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    focus_crop = None if str(args.focus_crop).lower() == "none" else normalize_value(args.focus_crop)

    if not dataset_root.exists():
        raise SystemExit(f"Dataset root does not exist: {dataset_root}")

    if not dataset_root.is_dir():
        raise SystemExit(f"Dataset root is not a directory: {dataset_root}")

    skip_json_paths: set[Path] = set()
    try:
        output_path.relative_to(dataset_root)
        skip_json_paths.add(output_path)
    except ValueError:
        pass

    summary = audit_dataset(
        dataset_root=dataset_root,
        focus_crop=focus_crop,
        sample_limit=args.sample_limit,
        skip_json_paths=skip_json_paths,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    print(render_summary(summary))
    print("")
    print(f"Saved summary JSON to: {output_path}")


if __name__ == "__main__":
    main()
