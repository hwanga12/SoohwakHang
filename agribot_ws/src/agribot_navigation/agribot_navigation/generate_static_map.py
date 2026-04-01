# 이 모듈은 자율주행과 경로 계획 패키지에서 generate static map 기능을 담당한다.
from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass
from pathlib import Path

import yaml


FREE = 254
OCCUPIED = 0
UNKNOWN = 205

DEFAULT_RESOLUTION = 0.05
GROUND_HALF_EXTENT = 10.0
OUTER_WALL_CENTER = 10.0
OUTER_WALL_LENGTH = 20.0
OUTER_WALL_THICKNESS = 0.5
CROP_ROW_SPECS = (
    (-6.0, 14.0),
    (-2.0, 14.0),
    (2.0, 14.0),
    (6.0, 14.0),
)
CROP_ROW_THICKNESS = 0.5
SPRINKLER_CENTERS = (
    (-6.0, 0.0),
    (-2.0, 0.0),
    (2.0, 0.0),
    (6.0, 0.0),
)
SPRINKLER_SIZE = 0.1


@dataclass(frozen=True)
class Rect:
    # rect 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @classmethod
    def from_center(
        cls,
        center_x: float,
        center_y: float,
        size_x: float,
        size_y: float,
    ) -> 'Rect':
        # 입력된 center 값을 바탕으로 새 값을 만든다.
        half_x = size_x / 2.0
        half_y = size_y / 2.0
        return cls(
            min_x=center_x - half_x,
            min_y=center_y - half_y,
            max_x=center_x + half_x,
            max_y=center_y + half_y,
        )


def parse_args() -> argparse.Namespace:
    # args를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    package_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            'Generate the hardcoded Nav2 occupancy map that matches '
            'agribot_description/worlds/farm_world.sdf.'
        )
    )
    parser.add_argument(
        '--output-prefix',
        type=Path,
        default=package_root / 'maps' / 'farm_map',
        help='Output prefix for the farm occupancy map.',
    )
    parser.add_argument(
        '--boundary-yaml',
        type=Path,
        default=package_root / 'maps' / 'farm_exploration_boundary.yaml',
        help='Optional yaml path for the exploration boundary map metadata.',
    )
    parser.add_argument(
        '--resolution',
        type=float,
        default=DEFAULT_RESOLUTION,
        help='Map resolution in meters per pixel.',
    )
    return parser.parse_args()


def make_grid(width: int, height: int, value: int = FREE) -> list[bytearray]:
    # grid를 새로 만들어 다음 처리 단계로 넘긴다.
    return [bytearray([value] * width) for _ in range(height)]


def world_to_index(
    x: float,
    y: float,
    origin_x: float,
    origin_y: float,
    resolution: float,
) -> tuple[int, int]:
    # 월드 index 정보를 계산해 반환한다.
    return (
        int(math.floor((x - origin_x) / resolution)),
        int(math.floor((y - origin_y) / resolution)),
    )


def clamp(value: int, lower: int, upper: int) -> int:
    # 대상 값을 허용 범위로 제한한다.
    return max(lower, min(value, upper))


def world_range_to_index_range(
    lower: float,
    upper: float,
    origin: float,
    resolution: float,
    limit: int,
) -> tuple[int, int] | None:
    # 월드 range index 정보를 계산해 반환한다.
    start = int(math.ceil(((lower - origin) / resolution) - 0.5))
    end = int(math.floor(((upper - origin) / resolution) - 0.5))
    if end < 0 or start > limit - 1 or start > end:
        return None
    return (
        clamp(start, 0, limit - 1),
        clamp(end, 0, limit - 1),
    )


def fill_rect(
    grid: list[bytearray],
    origin_x: float,
    origin_y: float,
    resolution: float,
    rect: Rect,
    value: int,
) -> None:
    # fill rect 정보를 계산해 반환한다.
    width = len(grid[0])
    height = len(grid)
    x_range = world_range_to_index_range(
        rect.min_x,
        rect.max_x,
        origin_x,
        resolution,
        width,
    )
    y_range = world_range_to_index_range(
        rect.min_y,
        rect.max_y,
        origin_y,
        resolution,
        height,
    )
    if x_range is None or y_range is None:
        return

    start_x, end_x = x_range
    start_y, end_y = y_range
    for map_y in range(start_y, end_y + 1):
        row = grid[height - 1 - map_y]
        for map_x in range(start_x, end_x + 1):
            row[map_x] = value


def farm_ground_bounds() -> Rect:
    # 농장 ground bounds 정보를 계산해 반환한다.
    return Rect(
        min_x=-GROUND_HALF_EXTENT,
        min_y=-GROUND_HALF_EXTENT,
        max_x=GROUND_HALF_EXTENT,
        max_y=GROUND_HALF_EXTENT,
    )


