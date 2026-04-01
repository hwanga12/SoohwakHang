# 이 테스트는 인지와 추론 패키지의 build tomato subset manifest 동작을 검증한다.
from __future__ import annotations

import csv
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path


def write_png(path: Path, width: int, height: int) -> None:
    # PNG를 파일이나 저장소에 기록한다.
    raw_rows = [b"\x00" + (b"\xff\xff\xff" * width) for _ in range(height)]
    raw_image = b"".join(raw_rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        # chunk 정보를 계산해 반환한다.
        checksum = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)

    png_bytes = b"\x89PNG\r\n\x1a\n"
    png_bytes += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png_bytes += chunk(b"IDAT", zlib.compress(raw_image))
    png_bytes += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes)


def write_json(path: Path, payload: dict[str, object]) -> None:
    # JSON 데이터를 파일이나 저장소에 기록한다.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def find_row(rows: list[dict[str, str]], *, source_origin: str, disease_code: str) -> dict[str, str]:
    # row을 찾아 반환한다.
    for row in rows:
        if row["source_origin"] == source_origin and row["disease_code"] == disease_code:
            return row
    raise AssertionError(f"Row not found for origin={source_origin!r}, disease={disease_code!r}")


def test_build_tomato_subset_manifest_combines_train_subset_and_validation(
    tmp_path: Path,
) -> None:
    # build tomato subset manifest combines train subset AND validation 동작과 회귀 여부를 검증한다.
    train_positive_root = tmp_path / "train_positive_subset"
    train_normal_root = tmp_path / "train_normal_subset"
    val_extracted_root = tmp_path / "val_extracted"

    train_positive_image = (
        train_positive_root / "source" / "토마토" / "병해" / "positive_a5.jpg"
    )
    train_positive_json = train_positive_root / "label" / "병해" / "positive_a5.json"
    train_normal_image = train_normal_root / "source" / "토마토" / "정상" / "normal_00.jpg"
    val_positive_image = val_extracted_root / "source" / "토마토" / "생리장해" / "val_b2.jpg"
    val_positive_json = val_extracted_root / "label" / "생리장해" / "val_b2.json"
    val_normal_image = val_extracted_root / "source" / "토마토" / "정상" / "val_00.jpg"
    val_normal_json = val_extracted_root / "label" / "정상" / "val_00.json"

    write_png(train_positive_image, width=64, height=64)
    write_png(train_normal_image, width=64, height=64)
    write_png(val_positive_image, width=64, height=64)
    write_png(val_normal_image, width=64, height=64)

    write_json(
        train_positive_json,
        {
            "description": {"image": "positive_a5.JPG", "task": 1},
            "annotations": {
                "crop": "2",
                "disease": "a5",
                "risk": "2",
                "bbox": [{"x": 4, "y": 8, "w": 20, "h": 18}],
            },
        },
    )
    write_json(
        val_positive_json,
        {
            "description": {"image": val_positive_image.name, "task": 1},
            "annotations": {
                "crop": "2",
                "disease": "b2",
                "risk": "1",
                "bbox": [{"x": 10, "y": 12, "w": 16, "h": 20}],
            },
        },
    )
    write_json(
        val_normal_json,
        {
            "description": {"image": val_normal_image.name, "task": 1},
            "annotations": {
                "crop": "2",
                "disease": "00",
                "risk": "0",
                "bbox": [{"x": 1, "y": 2, "w": 8, "h": 10}],
            },
        },
    )

    output_path = tmp_path / "combined_manifest.csv"
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "build_tomato_subset_manifest.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--train-positive-root",
            str(train_positive_root),
            "--train-normal-root",
            str(train_normal_root),
            "--val-extracted-root",
            str(val_extracted_root),
            "--output",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Rows for detection: 4" in result.stdout
    assert "Detection split train: 2" in result.stdout
    assert "Detection split val: 2" in result.stdout

    with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 4

    train_positive_row = find_row(
        rows,
        source_origin="train_positive_subset",
        disease_code="a5",
    )
    assert train_positive_row["source_split"] == "train"
    assert train_positive_row["image_path"] == str(train_positive_image.resolve())
    assert train_positive_row["image_rel_path"] == "source/토마토/병해/positive_a5.jpg"
    assert train_positive_row["json_rel_path"] == "label/병해/positive_a5.json"
    assert train_positive_row["use_for_detection"] == "true"
    assert train_positive_row["skip_reason"] == ""

    train_normal_row = find_row(
        rows,
        source_origin="train_normal_subset",
        disease_code="00",
    )
    assert train_normal_row["source_split"] == "train"
    assert train_normal_row["json_path"] == ""
    assert train_normal_row["json_rel_path"] == ""
    assert train_normal_row["is_negative_sample"] == "true"
    assert train_normal_row["use_for_detection"] == "true"

    val_positive_row = find_row(rows, source_origin="val_extracted", disease_code="b2")
    assert val_positive_row["source_split"] == "val"
    assert val_positive_row["json_path"] == str(val_positive_json.resolve())
    assert val_positive_row["image_rel_path"] == "source/토마토/생리장해/val_b2.jpg"
    assert val_positive_row["use_for_detection"] == "true"

    val_normal_row = find_row(rows, source_origin="val_extracted", disease_code="00")
    assert val_normal_row["source_origin"] == "val_extracted"
    assert val_normal_row["source_split"] == "val"
    assert val_normal_row["disease_code"] == "00"
    assert val_normal_row["is_negative_sample"] == "true"
    assert val_normal_row["use_for_detection"] == "true"
    assert val_normal_row["top_level_bbox_count"] == "0"
