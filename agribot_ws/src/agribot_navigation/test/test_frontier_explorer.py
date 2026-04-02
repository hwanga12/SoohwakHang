# 이 테스트는 자율주행과 경로 계획 패키지의 frontier explorer 동작을 검증한다.
from geometry_msgs.msg import Pose
from nav_msgs.msg import MapMetaData, OccupancyGrid
from sensor_msgs.msg import LaserScan

from agribot_navigation.frontier_explorer import (
    RobotPose,
    boundary_ray_clearance,
    bootstrap_ready_for_frontier,
    boundary_ready_for_frontier,
    build_coverage_fill_goals,
    build_frontier_candidates,
    build_recovery_commands,
    choose_open_heading,
    frontier_distance_reward,
    frontier_clusters,
    wall_follow_command,
)


def make_map(width: int, height: int, data: list[int], resolution: float = 1.0) -> OccupancyGrid:
    # 지도를 새로 만들어 다음 처리 단계로 넘긴다.
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
    # scan를 새로 만들어 다음 처리 단계로 넘긴다.
    scan = LaserScan()
    scan.angle_min = float(angle_min)
    scan.angle_max = float(angle_max)
    scan.angle_increment = float((angle_max - angle_min) / max(len(ranges) - 1, 1))
    scan.range_min = 0.12
    scan.range_max = 10.0
    scan.ranges = list(ranges)
    return scan


def test_frontier_clusters_detects_unknown_boundary_free_space() -> None:
    # frontier clusters detects unknown boundary free space 동작과 회귀 여부를 검증한다.
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
    # build frontier candidates uses standoff 목표 before frontier TIP 동작과 회귀 여부를 검증한다.
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
        maximum_goal_distance_m=0.0,
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
    # build frontier candidates skips blacklisted 목표 목록 동작과 회귀 여부를 검증한다.
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
        maximum_goal_distance_m=0.0,
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


def test_build_frontier_candidates_skips_recent_goal_revisits() -> None:
    # build frontier candidates skips recent 목표 revisits 동작과 회귀 여부를 검증한다.
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
        maximum_goal_distance_m=0.0,
        cluster_size_weight=2.5,
        maximum_distance_score_m=8.0,
        support_area_weight=0.18,
        forward_preference_weight=1.5,
        frontier_standoff_m=2.0,
        staging_search_radius_m=1.0,
        staging_support_radius_m=1.0,
        blacklisted_points=[],
        blacklist_radius_m=1.0,
        recent_goal_points=[(6.5, 2.5)],
        recent_goal_radius_m=1.0,
    )

    assert candidates == []


def test_build_frontier_candidates_skips_goals_beyond_maximum_distance() -> None:
    # build frontier candidates skips 목표 목록 beyond maximum distance 동작과 회귀 여부를 검증한다.
    grid = make_map(
        20,
        5,
        [
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
            -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
        ],
    )

    candidates = build_frontier_candidates(
        grid,
        robot_pose=RobotPose(x=1.5, y=2.5, yaw=0.0),
        minimum_cluster_size=3,
        minimum_goal_distance_m=0.5,
        maximum_goal_distance_m=5.0,
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

    assert candidates == []


def test_frontier_distance_reward_prefers_nearer_candidates() -> None:
    # frontier distance reward prefers nearer candidates 동작과 회귀 여부를 검증한다.
    assert frontier_distance_reward(1.0, 4.0) == 3.0
    assert frontier_distance_reward(2.5, 4.0) == 1.5
    assert frontier_distance_reward(8.0, 4.0) == 0.0


def test_choose_open_heading_prefers_forward_gap_when_front_is_clear() -> None:
    # choose open heading prefers forward GAP when front IS clear 동작과 회귀 여부를 검증한다.
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
    # choose open heading CAN select A behind escape 경로 동작과 회귀 여부를 검증한다.
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


def test_boundary_ray_clearance_stops_at_virtual_wall() -> None:
    # boundary RAY clearance stops AT virtual wall 동작과 회귀 여부를 검증한다.
    boundary = make_map(
        6,
        3,
        [
            0, 0, 0, 100, 100, 100,
            0, 0, 0, 100, 100, 100,
            0, 0, 0, 100, 100, 100,
        ],
    )

    clearance = boundary_ray_clearance(
        boundary,
        robot_pose=RobotPose(x=1.5, y=1.5, yaw=0.0),
        relative_angle=0.0,
        max_distance=5.0,
        step_distance=0.1,
    )

    assert 1.3 <= clearance <= 1.6


def test_bootstrap_ready_for_frontier_requires_minimum_straight_progress() -> None:
    # bootstrap ready FOR frontier requires minimum straight progress 동작과 회귀 여부를 검증한다.
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
    # boundary ready FOR frontier requires outline progress AND known ratio 동작과 회귀 여부를 검증한다.
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
    # wall follow 명령 arcs through A corner instead OF full spin 동작과 회귀 여부를 검증한다.
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
    # wall follow 명령 turns left when right wall IS TOO close 동작과 회귀 여부를 검증한다.
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
    # wall follow 명령 searches right when wall IS lost 동작과 회귀 여부를 검증한다.
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


def test_build_recovery_commands_prefers_turn_and_drive_before_backup() -> None:
    # build recovery 명령 목록 prefers turn AND drive before backup 동작과 회귀 여부를 검증한다.
    commands = build_recovery_commands(
        front_clearance=1.1,
        best_heading=0.6,
        best_clearance=1.4,
        recovery_backup_distance_m=0.5,
        recovery_backup_speed_mps=0.12,
        recovery_drive_distance_m=0.6,
        recovery_drive_speed_mps=0.18,
        recovery_default_spin_rad=3.141592653589793,
    )

    assert [command.kind for command in commands] == ['spin', 'drive', 'backup']


def test_build_recovery_commands_keeps_backup_as_last_resort_in_tight_space() -> None:
    # build recovery 명령 목록 keeps backup AS last resort IN tight space 동작과 회귀 여부를 검증한다.
    commands = build_recovery_commands(
        front_clearance=0.35,
        best_heading=None,
        best_clearance=0.40,
        recovery_backup_distance_m=0.5,
        recovery_backup_speed_mps=0.12,
        recovery_drive_distance_m=0.6,
        recovery_drive_speed_mps=0.18,
        recovery_default_spin_rad=3.141592653589793,
    )

    assert [command.kind for command in commands] == ['spin', 'backup']


def test_build_coverage_fill_goals_creates_boustrophedon_endpoints() -> None:
    # build coverage fill 목표 목록 creates boustrophedon endpoints 동작과 회귀 여부를 검증한다.
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
