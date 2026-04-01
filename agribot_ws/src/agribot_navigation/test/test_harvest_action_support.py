# 이 테스트는 자율주행과 경로 계획 패키지의 harvest action support 동작을 검증한다.
from pathlib import Path
import json

from agribot_interfaces.msg import HarvestBasketState, HarvestEvent, MissionStatus
from dataclasses import replace

from agribot_navigation.harvest_action_support import (
    PHASE_PROGRESS_PCT,
    alignment_required,
    build_basket_state,
    build_basket_state_payload,
    build_feedback,
    build_failure_alert_payload,
    build_harvest_event,
    build_harvest_event_payload,
    build_mission_status,
    build_mission_status_payload,
    build_result,
    ensure_harvest_target_available,
    resolve_harvest_goal,
    should_retry_phase,
)
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


def test_resolve_harvest_goal_defaults_mission_and_zone() -> None:
    # resolve harvest 목표 defaults 미션 AND 구역 동작과 회귀 여부를 검증한다.
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    resolved = resolve_harvest_goal(
        mission_id='',
        zone_id='',
        plant_id='',
        fruit_id='farm01_plant_01_tomato_01',
        approach_waypoint_id='farm_01_lane_01_inspect_01',
        default_zone_id='farm_01',
        catalog=crop_catalog,
    )

    assert resolved.mission_id.startswith('harvest-')
    assert resolved.zone_id == 'farm_01'
    assert resolved.plant_id == 'farm01_plant_01'
    assert resolved.tomato_id == 'farm01_plant_01_tomato_01'
    assert resolved.preferred_approach_waypoint_id == 'farm_01_lane_01_inspect_01'


def test_resolve_harvest_goal_accepts_none_for_optional_strings() -> None:
    # resolve harvest 목표 accepts none FOR optional strings 동작과 회귀 여부를 검증한다.
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    resolved = resolve_harvest_goal(
        mission_id=None,
        zone_id='farm_01',
        plant_id=None,
        fruit_id='farm01_plant_01_tomato_01',
        approach_waypoint_id=None,
        default_zone_id='farm_01',
        catalog=crop_catalog,
    )

    assert resolved.plant_id == 'farm01_plant_01'
    assert resolved.preferred_approach_waypoint_id == ''


def test_resolve_harvest_goal_treats_string_none_as_empty() -> None:
    # resolve harvest 목표 treats string none AS empty 동작과 회귀 여부를 검증한다.
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    resolved = resolve_harvest_goal(
        mission_id='None',
        zone_id='farm_01',
        plant_id='None',
        fruit_id='farm01_plant_01_tomato_01',
        approach_waypoint_id='null',
        default_zone_id='farm_01',
        catalog=crop_catalog,
    )

    assert resolved.mission_id.startswith('harvest-')
    assert resolved.plant_id == 'farm01_plant_01'
    assert resolved.preferred_approach_waypoint_id == ''


def test_resolve_harvest_goal_rejects_mismatched_plant() -> None:
    # resolve harvest 목표 rejects mismatched 작물 개체 동작과 회귀 여부를 검증한다.
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    with pytest.raises(ValueError, match='belongs to plant'):
        resolve_harvest_goal(
            mission_id='mission-01',
            zone_id='farm_01',
            plant_id='farm01_plant_09',
            fruit_id='farm01_plant_01_tomato_01',
            approach_waypoint_id='',
            default_zone_id='farm_01',
            catalog=crop_catalog,
        )


def test_ensure_harvest_target_available_rejects_duplicate_runtime_target() -> None:
    # ensure harvest target 사용 가능 상태 rejects duplicate 런타임 데이터 target 동작과 회귀 여부를 검증한다.
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    with pytest.raises(ValueError, match='already harvested'):
        ensure_harvest_target_available(
            catalog=crop_catalog,
            tomato_id='farm01_plant_01_tomato_01',
            harvested_tomato_ids={'farm01_plant_01_tomato_01'},
        )


def test_alignment_required_reflects_approach_and_align_difference() -> None:
    # alignment required reflects approach AND align difference 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)
    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_01_tomato_01',
    )

    assert alignment_required(route_plan) is False

    adjusted_route_plan = replace(
        route_plan,
        align_pose=Pose2D(
            x=route_plan.approach_pose.x,
            y=route_plan.approach_pose.y + 0.4,
            z=route_plan.approach_pose.z,
            yaw=route_plan.approach_pose.yaw,
        ),
    )

    assert alignment_required(adjusted_route_plan) is True


