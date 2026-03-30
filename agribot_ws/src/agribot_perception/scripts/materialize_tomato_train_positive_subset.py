#!/usr/bin/env python3
"""Materialize the selected tomato train positive subset from planner CSV + source zips.

Images are resolved from train source zip files. Because zip members are not
filesystem entries, source images are always copied out of the archive into the
output tree. ``--link-mode`` therefore applies to label JSON materialization,
with a safe fallback to copy when hardlinking is not possible across devices.
"""

from __future__ import annotations

import argparse
import csv
import errno
import json
import logging
import os
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile

LOGGER = logging.getLogger("materialize_tomato_train_positive_subset")
POSITIVE_DISEASE_CODES = {"a5", "a6", "b2", "b3"}
PLAN_REQUIRED_COLUMNS = {
    "row_type",
    "is_selected",
    "disease_code",
    "source_split",
    "image_filename",
    "json_filename",
    "json_rel_path",
    "json_path",
}
MISSING_FIELDNAMES = [
    "issue_type",
    "disease_code",
    "source_split",
    "image_filename",
    "json_filename",
    "json_rel_path",
    "detail",
]


@dataclass(frozen=True, slots=True)
class PlannedPositiveRecord:
    """One selected positive row loaded from the planner CSV."""

    line_number: int
    disease_code: str
    source_split: str
    image_filename: str
    json_filename: str
    json_rel_path: str
    json_path: Path

    @property
    def label_category(self) -> str:
        parts = Path(self.json_rel_path).parts
        return parts[0] if parts else ""


