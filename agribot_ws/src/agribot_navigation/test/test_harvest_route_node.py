"""수확 route 노드의 복구 분기와 pose 비교 규칙이 의도대로 동작하는지 검증한다."""

from types import SimpleNamespace

from agribot_navigation.harvest_route_node import (
    HarvestRouteNode,
    _poses_are_effectively_same,
)
from agribot_navigation.harvest_routing import HarvestRoutePlan
from agribot_navigation.patrol_config import Pose2D, Waypoint


class _StaticFuture:
    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value


def _build_route_plan(*, approach_pose: Pose2D) -> HarvestRoutePlan:
    return HarvestRoutePlan(
        tomato_id='farm01_plant_01_tomato_01',
        plant_id='farm01_plant_01',
        route_id='farm_01_harvest_lane_01',
        lane_side='harvest_lane_01',
        inspect_waypoint_id='farm_01_lane_01_inspect_01',
        inspect_waypoint_name='Harvest Aisle 01 Inspect 01',
        approach_pose=approach_pose,
        align_pose=approach_pose,
        return_mode='resume_patrol',
        return_waypoint_id='farm_01_lane_01_inspect_01',
        fallback_return_waypoint_id='farm_01_home',
        fallback_return_mode='home',
    )


def _build_waypoint(*, pose: Pose2D) -> Waypoint:
    return Waypoint(
        waypoint_id='farm_01_lane_01_inspect_01',
        display_name='Harvest Aisle 01 Inspect 01',
        purpose='inspect',
        description='inspect',
        pose=pose,
        lane_id='harvest_lane_01',
        batchable=False,
        observe_here=True,
        observed_plant_ids=('farm01_plant_01',),
        observed_tomato_ids=('farm01_plant_01_tomato_01',),
    )


def _build_node_for_recovery(
    *,
    approach_pose: Pose2D,
    inspect_pose: Pose2D,
    inspect_waypoint_fallback_enabled: bool = True,
    demo_recovery_enabled: bool = True,
):
    node = object.__new__(HarvestRouteNode)
    warnings: list[str] = []
    node._active_plan = _build_route_plan(approach_pose=approach_pose)
    node._plan = SimpleNamespace(waypoints={'farm_01_lane_01_inspect_01': _build_waypoint(pose=inspect_pose)})
    node._harvest_inspect_waypoint_fallback_enabled = inspect_waypoint_fallback_enabled
    node._harvest_demo_recovery_enabled = demo_recovery_enabled
    node._using_inspect_waypoint_approach = False
    node._using_demo_harvest_recovery = False
    node.get_logger = lambda: SimpleNamespace(warning=warnings.append)
    return node, warnings


def test_poses_are_effectively_same_uses_distance_and_yaw_tolerance() -> None:
    base_pose = Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708)

    assert _poses_are_effectively_same(
        base_pose,
        Pose2D(x=-8.02, y=-5.99, z=0.0, yaw=1.58),
    )
    assert not _poses_are_effectively_same(
        base_pose,
        Pose2D(x=-7.6, y=-6.0, z=0.0, yaw=1.5708),
    )


def test_recover_from_failed_approach_retries_inspect_waypoint_first() -> None:
    node, warnings = _build_node_for_recovery(
        approach_pose=Pose2D(x=-6.75, y=-6.0, z=0.0, yaw=0.0),
        inspect_pose=Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708),
    )
    retried = {'called': False}
    node._start_approach_navigation = lambda: retried.__setitem__('called', True)
    node._start_harvest_dwell = lambda: (_ for _ in ()).throw(AssertionError('demo fallback should not run'))

    recovered = HarvestRouteNode._recover_from_failed_approach(
        node,
        'approaching navigation failed. (error_code=104)',
    )

    assert recovered is True
    assert node._using_inspect_waypoint_approach is True
    assert node._using_demo_harvest_recovery is False
    assert retried['called'] is True
    assert warnings


def test_recover_from_failed_approach_falls_back_to_demo_when_retry_is_not_available() -> None:
    node, warnings = _build_node_for_recovery(
        approach_pose=Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708),
        inspect_pose=Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708),
    )
    dwell = {'called': False}
    node._start_approach_navigation = lambda: (_ for _ in ()).throw(AssertionError('inspect retry should not run'))
    node._start_harvest_dwell = lambda: dwell.__setitem__('called', True)

    recovered = HarvestRouteNode._recover_from_failed_approach(
        node,
        'approaching navigation failed. (error_code=104)',
    )

    assert recovered is True
    assert node._using_inspect_waypoint_approach is False
    assert node._using_demo_harvest_recovery is True
    assert dwell['called'] is True
    assert warnings


def test_recover_from_failed_alignment_continues_with_demo_harvest() -> None:
    node, warnings = _build_node_for_recovery(
        approach_pose=Pose2D(x=-6.75, y=-6.0, z=0.0, yaw=0.0),
        inspect_pose=Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708),
    )
    settle = {'called': False}
    node._start_alignment_settle = lambda: settle.__setitem__('called', True)

    recovered = HarvestRouteNode._recover_from_failed_alignment(
        node,
        'aligning navigation failed. (error_code=104)',
    )

    assert recovered is True
    assert node._using_demo_harvest_recovery is True
    assert settle['called'] is True
    assert warnings


def test_handle_goal_response_recovers_from_rejected_approach_goal() -> None:
    node, warnings = _build_node_for_recovery(
        approach_pose=Pose2D(x=-6.75, y=-6.0, z=0.0, yaw=0.0),
        inspect_pose=Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708),
    )
    errors: list[str] = []
    node._goal_send_future = object()
    node._active_goal_handle = None
    node._goal_result_future = None
    node._used_return_fallback = False
    node._set_error = errors.append
    node._start_return_navigation = lambda use_fallback: (_ for _ in ()).throw(
        AssertionError('return fallback should not run for approach rejection')
    )
    retried = {'called': False}
    node._start_approach_navigation = lambda: retried.__setitem__('called', True)
    node._start_harvest_dwell = lambda: (_ for _ in ()).throw(
        AssertionError('demo harvest fallback should not run on first inspect retry')
    )

    HarvestRouteNode._handle_goal_response(
        node,
        _StaticFuture(SimpleNamespace(accepted=False)),
        'approaching',
    )

    assert retried['called'] is True
    assert errors == []
    assert warnings


def test_handle_goal_response_uses_fallback_return_waypoint_when_return_goal_is_rejected() -> None:
    node, warnings = _build_node_for_recovery(
        approach_pose=Pose2D(x=-6.75, y=-6.0, z=0.0, yaw=0.0),
        inspect_pose=Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708),
    )
    errors: list[str] = []
    fallback_calls: list[bool] = []
    node._goal_send_future = object()
    node._active_goal_handle = None
    node._goal_result_future = None
    node._used_return_fallback = False
    node._set_error = errors.append
    node._start_return_navigation = lambda use_fallback: fallback_calls.append(use_fallback)

    HarvestRouteNode._handle_goal_response(
        node,
        _StaticFuture(SimpleNamespace(accepted=False)),
        'returning',
    )

    assert fallback_calls == [True]
    assert errors == []
    assert warnings
