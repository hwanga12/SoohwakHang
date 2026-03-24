from pathlib import Path

from agribot_interfaces.msg import HarvestBasketState, HarvestEvent
from agribot_navigation.harvest_action_support import (
    PHASE_PROGRESS_PCT,
    alignment_required,
    build_basket_state,
    build_feedback,
    build_harvest_event,
    build_result,
    ensure_harvest_target_available,
    resolve_harvest_goal,
)
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


def test_resolve_harvest_goal_defaults_mission_and_zone() -> None:
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
    crop_catalog = load_crop_catalog(CROP_INSTANCES)

    with pytest.raises(ValueError, match='already harvested'):
        ensure_harvest_target_available(
            catalog=crop_catalog,
            tomato_id='farm01_plant_01_tomato_01',
            harvested_tomato_ids={'farm01_plant_01_tomato_01'},
        )


def test_alignment_required_reflects_approach_and_align_difference() -> None:
    patrol_plan = load_patrol_plan(PATROL_WAYPOINTS)
    crop_catalog = load_crop_catalog(CROP_INSTANCES)
    route_plan = compute_harvest_route(
        patrol_plan,
        crop_catalog,
        'farm01_plant_01_tomato_01',
    )

    assert alignment_required(route_plan) is True


def test_build_feedback_and_result_match_action_contract() -> None:
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