def test_build_feedback_and_result_match_action_contract() -> None:
    # build feedback AND 결과 match action 계약 동작과 회귀 여부를 검증한다.
    feedback = build_feedback(
        current_phase='VERIFYING',
        progress_pct=PHASE_PROGRESS_PCT['VERIFYING'],
        aligned_to_target=True,
        gripper_engaged=True,
    )
    result = build_result(
        success=True,
        harvest_event_id='harvest-event-01',
        basket_count=3,
        message='Harvest completed.',
    )

    assert feedback.current_phase == 'VERIFYING'
    assert feedback.progress_pct == pytest.approx(85.0)
    assert feedback.aligned_to_target is True
    assert feedback.gripper_engaged is True
    assert result.success is True
    assert result.harvest_event_id == 'harvest-event-01'
    assert result.basket_count == 3


def test_build_harvest_event_populates_message_fields() -> None:
    # build harvest 이벤트 populates message fields 동작과 회귀 여부를 검증한다.
    event = build_harvest_event(
        event_id='harvest-event-42',
        mission_id='mission-42',
        zone_id='farm_01',
        plant_id='farm01_plant_01',
        fruit_id='farm01_plant_01_tomato_01',
        frame_id='odom',
        basket_count=1,
        success=False,
        failure_reason='verification failed',
    )

    assert isinstance(event, HarvestEvent)
    assert event.event_id == 'harvest-event-42'
    assert event.header.frame_id == 'odom'
    assert event.success is False
    assert event.failure_reason == 'verification failed'
    assert event.basket_count == 1


def test_build_basket_state_tracks_loaded_fruits_and_remaining_count() -> None:
    # build basket 상태 tracks loaded fruits AND remaining count 동작과 회귀 여부를 검증한다.
    basket_state = build_basket_state(
        zone_id='farm_01',
        frame_id='odom',
        basket_count=2,
        harvested_count=2,
        remaining_ready_count=70,
        last_event_id='harvest-event-02',
        last_harvested_fruit_id='farm01_plant_02_tomato_01',
        loaded_fruit_ids=[
            'farm01_plant_01_tomato_01',
            'farm01_plant_02_tomato_01',
        ],
    )

    assert isinstance(basket_state, HarvestBasketState)
    assert basket_state.zone_id == 'farm_01'
    assert basket_state.header.frame_id == 'odom'
    assert basket_state.basket_count == 2
    assert basket_state.harvested_count == 2
    assert basket_state.remaining_ready_count == 70
    assert basket_state.last_event_id == 'harvest-event-02'
    assert basket_state.last_harvested_fruit_id == 'farm01_plant_02_tomato_01'
    assert basket_state.loaded_fruit_ids == [
        'farm01_plant_01_tomato_01',
        'farm01_plant_02_tomato_01',
    ]


def test_runtime_payload_helpers_keep_event_basket_and_phase_fields() -> None:
    # 런타임 데이터 payload helpers keep 이벤트 basket AND 단계 fields 동작과 회귀 여부를 검증한다.
    event = build_harvest_event(
        event_id='harvest-event-55',
        mission_id='mission-55',
        zone_id='farm_01',
        plant_id='farm01_plant_05',
        fruit_id='farm01_plant_05_tomato_01',
        frame_id='map',
        basket_count=4,
        success=True,
    )
    event.header.stamp.sec = 10
    event.header.stamp.nanosec = 20

    basket_state = build_basket_state(
        zone_id='farm_01',
        frame_id='map',
        basket_count=4,
        harvested_count=4,
        remaining_ready_count=18,
        last_event_id='harvest-event-55',
        last_harvested_fruit_id='farm01_plant_05_tomato_01',
        loaded_fruit_ids=['farm01_plant_05_tomato_01'],
    )
    basket_state.header.stamp.sec = 11
    basket_state.header.stamp.nanosec = 22

    mission_status = build_mission_status(
        mission_id='mission-55',
        mission_type='HARVEST',
        state='RUNNING',
        current_phase='STOWING',
        zone_id='farm_01',
        target_id='farm01_plant_05_tomato_01',
        progress_pct=95.0,
        detail_message='Loading fruit into the basket.',
        retry_count=0,
    )
    mission_status.header.stamp.sec = 12
    mission_status.header.stamp.nanosec = 23

    event_payload = build_harvest_event_payload(event, occurred_at='2026-03-26T09:00:00+00:00')
    basket_payload = build_basket_state_payload(basket_state, updated_at='2026-03-26T09:00:01+00:00')
    mission_payload = build_mission_status_payload(mission_status, updated_at='2026-03-26T09:00:02+00:00')

    assert event_payload['status'] == 'succeeded'
    assert event_payload['stamp'] == {'sec': 10, 'nanosec': 20}
    assert basket_payload['last_harvested_fruit_id'] == 'farm01_plant_05_tomato_01'
    assert basket_payload['loaded_fruit_ids'] == ['farm01_plant_05_tomato_01']
    assert mission_payload['status'] == 'running'
    assert mission_payload['current_phase'] == 'STOWING'
    assert mission_payload['progress_pct'] == pytest.approx(95.0)


