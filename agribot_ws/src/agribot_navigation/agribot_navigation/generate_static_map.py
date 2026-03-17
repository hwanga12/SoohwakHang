"""Generate a reproducible baseline greenhouse occupancy map."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable

import yaml


FREE = 254
OCCUPIED = 0
UNKNOWN = 205


def parse_args() -> argparse.Namespace:
    package_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Generate a baseline greenhouse occupancy map from the committed "
            "zone and crop metadata."
        )
    )
    parser.add_argument(
        '--zones',
        type=Path,
        default=package_root / 'config' / 'zones.yaml',
        help='Path to zones.yaml.',
    )
    parser.add_argument(
        '--crops',
        type=Path,
        default=package_root.parent / 'agribot_description' / 'config' / 'crop_instances.yaml',
        help='Path to crop_instances.yaml.',
    )
    parser.add_argument(
        '--output-prefix',
        type=Path,
        default=package_root / 'maps' / 'greenhouse_map',
        help='Output prefix for the generated map files.',
    )
    parser.add_argument('--resolution', type=float, default=0.10)
    parser.add_argument('--padding', type=float, default=5.0)
    parser.add_argument('--wall-thickness', type=float, default=0.80)
    parser.add_argument('--crop-padding-x', type=float, default=2.50)
    parser.add_argument('--crop-padding-y', type=float, default=4.00)
    parser.add_argument('--plant-radius', type=float, default=1.00)
    parser.add_argument('--entrance-half-width', type=float, default=4.00)
    return parser.parse_args()


def load_yaml(path: Path) -> dict:
    with path.open('r', encoding='utf-8') as stream:
        return yaml.safe_load(stream)


def make_grid(width: int, height: int, value: int = FREE) -> list[bytearray]:
    return [bytearray([value] * width) for _ in range(height)]


def world_to_index(
    x: float,
    y: float,
    origin_x: float,
    origin_y: float,
    resolution: float,
) -> tuple[int, int]:
    return (
        int(math.floor((x - origin_x) / resolution)),
        int(math.floor((y - origin_y) / resolution)),
    )


def clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def fill_rect(
    grid: list[bytearray],
    origin_x: float,
    origin_y: float,
    resolution: float,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    value: int,
) -> None:
    width = len(grid[0])
    height = len(grid)
    start_x, start_y = world_to_index(min_x, min_y, origin_x, origin_y, resolution)
    end_x, end_y = world_to_index(max_x, max_y, origin_x, origin_y, resolution)

    start_x = clamp(start_x, 0, width - 1)
    end_x = clamp(end_x, 0, width - 1)
    start_y = clamp(start_y, 0, height - 1)
    end_y = clamp(end_y, 0, height - 1)

    for map_y in range(start_y, end_y + 1):
        row = grid[height - 1 - map_y]
        for map_x in range(start_x, end_x + 1):
            row[map_x] = value


def fill_circle(
    grid: list[bytearray],
    origin_x: float,
    origin_y: float,
    resolution: float,
    center_x: float,
    center_y: float,
    radius: float,
    value: int,
) -> None:
    width = len(grid[0])
    height = len(grid)
    min_x, min_y = world_to_index(
        center_x - radius,
        center_y - radius,
        origin_x,
        origin_y,
        resolution,
    )
    max_x, max_y = world_to_index(
        center_x + radius,
        center_y + radius,
        origin_x,
        origin_y,
        resolution,
    )
    min_x = clamp(min_x, 0, width - 1)
    max_x = clamp(max_x, 0, width - 1)
    min_y = clamp(min_y, 0, height - 1)
    max_y = clamp(max_y, 0, height - 1)

    radius_sq = radius * radius
    for map_y in range(min_y, max_y + 1):
        world_y = origin_y + (map_y + 0.5) * resolution
        row = grid[height - 1 - map_y]
        for map_x in range(min_x, max_x + 1):
            world_x = origin_x + (map_x + 0.5) * resolution
            if (world_x - center_x) ** 2 + (world_y - center_y) ** 2 <= radius_sq:
                row[map_x] = value


def build_crop_beds(
    plants: Iterable[dict],
    pad_x: float,
    pad_y: float,
) -> list[tuple[float, float, float, float]]:
    grouped: dict[str, list[tuple[float, float]]] = {'left': [], 'right': []}
    for plant in plants:
        pose = plant['pose']
        side = 'left' if pose['x'] < 0.0 else 'right'
        grouped[side].append((pose['x'], pose['y']))

    beds: list[tuple[float, float, float, float]] = []
    for poses in grouped.values():
        if not poses:
            continue
        xs = [pose[0] for pose in poses]
        ys = [pose[1] for pose in poses]
        beds.append((
            min(xs) - pad_x,
            min(ys) - pad_y,
            max(xs) + pad_x,
            max(ys) + pad_y,
        ))
    return beds


def write_pgm(path: Path, grid: list[bytearray]) -> None:
    width = len(grid[0])
    height = len(grid)
    with path.open('wb') as stream:
        stream.write(f'P5\n{width} {height}\n255\n'.encode('ascii'))
        for row in grid:
            stream.write(row)


def write_map_yaml(path: Path, image_name: str, resolution: float, origin: tuple[float, float]) -> None:
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


def main() -> int:
    args = parse_args()
    zones = load_yaml(Path(args.zones))
    crops = load_yaml(Path(args.crops))

    zone = next(
        candidate
        for candidate in zones['zones']
        if candidate['zone_id'] == zones['default_zone_id']
    )
    bounds = zone['bounds']
    plants = crops['plants']

    origin_x = bounds['min_x'] - args.padding
    origin_y = bounds['min_y'] - args.padding
    width = int(math.ceil((bounds['max_x'] - bounds['min_x'] + 2 * args.padding) / args.resolution))
    height = int(math.ceil((bounds['max_y'] - bounds['min_y'] + 2 * args.padding) / args.resolution))

    grid = make_grid(width, height, UNKNOWN)
    fill_rect(
        grid,
        origin_x,
        origin_y,
        args.resolution,
        bounds['min_x'],
        bounds['min_y'],
        bounds['max_x'],
        bounds['max_y'],
        FREE,
    )

    wall = args.wall_thickness
    entrance_half_width = args.entrance_half_width
    fill_rect(
        grid,
        origin_x,
        origin_y,
        args.resolution,
        bounds['min_x'],
        bounds['min_y'],
        bounds['min_x'] + wall,
        bounds['max_y'],
        OCCUPIED,
    )
    fill_rect(
        grid,
        origin_x,
        origin_y,
        args.resolution,
        bounds['max_x'] - wall,
        bounds['min_y'],
        bounds['max_x'],
        bounds['max_y'],
        OCCUPIED,
    )
    fill_rect(
        grid,
        origin_x,
        origin_y,
        args.resolution,
        bounds['min_x'],
        bounds['max_y'] - wall,
        bounds['max_x'],
        bounds['max_y'],
        OCCUPIED,
    )
    fill_rect(
        grid,
        origin_x,
        origin_y,
        args.resolution,
        bounds['min_x'],
        bounds['min_y'],
        -entrance_half_width,
        bounds['min_y'] + wall,
        OCCUPIED,
    )
    fill_rect(
        grid,
        origin_x,
        origin_y,
        args.resolution,
        entrance_half_width,
        bounds['min_y'],
        bounds['max_x'],
        bounds['min_y'] + wall,
        OCCUPIED,
    )

    for min_x, min_y, max_x, max_y in build_crop_beds(
        plants,
        args.crop_padding_x,
        args.crop_padding_y,
    ):
        fill_rect(
            grid,
            origin_x,
            origin_y,
            args.resolution,
            min_x,
            min_y,
            max_x,
            max_y,
            OCCUPIED,
        )

    for plant in plants:
        pose = plant['pose']
        fill_circle(
            grid,
            origin_x,
            origin_y,
            args.resolution,
            pose['x'],
            pose['y'],
            args.plant_radius,
            OCCUPIED,
        )

    output_prefix = Path(args.output_prefix)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    pgm_path = output_prefix.with_suffix('.pgm')
    yaml_path = output_prefix.with_suffix('.yaml')
    write_pgm(pgm_path, grid)
    write_map_yaml(yaml_path, pgm_path.name, args.resolution, (origin_x, origin_y))

    print(f'Wrote {pgm_path}')
    print(f'Wrote {yaml_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
