from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


PLAN_FIELDNAMES = [
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


def write_plan_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"description": {"image": path.stem + ".jpg"}}), encoding="utf-8")


def build_plan_row(
    *,
    disease_code: str,
    source_split: str,
    image_filename: str,
    json_rel_path: str,
    json_path: Path,
    is_selected: bool = True,
) -> dict[str, str]:
    return {
        "row_type": "candidate",
        "is_selected": "true" if is_selected else "false",
        "selected_reason": "target_positive" if is_selected else "skipped_over_quota",
        "crop_code": "2",
        "crop_name": "tomato",
        "disease_code": disease_code,
        "disease_name_en": disease_code,
        "risk": "1",
        "top_level_bbox_count": "1",
        "source_split": source_split,
        "image_filename": image_filename,
        "json_filename": Path(json_rel_path).name,
        "image_declared_path": image_filename,
        "json_rel_path": json_rel_path,
        "json_path": str(json_path),
        "requested_count": "1",
        "available_count": "1",
        "selected_count": "1" if is_selected else "0",
        "shortfall_count": "0",
    }


def run_materializer(
    plan_csv: Path,
    source_root: Path,
    label_root: Path,
    out_root: Path,
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "materialize_tomato_train_positive_subset.py"
    )
    return subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--plan-csv",
            str(plan_csv),
            "--train-source-root",
            str(source_root),
            "--train-label-root",
            str(label_root),
            "--out-root",
            str(out_root),
            *extra_args,
        ],
        capture_output=True,
        text=True,
    )


def test_positive_materializer_handles_duplicate_filenames_and_missing_rows(tmp_path: Path) -> None:
    label_root = tmp_path / "labels"
    source_root = tmp_path / "source_zip"
    out_root = tmp_path / "subset_out"

    disease_json = label_root / "병해" / "disease_shared.json"
    physiology_json = label_root / "생리장해" / "physiology_shared.json"
    stem_fallback_json = label_root / "생리장해" / "stem_fallback.json"
    missing_json = label_root / "병해" / "missing_image.json"
    write_json(disease_json)
    write_json(physiology_json)
    write_json(stem_fallback_json)
    write_json(missing_json)

    zip_dir = (
        source_root
        / "104.식물 병 유발 통합 데이터"
        / "01.데이터"
        / "1.Training"
        / "원천데이터"
    )
    zip_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_dir / "TS22_토마토_병해.zip", "w") as zf:
        zf.writestr("토마토/병해/shared.jpg", b"disease-bytes")
    with ZipFile(zip_dir / "TS23_토마토_생리장해.zip", "w") as zf:
        zf.writestr("토마토/생리장해/shared.jpg", b"physiology-bytes")
        zf.writestr("토마토/생리장해/stem_fallback.jpg", b"stem-fallback-bytes")

    plan_csv = tmp_path / "plan.csv"
    write_plan_csv(
        plan_csv,
        [
            build_plan_row(
                disease_code="a5",
                source_split="train",
                image_filename="shared.jpg",
                json_rel_path="병해/disease_shared.json",
                json_path=disease_json,
            ),
            build_plan_row(
                disease_code="b2",
                source_split="train",
                image_filename="shared.JPG",
                json_rel_path="생리장해/physiology_shared.json",
                json_path=physiology_json,
            ),
            build_plan_row(
                disease_code="b3",
                source_split="train",
                image_filename="stem_fallback.JPEG",
                json_rel_path="생리장해/stem_fallback.json",
                json_path=stem_fallback_json,
            ),
            build_plan_row(
                disease_code="a6",
                source_split="train",
                image_filename="missing.JPG",
                json_rel_path="병해/missing_image.json",
                json_path=missing_json,
            ),
            build_plan_row(
                disease_code="00",
                source_split="train",
                image_filename="normal.jpg",
                json_rel_path="정상/normal.json",
                json_path=tmp_path / "normal.json",
            ),
        ],
    )

    result = run_materializer(plan_csv, source_root, label_root, out_root)
    assert result.returncode == 0, result.stderr

    disease_image_out = out_root / "source" / "토마토" / "병해" / "shared.jpg"
    physiology_image_out = out_root / "source" / "토마토" / "생리장해" / "shared.jpg"
    stem_fallback_image_out = out_root / "source" / "토마토" / "생리장해" / "stem_fallback.jpg"
    disease_label_out = out_root / "label" / "병해" / "disease_shared.json"
    physiology_label_out = out_root / "label" / "생리장해" / "physiology_shared.json"
    stem_fallback_label_out = out_root / "label" / "생리장해" / "stem_fallback.json"

    assert disease_image_out.read_bytes() == b"disease-bytes"
    assert physiology_image_out.read_bytes() == b"physiology-bytes"
    assert stem_fallback_image_out.read_bytes() == b"stem-fallback-bytes"
    assert disease_label_out.exists()
    assert physiology_label_out.exists()
    assert stem_fallback_label_out.exists()
    assert os.stat(disease_label_out).st_ino == os.stat(disease_json).st_ino
    assert os.stat(physiology_label_out).st_ino == os.stat(physiology_json).st_ino
    assert os.stat(stem_fallback_label_out).st_ino == os.stat(stem_fallback_json).st_ino

    with (out_root / "missing_files.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        missing_rows = list(csv.DictReader(handle))
    assert len(missing_rows) == 1
    assert missing_rows[0]["issue_type"] == "image_missing"
    assert missing_rows[0]["image_filename"] == "missing.JPG"

    stats = json.loads((out_root / "subset_stats.json").read_text(encoding="utf-8"))
    assert stats["selected_positive_rows"] == 4
    assert stats["complete_pairs_materialized"] == 3
    assert stats["missing_images"] == 1
    assert stats["materialized_count_by_disease"] == {"a5": 1, "b2": 1, "b3": 1}
    assert stats["missing_by_disease_code"] == {"a6": 1}
    assert stats["missing_by_issue_type"] == {"image_missing": 1}
    assert stats["missing_by_extension"] == {".JPG": 1}


def test_positive_materializer_strict_mode_fails_on_missing_files(tmp_path: Path) -> None:
    label_root = tmp_path / "labels"
    source_root = tmp_path / "source_zip"
    out_root = tmp_path / "subset_out"

    json_path = label_root / "병해" / "missing_image.json"
    write_json(json_path)
    zip_dir = (
        source_root
        / "104.식물 병 유발 통합 데이터"
        / "01.데이터"
        / "1.Training"
        / "원천데이터"
    )
    zip_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_dir / "TS22_토마토_병해.zip", "w") as zf:
        zf.writestr("토마토/병해/other.jpg", b"other")

    plan_csv = tmp_path / "plan.csv"
    write_plan_csv(
        plan_csv,
        [
            build_plan_row(
                disease_code="a5",
                source_split="train",
                image_filename="missing.jpg",
                json_rel_path="병해/missing_image.json",
                json_path=json_path,
            )
        ],
    )

    result = run_materializer(
        plan_csv,
        source_root,
        label_root,
        out_root,
        "--strict",
    )
    assert result.returncode == 1
    assert "Strict mode enabled" in result.stderr
