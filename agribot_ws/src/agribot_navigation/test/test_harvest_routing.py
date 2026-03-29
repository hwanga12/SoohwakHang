import math
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


def test_farm_harvest_metadata_covers_all_grid_targets() -> None:
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


def test_compute_harvest_route_uses_generic_approach_pose_for_rectangular_farm() -> None:
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
