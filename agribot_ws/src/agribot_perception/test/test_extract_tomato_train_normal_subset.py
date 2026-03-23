from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile


def run_extractor(
    zip_path: Path,
    out_root: Path,
    manifest_csv: Path,
    *,
    seed: int,
) -> subprocess.CompletedProcess[str]:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "extract_tomato_train_normal_subset.py"
    )
    return subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--zip-path",
            str(zip_path),
            "--out-root",
            str(out_root),
            "--num-samples",
            "2",
            "--seed",
            str(seed),
            "--manifest-csv",
            str(manifest_csv),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def read_manifest_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_normal_extractor_samples_only_jpg_and_is_seeded(tmp_path: Path) -> None:
    zip_path = tmp_path / "TS25_토마토_정상.zip"
    with ZipFile(zip_path, "w") as zf:
        zf.writestr("토마토/정상/a.jpg", b"a")
        zf.writestr("토마토/정상/b.JPG", b"b")
        zf.writestr("토마토/정상/c.jpg", b"c")
        zf.writestr("토마토/정상/d.png", b"d")
        zf.writestr("토마토/정상/sub/e.jpg", b"e")

    out_root_a = tmp_path / "normal_a"
    manifest_a = out_root_a / "normal_subset_manifest.csv"
    out_root_b = tmp_path / "normal_b"
    manifest_b = out_root_b / "normal_subset_manifest.csv"

    run_extractor(zip_path, out_root_a, manifest_a, seed=42)
    run_extractor(zip_path, out_root_b, manifest_b, seed=42)

    rows_a = read_manifest_rows(manifest_a)
    rows_b = read_manifest_rows(manifest_b)

    assert rows_a == rows_b
    assert len(rows_a) == 2
    assert all(row["zip_member_path"].lower().endswith(".jpg") for row in rows_a)

    for row in rows_a:
        output_path = out_root_a / row["output_rel_path"]
        assert output_path.exists()

    stats = json.loads((out_root_a / "subset_stats.json").read_text(encoding="utf-8"))
    assert stats["available_jpg_candidates"] == 4
    assert stats["selected_samples"] == 2
    assert stats["shortfall_count"] == 0
