from geometry_msgs.msg import Pose
from nav_msgs.msg import MapMetaData, OccupancyGrid
from sensor_msgs.msg import LaserScan

from agribot_navigation.frontier_explorer import (
    RobotPose,
    bootstrap_ready_for_frontier,
    boundary_ready_for_frontier,
    build_coverage_fill_goals,
    build_frontier_candidates,
    choose_open_heading,
    frontier_clusters,
    wall_follow_command,
)


def make_map(width: int, height: int, data: list[int], resolution: float = 1.0) -> OccupancyGrid:
    grid = OccupancyGrid()
    grid.info = MapMetaData()
    grid.info.width = width
    grid.info.height = height
    grid.info.resolution = resolution
    grid.info.origin = Pose()
    grid.data = data
    return grid


def make_scan(
    ranges: list[float],
    *,
    angle_min: float = -3.141592653589793,
    angle_max: float = 3.141592653589793,
) -> LaserScan:
    scan = LaserScan()
    scan.angle_min = float(angle_min)
    scan.angle_max = float(angle_max)
    scan.angle_increment = float((angle_max - angle_min) / max(len(ranges) - 1, 1))
    scan.range_min = 0.12
    scan.range_max = 10.0
    scan.ranges = list(ranges)
    return scan


def test_frontier_clusters_detects_unknown_boundary_free_space() -> None:
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


def test_build_frontier_candidates_uses_standoff_goal_before_frontier_tip() -> None:
    grid = make_map(
        10,
        5,
        [
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, 0, 0, 0, 0, 0, 0, 0, 0, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
        ],
    )

    candidates = build_frontier_candidates(
        grid,
        robot_pose=RobotPose(x=1.5, y=2.5, yaw=0.0),
        minimum_cluster_size=3,
        minimum_goal_distance_m=0.5,
        cluster_size_weight=2.5,
        maximum_distance_score_m=8.0,
        support_area_weight=0.18,
        forward_preference_weight=1.5,
        frontier_standoff_m=2.0,
        staging_search_radius_m=1.0,
        staging_support_radius_m=1.0,
        blacklisted_points=[],
        blacklist_radius_m=1.0,
    )

    assert candidates
    best = candidates[0]
    assert 5.0 <= best.world_x <= 7.0
    assert best.world_x < 8.5


def test_build_frontier_candidates_skips_blacklisted_goals() -> None:
    grid = make_map(
        10,
        5,
        [
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, 0, 0, 0, 0, 0, 0, 0, 0, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
        ],
    )

    candidates = build_frontier_candidates(
        grid,
        robot_pose=RobotPose(x=1.5, y=2.5, yaw=0.0),
        minimum_cluster_size=3,
        minimum_goal_distance_m=0.5,
        cluster_size_weight=2.5,
        maximum_distance_score_m=8.0,
        support_area_weight=0.18,
        forward_preference_weight=1.5,
        frontier_standoff_m=2.0,
        staging_search_radius_m=1.0,
        staging_support_radius_m=1.0,
        blacklisted_points=[(6.5, 2.5)],
        blacklist_radius_m=2.0,
    )

    assert candidates == []


def test_choose_open_heading_prefers_forward_gap_when_front_is_clear() -> None:
    scan = make_scan([2.0] * 720)

    heading, clearance, score = choose_open_heading(
        scan,
        preferred_heading=0.0,
        heading_window=0.40,
        sample_count=72,
        forward_bias_weight=1.2,
    )

    assert heading is not None
    assert abs(heading) < 0.20
    assert clearance >= 1.9
    assert score > 0.0


def test_choose_open_heading_can_select_a_behind_escape_route() -> None:
    ranges = [0.4] * 720
    for index in list(range(0, 40)) + list(range(680, 720)):
        ranges[index] = 3.0
    scan = make_scan(ranges)

    heading, clearance, _ = choose_open_heading(
        scan,
        preferred_heading=0.0,
        heading_window=0.35,
        sample_count=72,
        forward_bias_weight=0.2,
    )

    assert heading is not None
    assert 2.5 <= abs(heading) <= 3.2
    assert clearance >= 2.5


