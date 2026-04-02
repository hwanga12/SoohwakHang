# 이 테스트는 인지와 추론 패키지의 json to yolo det 동작을 검증한다.
from __future__ import annotations

import csv
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path


MANIFEST_FIELDNAMES = [
    "image_path",
    "image_rel_path",
    "json_path",
    "json_rel_path",
    "disease_code",
    "is_negative_sample",
    "use_for_detection",
    "top_level_bbox_count",
    "source_split",
]


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


def manifest_row(
    image_path: Path,
    image_rel_path: str,
    disease_code: str,
    *,
    json_path: Path | None = None,
    json_rel_path: str = "",
    is_negative_sample: bool,
    use_for_detection: bool,
    top_level_bbox_count: int,
    source_split: str,
) -> dict[str, str]:
    # manifest row 정보를 계산해 반환한다.
    return {
        "image_path": str(image_path),
        "image_rel_path": image_rel_path,
        "json_path": "" if json_path is None else str(json_path),
        "json_rel_path": json_rel_path,
        "disease_code": disease_code,
        "is_negative_sample": "true" if is_negative_sample else "false",
        "use_for_detection": "true" if use_for_detection else "false",
        "top_level_bbox_count": str(top_level_bbox_count),
        "source_split": source_split,
    }


def test_manifest_to_yolo_conversion_handles_negative_rows_and_bbox_clipping(
    tmp_path: Path,
) -> None:
    # manifest TO yolo conversion handles negative rows AND 바운딩 박스 clipping 동작과 회귀 여부를 검증한다.
    dataset_root = tmp_path / "dataset"
    positive_train_image = (
        dataset_root / "train_positive" / "source" / "토마토" / "병해" / "positive_train.png"
    )
    clipped_val_image = (
        dataset_root / "val" / "source" / "토마토" / "생리장해" / "clipped_val.png"
    )
    collapsed_val_image = (
        dataset_root / "val" / "source" / "토마토" / "병해" / "collapsed_val.png"
    )
    negative_train_image = (
        dataset_root / "train_normal" / "source" / "토마토" / "정상" / "negative_train.png"
    )

    positive_train_json = (
        dataset_root / "train_positive" / "label" / "병해" / "positive_train.json"
    )
    clipped_val_json = dataset_root / "val" / "label" / "생리장해" / "clipped_val.json"
    collapsed_val_json = dataset_root / "val" / "label" / "병해" / "collapsed_val.json"

    write_png(positive_train_image, width=100, height=200)
    write_png(clipped_val_image, width=100, height=100)
    write_png(collapsed_val_image, width=50, height=50)
    write_png(negative_train_image, width=40, height=40)

    write_json(
        positive_train_json,
        {
            "description": {"image": positive_train_image.name, "task": "detection"},
            "annotations": {
                "crop": "2",
                "disease": "a5",
                "risk": "1",
                "bbox": {"x": 10, "y": 20, "w": 30, "h": 40},
            },
        },
    )
    write_json(
        clipped_val_json,
        {
            "description": {"image": clipped_val_image.name, "task": "detection"},
            "annotation": [
                {
                    "crop": "2",
                    "disease": "b2",
                    "risk": "2",
                    "bbox": {"x": 80, "y": 90, "w": 40, "h": 20},
                }
            ],
        },
    )
    write_json(
        collapsed_val_json,
        {
            "description": {"image": collapsed_val_image.name, "task": "detection"},
            "annotations": {
                "crop": "2",
                "disease": "a6",
                "risk": "3",
                "bbox": {"x": 70, "y": 70, "w": 15, "h": 20},
            },
        },
    )

    manifest_path = tmp_path / "tomato_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            manifest_row(
                positive_train_image,
                "source/토마토/병해/positive_train.png",
                "a5",
                json_path=positive_train_json,
                json_rel_path="label/병해/positive_train.json",
                is_negative_sample=False,
                use_for_detection=True,
                top_level_bbox_count=1,
                source_split="train",
            )
        )
        writer.writerow(
            manifest_row(
                clipped_val_image,
                "source/토마토/생리장해/clipped_val.png",
                "b2",
                json_path=clipped_val_json,
                json_rel_path="label/생리장해/clipped_val.json",
                is_negative_sample=False,
                use_for_detection=True,
                top_level_bbox_count=1,
                source_split="val",
            )
        )
        writer.writerow(
            manifest_row(
                collapsed_val_image,
                "source/토마토/병해/collapsed_val.png",
                "a6",
                json_path=collapsed_val_json,
                json_rel_path="label/병해/collapsed_val.json",
                is_negative_sample=False,
                use_for_detection=True,
                top_level_bbox_count=1,
                source_split="val",
            )
        )
        writer.writerow(
            manifest_row(
                negative_train_image,
                "source/토마토/정상/negative_train.png",
                "00",
                json_path=None,
                json_rel_path="",
                is_negative_sample=True,
                use_for_detection=True,
                top_level_bbox_count=0,
                source_split="train",
            )
        )

    output_root = tmp_path / "yolo" / "tomato_det_v1"
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "json_to_yolo_det.py"
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

    assert "Rows selected: 4" in result.stdout
    assert "Rows converted: 3" in result.stdout
    assert "Rows skipped: 1" in result.stdout
    assert "Positive samples: 2" in result.stdout
    assert "Negative samples: 1" in result.stdout
    assert "Clipped bboxes: 1" in result.stdout
    assert "Collapsed bboxes skipped: 1" in result.stdout
    assert "Clipped bbox" in result.stderr
    assert "Skipped collapsed bbox" in result.stderr

    train_label_out = (
        output_root / "labels" / "train" / "source" / "토마토" / "병해" / "positive_train.txt"
    )
    val_positive_label_out = (
        output_root / "labels" / "val" / "source" / "토마토" / "생리장해" / "clipped_val.txt"
    )
    negative_label_out = (
        output_root / "labels" / "train" / "source" / "토마토" / "정상" / "negative_train.txt"
    )
    collapsed_image_out = (
        output_root / "images" / "val" / "source" / "토마토" / "병해" / "collapsed_val.png"
    )

    assert train_label_out.read_text(encoding="utf-8").strip() == (
        "0 0.250000 0.200000 0.300000 0.200000"
    )
    assert val_positive_label_out.read_text(encoding="utf-8").strip() == (
        "2 0.900000 0.950000 0.200000 0.100000"
    )
    assert negative_label_out.read_text(encoding="utf-8") == ""
    assert not collapsed_image_out.exists()

    dataset_yaml = (output_root / "dataset.yaml").read_text(encoding="utf-8")
    assert f"path: {output_root}" in dataset_yaml
    assert "train: images/train" in dataset_yaml
    assert "val: images/val" in dataset_yaml
    assert "  - tomato_powdery_mildew" in dataset_yaml
    assert "  - tomato_gray_mold" in dataset_yaml
    assert "  - tomato_crack" in dataset_yaml
    assert "  - tomato_calcium_deficiency" in dataset_yaml

    stats = json.loads((output_root / "stats.json").read_text(encoding="utf-8"))
    assert stats["selected_rows"] == 4
    assert stats["converted_rows"] == 3
    assert stats["skipped_rows"] == 1
    assert stats["positive_samples"] == 2
    assert stats["negative_samples"] == 1
    assert stats["clipped_bbox_count"] == 1
    assert stats["collapsed_bbox_count"] == 1
    assert stats["skipped_by_reason"] == {"no_valid_bbox_after_clipping": 1}

    with (output_root / "skipped.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        skipped_rows = list(csv.DictReader(handle))

    assert [row["issue_type"] for row in skipped_rows] == [
        "collapsed_bbox",
        "row_skipped",
    ]
    assert skipped_rows[0]["disease_code"] == "a6"
    assert skipped_rows[1]["detail"] == "no_valid_bbox_after_clipping"
