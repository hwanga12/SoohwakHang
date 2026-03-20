from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


def write_label_json(
    path: Path,
    *,
    disease_code: str,
    image_name: str,
    bbox_count: int = 1,
    risk: str = "1",
    use_list_container: bool = False,
) -> None:
    payload = {
        "description": {"image": image_name, "task": "detection"},
        "annotations" if not use_list_container else "annotation": {
            "crop": "2",
            "disease": disease_code,
            "risk": risk,
            "area": "3",
            "grow": "12",
            "bbox": [] if bbox_count == 0 else [{"x": 1, "y": 2, "w": 3, "h": 4}] * bbox_count,
        },
    }
    if use_list_container:
        payload["annotation"] = [payload["annotation"]]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def run_planner(label_root: Path, output_path: Path, *, seed: int) -> subprocess.CompletedProcess[str]:
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "plan_tomato_train_subset.py"
    )
    return subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--label-root",
            str(label_root),
            "--output",
            str(output_path),
            "--seed",
            str(seed),
            "--quota-a5",
            "2",
            "--quota-a6",
            "1",
            "--quota-b2",
            "3",
            "--quota-b3",
            "1",
            "--quota-00",
            "3",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def selected_jsons(rows: list[dict[str, str]], disease_code: str) -> list[str]:
    return sorted(
        row["json_filename"]
        for row in rows
        if row["row_type"] == "candidate"
        and row["disease_code"] == disease_code
        and row["is_selected"] == "true"
    )


def test_subset_planner_writes_candidate_and_shortfall_rows(tmp_path: Path) -> None:
    label_root = tmp_path / "dataset" / "raw"

    for name in ("a_001.json", "a_002.json", "a_003.json"):
        write_label_json(
            label_root / "train" / "extracted" / "label" / "병해" / name,
            disease_code="a5",
            image_name=name.replace(".json", ".jpg"),
        )

    for name in ("m_001.json", "m_002.json"):
        write_label_json(
            label_root / "val" / "extracted" / "label" / "병해" / name,
            disease_code="a6",
            image_name=name.replace(".json", ".jpg"),
            use_list_container=True,
        )

    write_label_json(
        label_root / "train" / "extracted" / "label" / "생리장해" / "b2_only.json",
        disease_code="b2",
        image_name="b2_only.jpg",
        risk="2",
    )

    for name in ("n_001.json", "n_002.json", "n_003.json", "n_004.json", "n_005.json"):
        write_label_json(
            label_root / "train" / "extracted" / "label" / "정상" / name,
            disease_code="00",
            image_name=name.replace(".json", ".jpg"),
            bbox_count=0,
            risk="0",
        )

    output_path = tmp_path / "subset_plan.csv"
    result = run_planner(label_root, output_path, seed=7)
    rows = read_rows(output_path)

    assert "a5: requested=2 available=3 selected=2 shortfall=0" in result.stdout
    assert "b2: requested=3 available=1 selected=1 shortfall=2" in result.stdout
    assert "b3: requested=1 available=0 selected=0 shortfall=1" in result.stdout
    assert "Shortfall classes: b2, b3" in result.stdout

    expected_columns = {
        "row_type",
        "is_selected",
        "selected_reason",
        "crop_code",
        "crop_name",
        "disease_code",
        "disease_name_en",
        "source_split",
        "image_filename",
        "json_filename",
        "json_rel_path",
        "json_path",
        "requested_count",
        "available_count",
        "selected_count",
        "shortfall_count",
    }
    assert expected_columns.issubset(rows[0].keys())

    a5_selected = [
        row
        for row in rows
        if row["disease_code"] == "a5"
        and row["row_type"] == "candidate"
        and row["is_selected"] == "true"
    ]
    assert [row["json_filename"] for row in a5_selected] == ["a_001.json", "a_002.json"]
    assert {row["selected_reason"] for row in a5_selected} == {"target_positive"}
    assert {row["crop_code"] for row in a5_selected} == {"2"}
    assert {row["crop_name"] for row in a5_selected} == {"tomato"}
    assert {row["disease_name_en"] for row in a5_selected} == {"tomato_powdery_mildew"}
    assert {row["source_split"] for row in a5_selected} == {"train"}

    a6_selected = [
        row
        for row in rows
        if row["disease_code"] == "a6"
        and row["row_type"] == "candidate"
        and row["is_selected"] == "true"
    ]
    assert [row["json_filename"] for row in a6_selected] == ["m_001.json"]
    assert {row["source_split"] for row in a6_selected} == {"val"}

    normal_selected = [
        row
        for row in rows
        if row["disease_code"] == "00"
        and row["row_type"] == "candidate"
        and row["is_selected"] == "true"
    ]
    assert len(normal_selected) == 3
    assert {row["selected_reason"] for row in normal_selected} == {"target_negative"}

    shortfall_rows = [
        row for row in rows if row["row_type"] == "shortfall_summary"
    ]
    assert {row["disease_code"] for row in shortfall_rows} == {"b2", "b3"}
    assert {row["selected_reason"] for row in shortfall_rows} == {
        "skipped_insufficient_candidate"
    }


def test_subset_planner_seed_is_reproducible_and_non_normal_is_stable(tmp_path: Path) -> None:
    label_root = tmp_path / "dataset" / "raw"

    for name in ("a_001.json", "a_002.json", "a_003.json"):
        write_label_json(
            label_root / "train" / "extracted" / "label" / "병해" / name,
            disease_code="a5",
            image_name=name.replace(".json", ".jpg"),
        )

    for index in range(10):
        name = f"normal_{index:03d}.json"
        write_label_json(
            label_root / "train" / "extracted" / "label" / "정상" / name,
            disease_code="00",
            image_name=name.replace(".json", ".jpg"),
            bbox_count=0,
            risk="0",
        )

    output_a = tmp_path / "subset_seed_7_a.csv"
    output_b = tmp_path / "subset_seed_7_b.csv"
    output_c = tmp_path / "subset_seed_9.csv"

    run_planner(label_root, output_a, seed=7)
    run_planner(label_root, output_b, seed=7)
    run_planner(label_root, output_c, seed=9)

    rows_a = read_rows(output_a)
    rows_b = read_rows(output_b)
    rows_c = read_rows(output_c)

    assert selected_jsons(rows_a, "a5") == ["a_001.json", "a_002.json"]
    assert selected_jsons(rows_b, "a5") == ["a_001.json", "a_002.json"]
    assert selected_jsons(rows_c, "a5") == ["a_001.json", "a_002.json"]

    normal_a = selected_jsons(rows_a, "00")
    normal_b = selected_jsons(rows_b, "00")
    normal_c = selected_jsons(rows_c, "00")

    assert normal_a == normal_b
    assert normal_a != normal_c