def test_bootstrap_ready_for_frontier_requires_minimum_straight_progress() -> None:
    assert not bootstrap_ready_for_frontier(
        has_candidates=True,
        known_ratio=0.08,
        known_ratio_threshold=0.06,
        bootstrap_passes=1,
        minimum_passes=2,
        bootstrap_total_distance_m=1.25,
        minimum_total_distance_m=2.4,
    )

    assert bootstrap_ready_for_frontier(
        has_candidates=True,
        known_ratio=0.08,
        known_ratio_threshold=0.06,
        bootstrap_passes=2,
        minimum_passes=2,
        bootstrap_total_distance_m=2.5,
        minimum_total_distance_m=2.4,
    )


def test_boundary_ready_for_frontier_requires_outline_progress_and_known_ratio() -> None:
    assert not boundary_ready_for_frontier(
        has_candidates=True,
        boundary_elapsed_sec=12.0,
        minimum_boundary_duration_sec=16.0,
        boundary_distance_m=11.0,
        minimum_boundary_distance_m=10.0,
        known_ratio=0.20,
        known_ratio_threshold=0.18,
    )

    assert not boundary_ready_for_frontier(
        has_candidates=True,
        boundary_elapsed_sec=20.0,
        minimum_boundary_duration_sec=16.0,
        boundary_distance_m=11.0,
        minimum_boundary_distance_m=10.0,
        known_ratio=0.12,
        known_ratio_threshold=0.18,
    )

    assert boundary_ready_for_frontier(
        has_candidates=True,
        boundary_elapsed_sec=20.0,
        minimum_boundary_duration_sec=16.0,
        boundary_distance_m=11.0,
        minimum_boundary_distance_m=10.0,
        known_ratio=0.20,
        known_ratio_threshold=0.18,
    )


def test_wall_follow_command_arcs_through_a_corner_instead_of_full_spin() -> None:
    linear_x, angular_z = wall_follow_command(
        front_clearance=0.55,
        side_clearance=0.55,
        diagonal_clearance=0.50,
        target_distance=0.6,
        front_stop_distance=0.75,
        wall_lost_distance=1.25,
        linear_speed=0.34,
        max_angular_speed=0.65,
        side_gain=1.8,
        diagonal_gain=0.9,
        follow_side='right',
    )

    assert linear_x > 0.0
    assert angular_z > 0.0


def test_wall_follow_command_turns_left_when_right_wall_is_too_close() -> None:
    linear_x, angular_z = wall_follow_command(
        front_clearance=2.0,
        side_clearance=0.35,
        diagonal_clearance=0.40,
        target_distance=0.6,
        front_stop_distance=0.75,
        wall_lost_distance=1.25,
        linear_speed=0.24,
        max_angular_speed=0.9,
        side_gain=2.6,
        diagonal_gain=1.6,
        follow_side='right',
    )

    assert linear_x > 0.0
    assert angular_z > 0.0


def test_wall_follow_command_searches_right_when_wall_is_lost() -> None:
    linear_x, angular_z = wall_follow_command(
        front_clearance=2.0,
        side_clearance=1.8,
        diagonal_clearance=1.7,
        target_distance=0.6,
        front_stop_distance=0.75,
        wall_lost_distance=1.25,
        linear_speed=0.24,
        max_angular_speed=0.9,
        side_gain=2.6,
        diagonal_gain=1.6,
        follow_side='right',
    )

    assert linear_x > 0.0
    assert angular_z < 0.0


def test_build_coverage_fill_goals_creates_boustrophedon_endpoints() -> None:
    grid = make_map(
        8,
        6,
        [
            -1, -1, -1, -1, -1, -1, -1, -1,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            -1, -1, -1, -1, -1, -1, -1, -1,
        ],
        resolution=0.5,
    )

    goals = build_coverage_fill_goals(
        grid,
        robot_pose=RobotPose(x=0.25, y=0.75, yaw=0.0),
        lane_spacing_m=1.0,
        minimum_segment_length_m=1.5,
    )

    assert len(goals) >= 2
    assert goals[0].heading in (0.0, 3.141592653589793)
    assert goals[1].heading in (0.0, 3.141592653589793)
    assert goals[0].heading != goals[1].heading
