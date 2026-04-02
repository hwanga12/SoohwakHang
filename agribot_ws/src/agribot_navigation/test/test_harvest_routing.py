# 이 테스트는 자율주행과 경로 계획 패키지의 harvest routing 동작을 검증한다.
import math
from pathlib import Path

from agribot_navigation.harvest_routing import compute_harvest_route, load_crop_catalog
from agribot_navigation.patrol_config import Pose2D, load_patrol_plan
import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
PATROL_WAYPOINTS = (
    REPO_ROOT
    / 'agribot_ws'
    / 'src'
    / 'agribot_navigation'
    / 'config'
    / 'patrol_waypoints.yaml'
)
CROP_INSTANCES = (
    REPO_ROOT
    / 'agribot_ws'
    / 'src'
    / 'agribot_description'
    / 'config'
    / 'crop_instances.yaml'
)


def test_farm_harvest_metadata_covers_all_grid_targets() -> None:
    # farm harvest metadata covers ALL grid targets 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    observed_tomato_ids = set()
    for waypoint in patrol_plan.waypoints.values():
        observed_tomato_ids.update(waypoint.observed_tomato_ids)

    assert patrol_plan.zone_id == 'farm_01'
    assert crop_catalog.zone_id == 'farm_01'
    assert len(crop_catalog.plants) == 24
    assert len(crop_catalog.tomatoes) == 24
    assert len(patrol_plan.routes) == 5
    assert 'farm_01_harvest_lane_center' in patrol_plan.routes
    assert observed_tomato_ids == set(crop_catalog.tomatoes)


def test_all_tomatoes_have_two_observation_candidates() -> None:
    # ALL tomatoes have TWO 관측 결과 candidates 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    candidates_by_tomato: dict[str, set[str]] = {
        tomato_id: set() for tomato_id in crop_catalog.tomatoes
    }
    for waypoint in patrol_plan.waypoints.values():
        if waypoint.purpose != 'inspect':
            continue
        for tomato_id in waypoint.observed_tomato_ids:
            if tomato_id in candidates_by_tomato:
                candidates_by_tomato[tomato_id].add(waypoint.waypoint_id)

    assert {tomato_id: len(candidates) for tomato_id, candidates in candidates_by_tomato.items()} == {
        tomato_id: 2 for tomato_id in crop_catalog.tomatoes
    }


def test_compute_harvest_route_uses_generic_approach_pose_for_rectangular_farm() -> None:
    # compute harvest 경로 uses generic approach 위치 자세 FOR rectangular farm 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_01_tomato_01',
    )

    assert route_plan.route_id == 'farm_01_harvest_lane_01'
    assert route_plan.inspect_waypoint_id == 'farm_01_lane_01_inspect_01'
    assert route_plan.return_mode == 'resume_patrol'
    assert route_plan.return_waypoint_id == 'farm_01_lane_01_inspect_01'
    assert route_plan.approach_pose.x == pytest.approx(-6.75, abs=1e-6)
    assert route_plan.approach_pose.y == pytest.approx(-6.0, abs=1e-6)
    assert route_plan.approach_pose.yaw == pytest.approx(0.0, abs=1e-6)
    # The current lane metadata caps lateral harvest motion at 1.25 m from the
    # inspect waypoint, so the align pose is clamped to the same safe corridor.
    assert route_plan.align_pose.x == pytest.approx(-6.75, abs=1e-6)
    assert route_plan.align_pose.y == pytest.approx(-6.0, abs=1e-6)
    assert route_plan.align_pose.yaw == pytest.approx(0.0, abs=1e-6)


def test_compute_harvest_route_can_force_home_return() -> None:
    # compute harvest 경로 CAN force home return 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_23_tomato_01',
        return_mode='home',
    )

    assert route_plan.route_id == 'farm_01_harvest_lane_03'
    assert route_plan.return_waypoint_id == patrol_plan.home_pose_id
    assert route_plan.fallback_return_waypoint_id == patrol_plan.home_pose_id
    assert route_plan.approach_pose.x == pytest.approx(2.75, abs=1e-6)
    assert route_plan.approach_pose.y == pytest.approx(6.0, abs=1e-6)
    assert route_plan.approach_pose.yaw == pytest.approx(math.pi, abs=1e-6)
    assert route_plan.align_pose.x == pytest.approx(2.75, abs=1e-6)
    assert route_plan.align_pose.y == pytest.approx(6.0, abs=1e-6)
    assert route_plan.align_pose.yaw == pytest.approx(math.pi, abs=1e-6)


