from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agribot_perception.crop_targeting import CropTargetResolver


def test_lookup_returns_requested_plant() -> None:
    resolver = CropTargetResolver(zone_id='farm_01')

    target = resolver.lookup('farm01_plant_10')

    assert target is not None
    assert target.plant_id == 'farm01_plant_10'
    assert target.fruit_id == 'farm01_plant_10_tomato_01'
    assert target.position.x == -2.0
    assert target.position.y == -2.0
    assert target.position.z == 1.05


def test_pose_resolution_prefers_front_facing_target() -> None:
    resolver = CropTargetResolver(
        zone_id='farm_01',
        max_distance_m=2.0,
        max_bearing_deg=55.0,
    )

    target = resolver.resolve(
        robot_x=-3.35,
        robot_y=-2.0,
        robot_yaw=0.0,
    )

    assert target is not None
    assert target.plant_id == 'farm01_plant_10'
    assert target.fruit_id == 'farm01_plant_10_tomato_01'
