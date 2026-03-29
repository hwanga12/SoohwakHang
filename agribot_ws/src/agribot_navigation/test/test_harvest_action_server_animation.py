"""수확 액션 서버가 Gazebo 시각 상태를 올바르게 되돌리고 참조 pose를 고르는지 검증한다."""

from types import SimpleNamespace

from agribot_navigation.harvest_action_server import HarvestActionServerNode
from agribot_navigation.harvest_routing import HarvestRoutePlan
from agribot_navigation.patrol_config import Pose2D


def _build_route_plan() -> HarvestRoutePlan:
    pose = Pose2D(x=-6.75, y=-6.0, z=0.0, yaw=0.0)
    align_pose = Pose2D(x=-7.45, y=-6.0, z=0.0, yaw=0.0)
    return HarvestRoutePlan(
        tomato_id='farm01_plant_01_tomato_01',
        plant_id='farm01_plant_01',
        route_id='farm_01_harvest_lane_01',
        lane_side='harvest_lane_01',
        inspect_waypoint_id='farm_01_lane_01_inspect_01',
        inspect_waypoint_name='Harvest Aisle 01 Inspect 01',
        approach_pose=pose,
        align_pose=align_pose,
        return_mode='resume_patrol',
        return_waypoint_id='farm_01_lane_01_inspect_01',
        fallback_return_waypoint_id='farm_01_home',
        fallback_return_mode='home',
    )


def test_resolve_animation_reference_pose_prefers_latest_robot_pose() -> None:
    node = object.__new__(HarvestActionServerNode)
    node._latest_robot_pose = Pose2D(x=1.0, y=2.0, z=0.0, yaw=0.5)

    resolved = HarvestActionServerNode._resolve_animation_reference_pose(
        node,
        _build_route_plan(),
    )

    assert resolved == node._latest_robot_pose


def test_approach_navigation_pose_prefers_inspect_waypoint_pose() -> None:
    node = object.__new__(HarvestActionServerNode)
    inspect_pose = Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708)
    node._plan = SimpleNamespace(
        waypoints={
            'farm_01_lane_01_inspect_01': SimpleNamespace(pose=inspect_pose),
        }
    )

    resolved = HarvestActionServerNode._approach_navigation_pose(
        node,
        _build_route_plan(),
    )

    assert resolved == inspect_pose


def test_reset_visual_harvest_state_restores_arm_and_tomato_pose() -> None:
    node = object.__new__(HarvestActionServerNode)
    published_positions: list[float] = []
    pose_updates: list[tuple[str, object]] = []
    node._harvest_arm_ready_position = 0.0
    node._catalog = SimpleNamespace(
        tomatoes={
            'farm01_plant_01_tomato_01': SimpleNamespace(
                world_model_name='farm01_plant_01_tomato_01',
                pose=Pose2D(x=-6.0, y=-6.0, z=0.82, yaw=0.0),
            )
        }
    )
    node._publish_arm_position = published_positions.append
    node._set_gazebo_entity_pose = lambda entity_name, pose: pose_updates.append((entity_name, pose))
    node._normalize_request_text = HarvestActionServerNode._normalize_request_text.__get__(
        node,
        HarvestActionServerNode,
    )

    HarvestActionServerNode._reset_visual_harvest_state(
        node,
        'farm01_plant_01_tomato_01',
    )

    assert published_positions == [0.0]
    assert len(pose_updates) == 1
    assert pose_updates[0][0] == 'farm01_plant_01_tomato_01'
    assert pose_updates[0][1].x == -6.0
    assert pose_updates[0][1].y == -6.0
    assert pose_updates[0][1].z == 0.82
