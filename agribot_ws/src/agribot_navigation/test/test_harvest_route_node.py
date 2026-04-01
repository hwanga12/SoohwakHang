# 이 테스트는 자율주행과 경로 계획 패키지의 harvest route node 동작을 검증한다.
from types import SimpleNamespace

from agribot_navigation.harvest_simulation import HarvestAnimationConfig
from agribot_navigation.harvest_route_node import (
    HarvestRouteNode,
    _poses_are_effectively_same,
)
from agribot_navigation.harvest_routing import HarvestRoutePlan
from agribot_navigation.patrol_config import Pose2D, Waypoint


class _StaticFuture:
    # static 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    def __init__(self, value):
        # _StaticFuture 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        self._value = value

    def result(self):
        # 결과 정보를 계산해 반환한다.
        return self._value


def _build_route_plan(*, approach_pose: Pose2D) -> HarvestRoutePlan:
    # 경로 계획를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
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
    # waypoint를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
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
    navigation_target_mode: str = 'approach_pose',
):
    # node FOR recovery를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    node = object.__new__(HarvestRouteNode)
    warnings: list[str] = []
    node._active_plan = _build_route_plan(approach_pose=approach_pose)
    node._plan = SimpleNamespace(waypoints={'farm_01_lane_01_inspect_01': _build_waypoint(pose=inspect_pose)})
    node._harvest_inspect_waypoint_fallback_enabled = inspect_waypoint_fallback_enabled
    node._harvest_demo_recovery_enabled = demo_recovery_enabled
    node._harvest_navigation_target_mode = navigation_target_mode
    node._harvest_goal_soft_tolerance_m = 0.4
    node._using_inspect_waypoint_approach = False
    node._using_demo_harvest_recovery = False
    node._latest_robot_pose = None
    node.get_logger = lambda: SimpleNamespace(warning=warnings.append, info=warnings.append)
    return node, warnings


def test_poses_are_effectively_same_uses_distance_and_yaw_tolerance() -> None:
    # 위치 자세 목록 ARE effectively same uses distance AND YAW tolerance 동작과 회귀 여부를 검증한다.
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
    # recover from failed approach retries inspect waypoint first 동작과 회귀 여부를 검증한다.
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
    # recover from failed approach falls back TO demo when retry IS NOT 사용 가능 상태 동작과 회귀 여부를 검증한다.
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
    # recover from failed alignment continues with demo harvest 동작과 회귀 여부를 검증한다.
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
    # handle 목표 응답 데이터 recovers from rejected approach 목표 동작과 회귀 여부를 검증한다.
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
    # handle 목표 응답 데이터 uses fallback return waypoint when return 목표 IS rejected 동작과 회귀 여부를 검증한다.
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


def test_finish_harvest_dwell_stages_basket_slot_preview_when_slot_is_available() -> None:
    # finish harvest dwell stages basket slot 미리보기 데이터 when slot IS 사용 가능 상태 동작과 회귀 여부를 검증한다.
    node = object.__new__(HarvestRouteNode)
    published_positions: list[float] = []
    return_calls: list[bool] = []
    sync_forces: list[bool] = []
    node._cancel_harvest_timer = lambda: None
    node._publish_arm_position = published_positions.append
    node._harvest_arm_ready_position = 0.0
    node._loaded_tomato_ids = []
    node._animation_config = HarvestAnimationConfig(basket_slot_count=2)
    node._finalize_harvested_tomato_visual = lambda: True
    node._sync_basket_visual_slots = lambda *, force=False: sync_forces.append(force)
    node._start_return_navigation = lambda use_fallback: return_calls.append(use_fallback)

    HarvestRouteNode._finish_harvest_dwell(node)

    assert published_positions == [0.0]
    assert node._basket_visual_preview_count == 1
    assert sync_forces == [True]
    assert return_calls == [False]


def test_finalize_harvested_tomato_visual_always_hides_actual_harvested_tomato() -> None:
    # finalize harvested tomato visual always hides actual harvested tomato 동작과 회귀 여부를 검증한다.
    node = object.__new__(HarvestRouteNode)
    hidden = {'called': False}
    node._hide_harvested_tomato_visual = lambda: hidden.__setitem__('called', True) or True

    finalized = HarvestRouteNode._finalize_harvested_tomato_visual(node)

    assert finalized is True
    assert hidden['called'] is True


def test_sync_basket_visual_slots_publishes_visible_and_hidden_joint_positions() -> None:
    # sync basket visual slots publishes visible AND hidden joint 위치 목록 동작과 회귀 여부를 검증한다.
    node = object.__new__(HarvestRouteNode)
    published_slot_01: list[float] = []
    published_slot_02: list[float] = []
    node._basket_visual_slot_publishers = [
        SimpleNamespace(publish=lambda msg: published_slot_01.append(msg.data)),
        SimpleNamespace(publish=lambda msg: published_slot_02.append(msg.data)),
    ]
    node._basket_visual_slot_hidden_position = 0.0
    node._basket_visual_slot_visible_position = 0.255
    node._basket_visual_preview_count = 1
    node._loaded_tomato_ids = []
    node._basket_visual_last_visible_count = -1

    HarvestRouteNode._sync_basket_visual_slots(node)

    assert published_slot_01 == [0.255]
    assert published_slot_02 == [0.0]
    assert node._basket_visual_last_visible_count == 1