def farm_collision_rects() -> tuple[Rect, ...]:
    # 농장 collision rects 정보를 계산해 반환한다.
    outer_walls = (
        Rect.from_center(0.0, OUTER_WALL_CENTER, OUTER_WALL_LENGTH, OUTER_WALL_THICKNESS),
        Rect.from_center(0.0, -OUTER_WALL_CENTER, OUTER_WALL_LENGTH, OUTER_WALL_THICKNESS),
        Rect.from_center(OUTER_WALL_CENTER, 0.0, OUTER_WALL_THICKNESS, OUTER_WALL_LENGTH),
        Rect.from_center(-OUTER_WALL_CENTER, 0.0, OUTER_WALL_THICKNESS, OUTER_WALL_LENGTH),
    )
    crop_rows = tuple(
        Rect.from_center(center_x, 0.0, CROP_ROW_THICKNESS, row_length)
        for center_x, row_length in CROP_ROW_SPECS
    )
    sprinklers = tuple(
        Rect.from_center(center_x, center_y, SPRINKLER_SIZE, SPRINKLER_SIZE)
        for center_x, center_y in SPRINKLER_CENTERS
    )
    return outer_walls + crop_rows + sprinklers


def collision_bounds(rects: tuple[Rect, ...]) -> Rect:
    # collision bounds 정보를 계산해 반환한다.
    return Rect(
        min_x=min(rect.min_x for rect in rects),
        min_y=min(rect.min_y for rect in rects),
        max_x=max(rect.max_x for rect in rects),
        max_y=max(rect.max_y for rect in rects),
    )


def build_farm_grid(
    resolution: float = DEFAULT_RESOLUTION,
) -> tuple[list[bytearray], tuple[float, float], Rect]:
    # farm grid를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    obstacles = farm_collision_rects()
    extents = collision_bounds(obstacles)
    width = int(math.ceil((extents.max_x - extents.min_x) / resolution))
    height = int(math.ceil((extents.max_y - extents.min_y) / resolution))

    origin_x = extents.min_x
    origin_y = extents.min_y
    grid = make_grid(width, height, UNKNOWN)
    fill_rect(grid, origin_x, origin_y, resolution, farm_ground_bounds(), FREE)
    for rect in obstacles:
        fill_rect(grid, origin_x, origin_y, resolution, rect, OCCUPIED)

    return grid, (origin_x, origin_y), extents


def write_pgm(path: Path, grid: list[bytearray]) -> None:
    # PGM를 파일이나 저장소에 기록한다.
    width = len(grid[0])
    height = len(grid)
    with path.open('wb') as stream:
        stream.write(f'P5\n{width} {height}\n255\n'.encode('ascii'))
        for row in grid:
            stream.write(row)


def write_map_yaml(path: Path, image_name: str, resolution: float, origin: tuple[float, float]) -> None:
    # 지도 YAML 데이터를 파일이나 저장소에 기록한다.
    payload = {
        'image': image_name,
        'mode': 'trinary',
        'resolution': resolution,
        'origin': [round(origin[0], 3), round(origin[1], 3), 0.0],
        'negate': 0,
        'occupied_thresh': 0.65,
        'free_thresh': 0.196,
    }
    with path.open('w', encoding='utf-8') as stream:
        yaml.safe_dump(payload, stream, sort_keys=False)


def relative_image_path(image_path: Path, yaml_path: Path) -> str:
    # relative 이미지 경로 정보를 계산해 반환한다.
    return os.path.relpath(image_path, yaml_path.parent)


def main() -> int:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    args = parse_args()
    grid, origin, extents = build_farm_grid(args.resolution)

    output_prefix = Path(args.output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    pgm_path = output_prefix.with_suffix('.pgm')
    yaml_path = output_prefix.with_suffix('.yaml')
    boundary_yaml_path = Path(args.boundary_yaml)
    boundary_yaml_path.parent.mkdir(parents=True, exist_ok=True)

    write_pgm(pgm_path, grid)
    write_map_yaml(
        yaml_path,
        relative_image_path(pgm_path, yaml_path),
        args.resolution,
        origin,
    )
    write_map_yaml(
        boundary_yaml_path,
        relative_image_path(pgm_path, boundary_yaml_path),
        args.resolution,
        origin,
    )

    width = len(grid[0])
    height = len(grid)
    print(
        'Wrote '
        f'{pgm_path} ({width}x{height}, resolution={args.resolution:.3f}, '
        f'origin=({origin[0]:.2f}, {origin[1]:.2f}), '
        f'collision_bounds=({extents.min_x:.2f}, {extents.min_y:.2f}) -> '
        f'({extents.max_x:.2f}, {extents.max_y:.2f}))'
    )
    print(f'Wrote {yaml_path}')
    print(f'Wrote {boundary_yaml_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