def test_compute_harvest_route_prefers_current_inspect_waypoint_when_available() -> None:
    # compute harvest 경로 prefers current inspect waypoint when 사용 가능 상태 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_01_tomato_01',
        preferred_return_waypoint_id='farm_01_lane_02_inspect_06',
    )

    assert route_plan.route_id == 'farm_01_harvest_lane_02'
    assert route_plan.inspect_waypoint_id == 'farm_01_lane_02_inspect_06'
    assert route_plan.return_waypoint_id == 'farm_01_lane_02_inspect_06'
    assert route_plan.fallback_return_waypoint_id == patrol_plan.home_pose_id
    assert route_plan.approach_pose.x == pytest.approx(-5.25, abs=1e-6)
    assert route_plan.approach_pose.y == pytest.approx(-6.0, abs=1e-6)
    assert route_plan.approach_pose.yaw == pytest.approx(math.pi, abs=1e-6)
    assert route_plan.align_pose.x == pytest.approx(-5.25, abs=1e-6)
    assert route_plan.align_pose.y == pytest.approx(-6.0, abs=1e-6)
    assert route_plan.align_pose.yaw == pytest.approx(math.pi, abs=1e-6)


def test_compute_harvest_route_prefers_explicit_inspect_waypoint_override() -> None:
    # compute harvest 경로 prefers explicit inspect waypoint override 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_18_tomato_01',
        preferred_inspect_waypoint_id='farm_01_lane_center_inspect_05',
        current_pose=Pose2D(x=-4.0, y=4.0, z=0.0, yaw=0.0),
    )

    assert route_plan.route_id == 'farm_01_harvest_lane_center'
    assert route_plan.inspect_waypoint_id == 'farm_01_lane_center_inspect_05'
    assert route_plan.approach_pose.x == pytest.approx(0.0, abs=1e-6)
    assert route_plan.approach_pose.y == pytest.approx(4.0, abs=1e-6)


def test_compute_harvest_route_prefers_observation_candidate_closest_to_current_pose() -> None:
    # compute harvest 경로 prefers 관측 결과 candidate closest TO current 위치 자세 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_23_tomato_01',
        current_pose=Pose2D(x=0.0, y=0.0, z=0.0, yaw=0.0),
    )

    assert route_plan.route_id == 'farm_01_harvest_lane_center'
    assert route_plan.inspect_waypoint_id == 'farm_01_lane_center_inspect_06'
    assert route_plan.approach_pose.x == pytest.approx(0.0, abs=1e-6)
    assert route_plan.approach_pose.y == pytest.approx(6.0, abs=1e-6)
    assert route_plan.approach_pose.yaw == pytest.approx(0.0, abs=1e-6)
    assert route_plan.align_pose.x == pytest.approx(0.0, abs=1e-6)
    assert route_plan.align_pose.y == pytest.approx(6.0, abs=1e-6)
    assert route_plan.align_pose.yaw == pytest.approx(0.0, abs=1e-6)


def test_compute_harvest_route_keeps_center_lane_targets_on_safe_inspect_corridor() -> None:
    # compute harvest 경로 keeps center lane targets ON safe inspect corridor 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_11_tomato_01',
        current_pose=Pose2D(x=0.0, y=0.0, z=0.0, yaw=0.0),
    )

    assert route_plan.route_id == 'farm_01_harvest_lane_center'
    assert route_plan.inspect_waypoint_id == 'farm_01_lane_center_inspect_03'
    assert route_plan.approach_pose.x == pytest.approx(0.0, abs=1e-6)
    assert route_plan.approach_pose.y == pytest.approx(-2.0, abs=1e-6)
    assert route_plan.align_pose.x == pytest.approx(0.0, abs=1e-6)
    assert route_plan.align_pose.y == pytest.approx(-2.0, abs=1e-6)


def test_compute_harvest_route_switches_to_left_edge_candidate_when_robot_starts_left() -> None:
    # compute harvest 경로 switches TO left edge candidate when robot starts left 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_01_tomato_01',
        current_pose=Pose2D(x=-9.0, y=-6.0, z=0.0, yaw=0.0),
    )

    assert route_plan.route_id == 'farm_01_harvest_lane_01'
    assert route_plan.inspect_waypoint_id == 'farm_01_lane_01_inspect_01'


def test_compute_harvest_route_switches_to_right_edge_candidate_when_robot_starts_right() -> None:
    # compute harvest 경로 switches TO right edge candidate when robot starts right 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_24_tomato_01',
        current_pose=Pose2D(x=9.0, y=6.0, z=0.0, yaw=math.pi),
    )

    assert route_plan.route_id == 'farm_01_harvest_lane_04'
    assert route_plan.inspect_waypoint_id == 'farm_01_lane_04_inspect_01'
