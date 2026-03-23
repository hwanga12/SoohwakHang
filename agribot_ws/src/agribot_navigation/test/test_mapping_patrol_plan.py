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
    assert len(plan.default_patrol_sequence) == 19

    xs = [waypoint.pose.x for waypoint in plan.waypoints.values()]
    ys = [waypoint.pose.y for waypoint in plan.waypoints.values()]
    assert min(xs) >= -9.1
    assert max(xs) <= 9.1
    assert min(ys) >= -9.1
    assert max(ys) <= 9.1
