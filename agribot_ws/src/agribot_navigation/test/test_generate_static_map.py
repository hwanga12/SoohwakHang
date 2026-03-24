from agribot_navigation.generate_static_map import (
    DEFAULT_RESOLUTION,
    FREE,
    OCCUPIED,
    UNKNOWN,
    build_farm_grid,
    farm_collision_rects,
    world_to_index,
)


def _cell_value(
    grid: list[bytearray],
    origin: tuple[float, float],
    world_x: float,
    world_y: float,
) -> int:
    map_x, map_y = world_to_index(
        world_x,
        world_y,
        origin[0],
        origin[1],
        DEFAULT_RESOLUTION,
    )
    return grid[len(grid) - 1 - map_y][map_x]


def test_farm_collision_rects_match_hardcoded_world_geometry() -> None:
    rects = farm_collision_rects()

    assert len(rects) == 12
    assert rects[0].min_x == -10.0
    assert rects[0].max_x == 10.0
    assert rects[0].min_y == 9.75
    assert rects[0].max_y == 10.25
    assert rects[4].min_x == -6.25
    assert rects[4].max_x == -5.75
    assert rects[4].min_y == -7.0
    assert rects[4].max_y == 7.0
    assert rects[-1].min_x == 5.95
    assert rects[-1].max_x == 6.05
    assert rects[-1].min_y == -0.05
    assert rects[-1].max_y == 0.05


def test_build_farm_grid_matches_world_bounds_and_occupancy() -> None:
    grid, origin, extents = build_farm_grid()

    assert origin == (-10.25, -10.25)
    assert extents.min_x == -10.25
    assert extents.max_x == 10.25
    assert extents.min_y == -10.25
    assert extents.max_y == 10.25
    assert len(grid) == 410
    assert len(grid[0]) == 410

    assert _cell_value(grid, origin, 0.0, 0.0) == FREE
    assert _cell_value(grid, origin, 0.0, 1.5) == FREE
    assert _cell_value(grid, origin, 2.0, 0.0) == OCCUPIED
    assert _cell_value(grid, origin, 10.0, 0.0) == OCCUPIED
    assert _cell_value(grid, origin, 9.5, 9.5) == FREE
    assert _cell_value(grid, origin, 10.2, 10.2) == UNKNOWN
