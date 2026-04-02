#!/usr/bin/env python3

# 이 모듈은 인지와 추론 패키지에서 extract tomato train normal subset 기능을 담당한다.
from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zipfile import ZipFile

LOGGER = logging.getLogger("extract_tomato_train_normal_subset")
MANIFEST_FIELDNAMES = [
    "selected_index",
    "selected_reason",
    "image_filename",
    "zip_member_path",
    "output_rel_path",
    "zip_path",
]


@dataclass(frozen=True, slots=True)
class SampledMember:
    # sampled 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    member_name: str

    @property
    def image_filename(self) -> str:
        # 이미지 filename 정보를 계산해 반환한다.
        return Path(self.member_name).name


def parse_args() -> argparse.Namespace:
    # args를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    parser = argparse.ArgumentParser(
        description="Extract a seeded tomato normal subset from a single zip file."
    )
    parser.add_argument("--zip-path", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--num-samples", required=True, type=int)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--manifest-csv", required=True)
    return parser.parse_args()


def configure_logging() -> None:
    # configure logging 정보를 계산해 반환한다.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def list_jpg_members(zip_handle: ZipFile) -> list[SampledMember]:
    # JPG members를 모아 순회하기 쉬운 형태로 정리한다.
    members = [
        SampledMember(info.filename)
        for info in zip_handle.infolist()
        if not info.is_dir() and Path(info.filename).suffix.lower() == ".jpg"
    ]
    return sorted(members, key=lambda item: item.member_name.lower())


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    # CSV를 파일이나 저장소에 기록한다.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_stats_json(path: Path, stats: dict[str, Any]) -> None:
    # stats JSON 데이터를 파일이나 저장소에 기록한다.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def remove_existing_file(path: Path) -> None:
    # existing 파일를 정리하거나 제거한다.
    if path.is_symlink() or path.exists():
        path.unlink()


def extract_member(zip_handle: ZipFile, member_name: str, destination_path: Path) -> None:
    # 원본 데이터에서 member만 골라 추출한다.
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    remove_existing_file(destination_path)
    with zip_handle.open(member_name) as source_handle, destination_path.open("wb") as output_handle:
        shutil.copyfileobj(source_handle, output_handle)


def extract_normal_subset(
    zip_path: Path,
    out_root: Path,
    *,
    num_samples: int,
    seed: int,
    manifest_csv_path: Path,
) -> int:
    # 원본 데이터에서 normal subset만 골라 추출한다.
    if num_samples < 0:
        raise SystemExit("--num-samples must be >= 0.")

    with ZipFile(zip_path) as zip_handle:
        candidates = list_jpg_members(zip_handle)
        LOGGER.info("Found %d JPG candidates in %s", len(candidates), zip_path)

        selected_count = min(num_samples, len(candidates))
        rng = random.Random(seed)
        selected = rng.sample(candidates, k=selected_count) if selected_count > 0 else []
        selected_sorted = sorted(selected, key=lambda item: item.member_name.lower())

        manifest_rows: list[dict[str, str]] = []
        for index, sampled_member in enumerate(selected_sorted):
            output_rel_path = str(Path("source") / sampled_member.member_name)
            extract_member(zip_handle, sampled_member.member_name, out_root / output_rel_path)
            manifest_rows.append(
                {
                    "selected_index": str(index),
                    "selected_reason": "target_negative",
                    "image_filename": sampled_member.image_filename,
                    "zip_member_path": sampled_member.member_name,
                    "output_rel_path": output_rel_path,
                    "zip_path": str(zip_path),
                }
            )

    write_csv(manifest_csv_path, MANIFEST_FIELDNAMES, manifest_rows)
    stats_payload = {
        "zip_path": str(zip_path),
        "out_root": str(out_root),
        "manifest_csv": str(manifest_csv_path),
        "seed": seed,
        "requested_samples": num_samples,
        "available_jpg_candidates": len(candidates),
        "selected_samples": selected_count,
        "shortfall_count": max(0, num_samples - selected_count),
    }
    write_stats_json(out_root / "subset_stats.json", stats_payload)
    LOGGER.info(
        "Requested=%d selected=%d shortfall=%d",
        num_samples,
        selected_count,
        max(0, num_samples - selected_count),
    )
    return 0


def main() -> int:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    configure_logging()
    args = parse_args()
    zip_path = Path(args.zip_path).expanduser().resolve()
    out_root = Path(args.out_root).expanduser().resolve()
    manifest_csv_path = Path(args.manifest_csv).expanduser().resolve()

    if not zip_path.exists() or not zip_path.is_file():
        raise SystemExit(f"--zip-path must point to an existing file: {zip_path}")

    return extract_normal_subset(
        zip_path,
        out_root,
        num_samples=args.num_samples,
        seed=args.seed,
        manifest_csv_path=manifest_csv_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
