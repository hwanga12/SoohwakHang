from pathlib import Path

from geometry_msgs.msg import Pose
from nav_msgs.msg import MapMetaData, OccupancyGrid

from agribot_navigation.frontier_explorer import build_frontier_candidates, frontier_clusters


def make_map(width: int, height: int, data: list[int], resolution: float = 1.0) -> OccupancyGrid:
    grid = OccupancyGrid()
    grid.info = MapMetaData()
    grid.info.width = width
    grid.info.height = height
    grid.info.resolution = resolution
    grid.info.origin = Pose()
    grid.data = data
    return grid


def test_frontier_clusters_detects_unknown_boundary_free_space() -> None:
    # 5x5 map:
    # unknown ring surrounds a free 3x3 patch, producing a single frontier cluster.
    grid = make_map(
        5,
        5,
        [
            -1, -1, -1, -1, -1,
            -1, 0, 0, 0, -1,
            -1, 0, 0, 0, -1,
            -1, 0, 0, 0, -1,
            -1, -1, -1, -1, -1,
        ],
    )

    clusters = frontier_clusters(grid, minimum_cluster_size=4)

    assert len(clusters) == 1
    assert len(clusters[0]) == 8


def test_build_frontier_candidates_prefers_larger_farther_cluster() -> None:
    # Two frontier regions exist. The larger and farther region should score higher.
    grid = make_map(
        8,
        5,
        [
            -1, -1, -1, -1, -1, -1, -1, -1,
            -1, 0, 0, -1, -1, 0, 0, -1,
            -1, 0, 0, -1, -1, 0, 0, 0,
            -1, 0, 0, -1, -1, 0, 0, 0,
            -1, -1, -1, -1, -1, -1, -1, -1,
        ],
    )

    candidates = build_frontier_candidates(
        grid,
        robot_x=1.5,
        robot_y=1.5,
        minimum_cluster_size=3,
        minimum_goal_distance_m=0.5,
        cluster_size_weight=2.5,
        maximum_distance_score_m=8.0,
        blacklisted_points=[],
        blacklist_radius_m=1.0,
    )

    assert candidates
    best = candidates[0]
    assert best.world_x > 4.0
    assert best.size >= 5


def test_build_frontier_candidates_skips_blacklisted_goals() -> None:
    grid = make_map(
        5,
        5,
        [
            -1, -1, -1, -1, -1,
            -1, 0, 0, 0, -1,
            -1, 0, 0, 0, -1,
            -1, 0, 0, 0, -1,
            -1, -1, -1, -1, -1,
        ],
    )

    candidates = build_frontier_candidates(
        grid,
        robot_x=2.5,
        robot_y=2.5,
        minimum_cluster_size=4,
        minimum_goal_distance_m=0.5,
        cluster_size_weight=2.5,
        maximum_distance_score_m=8.0,
        blacklisted_points=[(2.5, 1.5)],
        blacklist_radius_m=2.0,
    )

    assert candidates == []