def test_build_mission_status_captures_return_home_progress() -> None:
    # build 미션 상태 captures return home progress 동작과 회귀 여부를 검증한다.
    mission_status = build_mission_status(
        mission_id='mission-455',
        mission_type='HARVEST',
        state='RUNNING',
        current_phase='RETURN_HOME',
        zone_id='farm_01',
        target_id='farm_01_home',
        progress_pct=PHASE_PROGRESS_PCT['RETURN_HOME'],
        detail_message='Returning to home pose after harvest.',
        retry_count=1,
    )

    assert isinstance(mission_status, MissionStatus)
    assert mission_status.mission_id == 'mission-455'
    assert mission_status.mission_type == 'HARVEST'
    assert mission_status.state == 'RUNNING'
    assert mission_status.current_phase == 'RETURN_HOME'
    assert mission_status.zone_id == 'farm_01'
    assert mission_status.target_id == 'farm_01_home'
    assert mission_status.progress_pct == pytest.approx(98.0)
    assert mission_status.retry_count == 1
    assert mission_status.detail_message == 'Returning to home pose after harvest.'


def test_should_retry_phase_respects_allowlist_and_limit() -> None:
    # should retry 단계 respects allowlist AND limit 동작과 회귀 여부를 검증한다.
    retryable_phases = {'APPROACHING', 'RETURN_HOME', 'RESUME'}

    assert should_retry_phase(
        current_phase='APPROACHING',
        retryable_phases=retryable_phases,
        retry_count=0,
        retry_limit=1,
    ) is True
    assert should_retry_phase(
        current_phase='APPROACHING',
        retryable_phases=retryable_phases,
        retry_count=1,
        retry_limit=1,
    ) is False
    assert should_retry_phase(
        current_phase='VERIFYING',
        retryable_phases=retryable_phases,
        retry_count=0,
        retry_limit=2,
    ) is False


def test_build_failure_alert_payload_marks_safe_stop_and_failure_reason() -> None:
    # build failure alert payload marks safe stop AND failure reason 동작과 회귀 여부를 검증한다.
    payload = build_failure_alert_payload(
        mission_id='mission-456',
        zone_id='farm_01',
        fruit_id='farm01_plant_01_tomato_01',
        current_phase='APPROACHING',
        failure_reason='NavigateToPose action server not available.',
        retry_count=2,
        safety_stop_requested=True,
        safety_stop_completed=True,
        harvest_completed=False,
    )
    decoded = json.loads(payload)

    assert decoded['alert_type'] == 'HARVEST_FAILURE'
    assert decoded['severity'] == 'ERROR'
    assert decoded['mission_id'] == 'mission-456'
    assert decoded['zone_id'] == 'farm_01'
    assert decoded['fruit_id'] == 'farm01_plant_01_tomato_01'
    assert decoded['current_phase'] == 'APPROACHING'
    assert decoded['retry_count'] == 2
    assert decoded['safety_stop_requested'] is True
    assert decoded['safety_stop_completed'] is True
    assert decoded['harvest_completed'] is False
    assert decoded['failure_reason'] == 'NavigateToPose action server not available.'
