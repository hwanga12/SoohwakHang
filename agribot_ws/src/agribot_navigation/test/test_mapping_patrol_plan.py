from pathlib import Path

from agribot_navigation.patrol_config import load_patrol_plan


def test_farm_mapping_patrol_plan_stays_within_rectangular_world_bounds() -> None:
    plan_path = (
        Path(__file__).resolve().parents[1]
        / 'config'
        / 'farm_mapping_patrol_waypoints.yaml'
    )

    plan = load_patrol_plan(plan_path)

    assert plan.zone_id == 'farm_01'
    assert plan.home_pose_id == 'farm_01_home'
    assert len(plan.default_patrol_sequence) == 22

    xs = [waypoint.pose.x for waypoint in plan.waypoints.values()]
    ys = [waypoint.pose.y for waypoint in plan.waypoints.values()]
    assert min(xs) >= -8.7
    assert max(xs) <= 8.7
    assert min(ys) >= -9.1
    assert max(ys) <= 9.1


def test_farm_mapping_patrol_plan_starts_from_spawn_aligned_center_sweep() -> None:
    plan_path = (
        Path(__file__).resolve().parents[1]
        / 'config'
        / 'farm_mapping_patrol_waypoints.yaml'
    )

    plan = load_patrol_plan(plan_path)

    home_waypoint = plan.waypoints[plan.home_pose_id]
    assert home_waypoint.pose.x == 0.0
    assert home_waypoint.pose.y == 0.0
    assert plan.waypoints['farm_01_lane_05_north'].pose.x == 8.6
    assert plan.waypoints['farm_01_lane_05_north'].pose.y == 0.0
    assert plan.default_patrol_sequence[:4] == (
        'farm_01_home',
        'farm_01_lane_05_north',
        'farm_01_lane_06_north',
        'farm_01_lane_06_south',
    )