@dataclass(frozen=True, slots=True)
class ZipMemberReference:
    """A zip member candidate indexed by basename."""

    zip_path: Path
    member_name: str
    file_size: int

    @property
    def member_parts(self) -> tuple[str, ...]:
        return Path(self.member_name).parts

    @property
    def basename(self) -> str:
        return Path(self.member_name).name

    @property
    def basename_casefold(self) -> str:
        return self.basename.casefold()

    @property
    def stem_casefold(self) -> str:
        return Path(self.member_name).stem.casefold()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize selected tomato train positive samples from planner CSV and source zips."
    )
    parser.add_argument("--plan-csv", required=True)
    parser.add_argument("--train-source-root", required=True)
    parser.add_argument("--train-label-root", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument(
        "--link-mode",
        choices=("hardlink", "symlink", "copy"),
        default="hardlink",
        help="Materialization mode for label JSON files. Zip images are always copied.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any missing/ambiguous file or count mismatch is found.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and validate without writing the output subset.",
    )
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def parse_bool_text(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def sort_counter(counter: Counter[str]) -> dict[str, int]:
    return {
        key: value
        for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    }


def image_extension(image_filename: str) -> str:
    suffix = Path(image_filename).suffix
    return suffix if suffix else "<none>"


def load_selected_positive_records(plan_csv_path: Path) -> list[PlannedPositiveRecord]:
    with plan_csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing_columns = sorted(PLAN_REQUIRED_COLUMNS - headers)
        if missing_columns:
            raise SystemExit(
                "Planner CSV is missing required columns: " + ", ".join(missing_columns)
            )

        records: list[PlannedPositiveRecord] = []
        for line_number, row in enumerate(reader, start=2):
            if row.get("row_type") != "candidate":
                continue
            if not parse_bool_text(row.get("is_selected", "")):
                continue

            disease_code = str(row.get("disease_code", "")).strip()
            if disease_code not in POSITIVE_DISEASE_CODES:
                continue

            image_filename = str(row.get("image_filename", "")).strip()
            json_filename = str(row.get("json_filename", "")).strip()
            json_rel_path = str(row.get("json_rel_path", "")).strip()
            json_path_text = str(row.get("json_path", "")).strip()
            if not image_filename or not json_filename or not json_rel_path:
                raise SystemExit(
                    f"Planner CSV row {line_number} is missing required image/json metadata."
                )

            records.append(
                PlannedPositiveRecord(
                    line_number=line_number,
                    disease_code=disease_code,
                    source_split=str(row.get("source_split", "")).strip(),
                    image_filename=image_filename,
                    json_filename=json_filename,
                    json_rel_path=json_rel_path,
                    json_path=Path(json_path_text).expanduser() if json_path_text else Path(),
                )
            )

    return records


def index_source_zip_members(
    train_source_root: Path,
) -> tuple[
    dict[Path, ZipFile],
    dict[str, list[ZipMemberReference]],
    dict[str, list[ZipMemberReference]],
    dict[str, list[ZipMemberReference]],
    int,
]:
    zip_paths = sorted(train_source_root.rglob("*.zip"))
    if not zip_paths:
        raise SystemExit(f"No zip files found under --train-source-root: {train_source_root}")

    zip_handles: dict[Path, ZipFile] = {}
    filename_index: dict[str, list[ZipMemberReference]] = defaultdict(list)
    filename_casefold_index: dict[str, list[ZipMemberReference]] = defaultdict(list)
    stem_casefold_index: dict[str, list[ZipMemberReference]] = defaultdict(list)
    member_count = 0

    for zip_path in zip_paths:
        zip_handle = ZipFile(zip_path)
        zip_handles[zip_path] = zip_handle
        for info in zip_handle.infolist():
            if info.is_dir():
                continue
            basename = Path(info.filename).name
            if not basename:
                continue
            filename_index[basename].append(
                ZipMemberReference(
                    zip_path=zip_path,
                    member_name=info.filename,
                    file_size=info.file_size,
                )
            )
            reference = filename_index[basename][-1]
            filename_casefold_index[reference.basename_casefold].append(reference)
            stem_casefold_index[reference.stem_casefold].append(reference)
            member_count += 1

    return (
        zip_handles,
        filename_index,
        filename_casefold_index,
        stem_casefold_index,
        member_count,
    )


def dedupe_candidates(candidates: list[ZipMemberReference]) -> list[ZipMemberReference]:
    unique_candidates: list[ZipMemberReference] = []
    seen: set[tuple[Path, str]] = set()
    for candidate in candidates:
        key = (candidate.zip_path, candidate.member_name)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)
    return unique_candidates


def filter_candidates_by_category(
    candidates: list[ZipMemberReference],
    category: str,
) -> list[ZipMemberReference]:
    if not category:
        return dedupe_candidates(candidates)

    category_casefold = category.casefold()
    preferred = [
        candidate
        for candidate in candidates
        if any(part.casefold() == category_casefold for part in candidate.member_parts)
    ]
    if preferred:
        return dedupe_candidates(preferred)
    return dedupe_candidates(candidates)


def select_unique_candidate(
    candidates: list[ZipMemberReference],
) -> tuple[ZipMemberReference | None, str | None]:
    if not candidates:
        return None, "image_missing"
    if len(candidates) == 1:
        return candidates[0], None

    unique_member_names = {candidate.member_name for candidate in candidates}
    if len(unique_member_names) == 1:
        return candidates[0], None
    return None, "image_ambiguous"


def resolve_zip_member(
    record: PlannedPositiveRecord,
    filename_index: dict[str, list[ZipMemberReference]],
    filename_casefold_index: dict[str, list[ZipMemberReference]],
    stem_casefold_index: dict[str, list[ZipMemberReference]],
) -> tuple[ZipMemberReference | None, str | None]:
    search_pools = [
        filename_index.get(record.image_filename, []),
        filename_casefold_index.get(record.image_filename.casefold(), []),
    ]

    stem_key = Path(record.image_filename).stem.casefold()
    if stem_key:
        search_pools.append(stem_casefold_index.get(stem_key, []))

    for candidates in search_pools:
        if not candidates:
            continue
        filtered_candidates = filter_candidates_by_category(candidates, record.label_category)
        candidate, issue_type = select_unique_candidate(filtered_candidates)
        if issue_type == "image_ambiguous":
            return None, issue_type
        if candidate is not None:
            return candidate, None

    return None, "image_missing"


def resolve_label_json_path(record: PlannedPositiveRecord, train_label_root: Path) -> Path | None:
    candidate_paths: list[Path] = []
    if str(record.json_path):
        candidate_paths.append(record.json_path.expanduser())
    candidate_paths.append((train_label_root / record.json_rel_path).resolve())

    seen: set[Path] = set()
    for candidate_path in candidate_paths:
        resolved = candidate_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    return None


def remove_existing_file(path: Path) -> None:
    if path.is_symlink() or path.exists():
        path.unlink()


def materialize_label_file(
    source_path: Path,
    destination_path: Path,
    link_mode: str,
    stats: Counter[str],
) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    remove_existing_file(destination_path)

    if link_mode == "copy":
        shutil.copy2(source_path, destination_path)
        return

    if link_mode == "symlink":
        destination_path.symlink_to(source_path)
        return

    try:
        os.link(source_path, destination_path)
    except OSError as exc:
        if exc.errno not in {errno.EXDEV, errno.EPERM, errno.EACCES, errno.ENOTSUP}:
            raise
        LOGGER.warning(
            "Hardlink failed for %s -> %s (%s). Falling back to copy.",
            source_path,
            destination_path,
            exc,
        )
        shutil.copy2(source_path, destination_path)
        stats["label_hardlink_fallback_to_copy"] += 1


def extract_zip_member_to_path(
    zip_handle: ZipFile,
    member_name: str,
    destination_path: Path,
) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    remove_existing_file(destination_path)
    with zip_handle.open(member_name) as source_handle, destination_path.open("wb") as output_handle:
        shutil.copyfileobj(source_handle, output_handle)


def build_missing_row(
    record: PlannedPositiveRecord,
    *,
    issue_type: str,
    detail: str,
) -> dict[str, str]:
    return {
        "issue_type": issue_type,
        "disease_code": record.disease_code,
        "source_split": record.source_split,
        "image_filename": record.image_filename,
        "json_filename": record.json_filename,
        "json_rel_path": record.json_rel_path,
        "detail": detail,
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_stats_json(path: Path, stats: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_counts(stats: Counter[str]) -> list[str]:
    issues: list[str] = []
    if stats["materialized_source_files"] != stats["materialized_label_files"]:
        issues.append("source/label materialized file counts do not match")
    if stats["complete_pairs_materialized"] != stats["materialized_source_files"]:
        issues.append("complete pair count does not match materialized source count")
    return issues


def materialize_subset(
    plan_csv_path: Path,
    train_source_root: Path,
    train_label_root: Path,
    out_root: Path,
    *,
    link_mode: str,
    strict: bool,
    dry_run: bool,
) -> int:
    selected_records = load_selected_positive_records(plan_csv_path)
    LOGGER.info("Loaded %d selected positive rows from planner CSV.", len(selected_records))

    zip_handles: dict[Path, ZipFile] = {}
    filename_index: dict[str, list[ZipMemberReference]] = {}
    filename_casefold_index: dict[str, list[ZipMemberReference]] = {}
    stem_casefold_index: dict[str, list[ZipMemberReference]] = {}
    total_zip_members = 0
    stats: Counter[str] = Counter()
    missing_rows: list[dict[str, str]] = []
    selected_count_by_disease: Counter[str] = Counter()
    materialized_count_by_disease: Counter[str] = Counter()

    try:
        (
            zip_handles,
            filename_index,
            filename_casefold_index,
            stem_casefold_index,
            total_zip_members,
        ) = index_source_zip_members(train_source_root)
        LOGGER.info(
            "Indexed %d zip files and %d source members.",
            len(zip_handles),
            total_zip_members,
        )

        for record in selected_records:
            selected_count_by_disease[record.disease_code] += 1
            member_ref, member_issue = resolve_zip_member(
                record,
                filename_index,
                filename_casefold_index,
                stem_casefold_index,
            )
            if member_issue == "image_missing":
                stats["missing_images"] += 1
                missing_rows.append(
                    build_missing_row(
                        record,
                        issue_type="image_missing",
                        detail="No source zip member matched image_filename.",
                    )
                )
                continue
            if member_issue == "image_ambiguous":
                stats["ambiguous_images"] += 1
                candidates = filename_index.get(record.image_filename, [])
                detail = "|".join(sorted(candidate.member_name for candidate in candidates))
                missing_rows.append(
                    build_missing_row(
                        record,
                        issue_type="image_ambiguous",
                        detail=detail,
                    )
                )
                continue

            label_source_path = resolve_label_json_path(record, train_label_root)
            if label_source_path is None:
                stats["missing_jsons"] += 1
                missing_rows.append(
                    build_missing_row(
                        record,
                        issue_type="json_missing",
                        detail="Could not resolve JSON under train label root.",
                    )
                )
                continue

            if member_ref is None:
                continue

            destination_source_path = out_root / "source" / member_ref.member_name
            destination_label_path = out_root / "label" / record.json_rel_path

            if not dry_run:
                extract_zip_member_to_path(
                    zip_handles[member_ref.zip_path],
                    member_ref.member_name,
                    destination_source_path,
                )
                materialize_label_file(
                    label_source_path,
                    destination_label_path,
                    link_mode,
                    stats,
                )

            stats["materialized_source_files"] += 1
            stats["materialized_label_files"] += 1
            stats["complete_pairs_materialized"] += 1
            materialized_count_by_disease[record.disease_code] += 1

        validation_issues = validate_counts(stats)
        if validation_issues:
            for issue in validation_issues:
                LOGGER.warning(issue)

        missing_by_disease_code: Counter[str] = Counter()
        missing_by_issue_type: Counter[str] = Counter()
        missing_by_extension: Counter[str] = Counter()
        for missing_row in missing_rows:
            missing_by_disease_code[missing_row["disease_code"]] += 1
            missing_by_issue_type[missing_row["issue_type"]] += 1
            missing_by_extension[image_extension(missing_row["image_filename"])] += 1

        stats_payload = {
            "plan_csv": str(plan_csv_path),
            "train_source_root": str(train_source_root),
            "train_label_root": str(train_label_root),
            "out_root": str(out_root),
            "link_mode_requested": link_mode,
            "source_materialization_mode": "copy_from_zip",
            "strict": strict,
            "dry_run": dry_run,
            "selected_positive_rows": len(selected_records),
            "complete_pairs_materialized": stats["complete_pairs_materialized"],
            "materialized_source_files": stats["materialized_source_files"],
            "materialized_label_files": stats["materialized_label_files"],
            "missing_images": stats["missing_images"],
            "missing_jsons": stats["missing_jsons"],
            "ambiguous_images": stats["ambiguous_images"],
            "missing_rows_written": len(missing_rows),
            "label_hardlink_fallback_to_copy": stats["label_hardlink_fallback_to_copy"],
            "zip_files_indexed": len(zip_handles),
            "zip_members_indexed": total_zip_members,
            "selected_count_by_disease": dict(sorted(selected_count_by_disease.items())),
            "materialized_count_by_disease": dict(sorted(materialized_count_by_disease.items())),
            "missing_by_disease_code": sort_counter(missing_by_disease_code),
            "missing_by_issue_type": sort_counter(missing_by_issue_type),
            "missing_by_extension": sort_counter(missing_by_extension),
            "validation_issues": validation_issues,
        }

        if not dry_run:
            write_csv(out_root / "missing_files.csv", MISSING_FIELDNAMES, missing_rows)
            write_stats_json(out_root / "subset_stats.json", stats_payload)

        LOGGER.info(
            "Selected=%d complete_pairs=%d missing=%d ambiguous=%d",
            len(selected_records),
            stats["complete_pairs_materialized"],
            len(missing_rows),
            stats["ambiguous_images"],
        )

        has_failures = bool(missing_rows or validation_issues)
        if strict and has_failures:
            LOGGER.error("Strict mode enabled and validation failures were found.")
            return 1
        return 0
    finally:
        for zip_handle in zip_handles.values():
            zip_handle.close()


def main() -> int:
    configure_logging()
    args = parse_args()
    plan_csv_path = Path(args.plan_csv).expanduser().resolve()
    train_source_root = Path(args.train_source_root).expanduser().resolve()
    train_label_root = Path(args.train_label_root).expanduser().resolve()
    out_root = Path(args.out_root).expanduser().resolve()

    if not plan_csv_path.exists() or not plan_csv_path.is_file():
        raise SystemExit(f"--plan-csv must point to an existing file: {plan_csv_path}")
    if not train_source_root.exists() or not train_source_root.is_dir():
        raise SystemExit(
            f"--train-source-root must point to an existing directory: {train_source_root}"
        )
    if not train_label_root.exists() or not train_label_root.is_dir():
        raise SystemExit(
            f"--train-label-root must point to an existing directory: {train_label_root}"
        )

    return materialize_subset(
        plan_csv_path,
        train_source_root,
        train_label_root,
        out_root,
        link_mode=args.link_mode,
        strict=args.strict,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
