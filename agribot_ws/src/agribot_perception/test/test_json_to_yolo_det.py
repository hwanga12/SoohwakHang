from __future__ import annotations

import csv
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path


def write_png(path: Path, width: int, height: int) -> None:
    raw_rows = [b"\x00" + (b"\xff\xff\xff" * width) for _ in range(height)]
    raw_image = b"".join(raw_rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)

    png_bytes = b"\x89PNG\r\n\x1a\n"
    png_bytes += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png_bytes += chunk(b"IDAT", zlib.compress(raw_image))
    png_bytes += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def manifest_row(
    image_path: Path,
    image_rel_path: str,
    json_path: Path,
    json_rel_path: str,
    disease_code: str,
    *,
    is_negative_sample: bool,
    use_for_detection: bool,
    top_level_bbox_count: int,
) -> dict[str, str]:
    return {
        "image_path": str(image_path),
        "image_rel_path": image_rel_path,
        "json_path": str(json_path),
        "json_rel_path": json_rel_path,
        "disease_code": disease_code,
        "is_negative_sample": "true" if is_negative_sample else "false",
        "use_for_detection": "true" if use_for_detection else "false",
        "top_level_bbox_count": str(top_level_bbox_count),
    }


def test_manifest_to_yolo_conversion(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    positive_train_image = (
        dataset_root
        / "raw"
        / "train"
        / "extracted"
        / "source"
        / "tomato"
        / "disease"
        / "positive_train.png"
    )
    positive_val_image = (
        dataset_root
        / "raw"
        / "val"
        / "extracted"
        / "source"
        / "tomato"
        / "physiology"
        / "positive_val.png"
    )
    negative_val_image = (
        dataset_root
        / "raw"
        / "val"
        / "extracted"
        / "source"
        / "tomato"
        / "normal"
        / "negative_val.png"
    )

    positive_train_json = (
        dataset_root
        / "raw"
        / "train"
        / "extracted"
        / "label"
        / "disease"
        / "positive_train.json"
    )
    positive_val_json = (
        dataset_root
        / "raw"
        / "val"
        / "extracted"
        / "label"
        / "physiology"
        / "positive_val.json"
    )
    negative_val_json = (
        dataset_root
        / "raw"
        / "val"
        / "extracted"
        / "label"
        / "normal"
        / "negative_val.json"
    )

    write_png(positive_train_image, width=100, height=200)
    write_png(positive_val_image, width=50, height=100)
    write_png(negative_val_image, width=40, height=40)

    write_json(
        positive_train_json,
        {
            "description": {"image": positive_train_image.name, "task": "detection"},
            "annotations": {
                "crop": "2",
                "disease": "a5",
                "risk": "1",
                "area": "3",
                "grow": "12",
                "bbox": {"x": 10, "y": 20, "w": 30, "h": 40},
            },
        },
    )
    write_json(
        positive_val_json,
        {
            "description": {"image": positive_val_image.name, "task": "detection"},
            "annotation": [
                {
                    "crop": "2",
                    "disease": "b2",
                    "risk": "2",
                    "area": "1",
                    "grow": "13",
                    "bbox": {"x1": 5, "y1": 10, "x2": 25, "y2": 40},
                }
            ],
        },
    )
    write_json(
        negative_val_json,
        {
            "description": {"image": negative_val_image.name, "task": "detection"},
            "annotations": {
                "crop": "2",
                "disease": "00",
                "risk": "0",
                "area": "3",
                "grow": "12",
                "bbox": [],
            },
        },
    )

    manifest_path = tmp_path / "tomato_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "image_path",
                "image_rel_path",
                "json_path",
                "json_rel_path",
                "disease_code",
                "is_negative_sample",
                "use_for_detection",
                "top_level_bbox_count",
            ],
        )
        writer.writeheader()
        writer.writerow(
            manifest_row(
                positive_train_image,
                "raw/train/extracted/source/tomato/disease/positive_train.png",
                positive_train_json,
                "raw/train/extracted/label/disease/positive_train.json",
                "a5",
                is_negative_sample=False,
                use_for_detection=True,
                top_level_bbox_count=1,
            )
        )
        writer.writerow(
            manifest_row(
                positive_val_image,
                "raw/val/extracted/source/tomato/physiology/positive_val.png",
                positive_val_json,
                "raw/val/extracted/label/physiology/positive_val.json",
                "b2",
                is_negative_sample=False,
                use_for_detection=True,
                top_level_bbox_count=1,
            )
        )
        writer.writerow(
            manifest_row(
                negative_val_image,
                "raw/val/extracted/source/tomato/normal/negative_val.png",
                negative_val_json,
                "raw/val/extracted/label/normal/negative_val.json",
                "00",
                is_negative_sample=True,
                use_for_detection=True,
                top_level_bbox_count=0,
            )
        )
        writer.writerow(
            manifest_row(
                tmp_path / "skip" / "missing.png",
                "raw/train/extracted/source/tomato/skip/missing.png",
                tmp_path / "skip" / "missing.json",
                "raw/train/extracted/label/tomato/skip/missing.json",
                "a6",
                is_negative_sample=False,
                use_for_detection=False,
                top_level_bbox_count=1,
            )
        )

    output_root = tmp_path / "yolo" / "tomato_det_v1"
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "json_to_yolo_det.py"
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--manifest",
            str(manifest_path),
            "--output-root",
            str(output_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Rows converted: 3" in result.stdout
    assert "Positive samples: 2" in result.stdout
    assert "Negative samples: 1" in result.stdout

    train_image_out = (
        output_root
        / "images"
        / "train"
        / "extracted"
        / "source"
        / "tomato"
        / "disease"
        / "positive_train.png"
    )
    train_label_out = (
        output_root
        / "labels"
        / "train"
        / "extracted"
        / "source"
        / "tomato"
        / "disease"
        / "positive_train.txt"
    )
    val_positive_label_out = (
        output_root
        / "labels"
        / "val"
        / "extracted"
        / "source"
        / "tomato"
        / "physiology"
        / "positive_val.txt"
    )
    val_negative_label_out = (
        output_root
        / "labels"
        / "val"
        / "extracted"
        / "source"
        / "tomato"
        / "normal"
        / "negative_val.txt"
    )

    assert train_image_out.exists()
    assert train_label_out.read_text(encoding="utf-8").strip() == (
        "0 0.250000 0.200000 0.300000 0.200000"
    )
    assert val_positive_label_out.read_text(encoding="utf-8").strip() == (
        "2 0.300000 0.250000 0.400000 0.300000"
    )
    assert val_negative_label_out.read_text(encoding="utf-8") == ""

    dataset_yaml = (output_root / "dataset.yaml").read_text(encoding="utf-8")
    assert f"path: {output_root}" in dataset_yaml
    assert "train: images/train" in dataset_yaml
    assert "val: images/val" in dataset_yaml
    assert "  - tomato_powdery_mildew" in dataset_yaml
    assert "  - tomato_gray_mold" in dataset_yaml
    assert "  - tomato_crack" in dataset_yaml
    assert "  - tomato_calcium_deficiency" in dataset_yaml