def test_start_approach_navigation_uses_safe_inspect_waypoint_target_in_default_mode() -> None:
    # start approach navigation uses safe inspect waypoint target IN default 모드 동작과 회귀 여부를 검증한다.
    inspect_pose = Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708)
    node, _ = _build_node_for_recovery(
        approach_pose=Pose2D(x=-6.75, y=-6.0, z=0.0, yaw=0.0),
        inspect_pose=inspect_pose,
        navigation_target_mode='inspect_waypoint',
    )
    started: list[tuple[Pose2D, str, str]] = []
    node._start_navigation = lambda pose, *, phase, message: started.append((pose, phase, message))

    HarvestRouteNode._start_approach_navigation(node)

    assert len(started) == 1
    pose, phase, message = started[0]
    assert pose == inspect_pose
    assert phase == 'approaching'
    assert 'safe harvest observation waypoint' in message


def test_start_return_navigation_finishes_immediately_when_robot_is_already_near_target() -> None:
    # start return navigation finishes immediately when robot IS already near target 동작과 회귀 여부를 검증한다.
    inspect_pose = Pose2D(x=-8.0, y=-6.0, z=0.0, yaw=1.5708)
    node, _ = _build_node_for_recovery(
        approach_pose=Pose2D(x=-6.75, y=-6.0, z=0.0, yaw=0.0),
        inspect_pose=inspect_pose,
        navigation_target_mode='inspect_waypoint',
    )
    node._latest_robot_pose = Pose2D(x=-8.05, y=-6.02, z=0.0, yaw=1.5708)
    node._start_navigation = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError('return navigation should be skipped when already near the target')
    )
    finished = {'called': False}
    node._finish_sequence_after_return = lambda: finished.__setitem__('called', True)

    HarvestRouteNode._start_return_navigation(node, use_fallback=False)

    assert finished['called'] is True


def test_continue_harvest_to_basket_fails_when_visual_update_is_rejected() -> None:
    # continue harvest TO basket fails when visual update IS rejected 동작과 회귀 여부를 검증한다.
    node = object.__new__(HarvestRouteNode)
    node._cancel_harvest_timer = lambda: None
    node._active_plan = SimpleNamespace(tomato_id='farm01_plant_01_tomato_01')
    node._catalog = SimpleNamespace(
        tomatoes={
            'farm01_plant_01_tomato_01': SimpleNamespace(
                world_model_name='farm01_plant_01_tomato_01',
                pose=Pose2D(x=-6.0, y=-6.0, z=0.82, yaw=0.0),
            )
        }
    )
    node._completed_tomato_ids = []
    node._animation_config = HarvestAnimationConfig()
    node._harvest_arm_ready_position = 0.0
    node._harvest_stow_sec = 1.2
    errors: list[str] = []
    scheduled: list[tuple[float, object]] = []
    published_positions: list[float] = []
    node._resolve_animation_reference_pose = lambda: Pose2D(x=0.0, y=0.0, z=0.0, yaw=0.0)
    node._set_gazebo_entity_pose = lambda entity_name, pose: False
    node._set_error = errors.append
    node._schedule_harvest_timer = lambda duration_sec, callback: scheduled.append((duration_sec, callback))
    node._publish_arm_position = published_positions.append
    node._set_state = lambda state, message: None
    node._publish_execution_status = lambda **kwargs: None

    HarvestRouteNode._continue_harvest_to_basket(node)

    assert published_positions == []
    assert scheduled == []
    assert errors == [
        '토마토를 뒤 바구니 슬롯으로 옮기는 연출을 Gazebo에 반영하지 못했습니다. '
        '(farm01_plant_01_tomato_01, stage=basket)'
    ]


def test_finish_harvest_dwell_stops_when_hiding_visual_fails() -> None:
    # finish harvest dwell stops when hiding visual fails 동작과 회귀 여부를 검증한다.
    node = object.__new__(HarvestRouteNode)
    published_positions: list[float] = []
    return_calls: list[bool] = []
    node._cancel_harvest_timer = lambda: None
    node._publish_arm_position = published_positions.append
    node._harvest_arm_ready_position = 0.0
    node._finalize_harvested_tomato_visual = lambda: False
    node._start_return_navigation = lambda use_fallback: return_calls.append(use_fallback)

    HarvestRouteNode._finish_harvest_dwell(node)

    assert published_positions == [0.0]
    assert return_calls == []
