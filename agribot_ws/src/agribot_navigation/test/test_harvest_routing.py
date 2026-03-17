from pathlib import Path

from agribot_navigation.harvest_routing import compute_harvest_route, load_crop_catalog
from agribot_navigation.patrol_config import load_patrol_plan
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


def test_compute_harvest_route_prefers_lane_specific_approach_pose() -> None:
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'gh01_plant_09_tomato_01',
    )

    assert route_plan.route_id == 'greenhouse_01_right_bed_southbound'
    assert route_plan.inspect_waypoint_id == 'greenhouse_01_right_rear_inspect'
    assert route_plan.return_mode == 'resume_patrol'
    assert route_plan.return_waypoint_id == 'greenhouse_01_right_rear_inspect'
    assert route_plan.approach_pose.x == pytest.approx(15.3179)
    assert route_plan.approach_pose.y == pytest.approx(166.456497)
    assert route_plan.approach_pose.yaw == pytest.approx(0.0)


def test_compute_harvest_route_can_force_home_return() -> None:
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'gh01_plant_01_tomato_01',
        return_mode='home',
    )

    assert route_plan.route_id == 'greenhouse_01_left_bed_northbound'
    assert route_plan.return_waypoint_id == patrol_plan.home_pose_id
    assert route_plan.fallback_return_waypoint_id == patrol_plan.home_pose_id
    assert route_plan.approach_pose.x == pytest.approx(-11.9595)
    assert route_plan.approach_pose.y == pytest.approx(12.0)
    assert route_plan.approach_pose.yaw == pytest.approx(3.1416)


def test_compute_harvest_route_uses_preferred_return_waypoint_when_resuming() -> None:
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'gh01_plant_04_tomato_01',
        preferred_return_waypoint_id='greenhouse_01_rear_connector',
    )

    assert route_plan.return_waypoint_id == 'greenhouse_01_rear_connector'
    assert route_plan.fallback_return_waypoint_id == patrol_plan.home_pose_id
