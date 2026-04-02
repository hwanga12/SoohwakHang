from agribot_control.actuation_request_planner import (
    RequestRoute,
    plan_actuation_requests,
    request_signature,
)
from agribot_control.environment_disease_rules import DiseaseSignal, EnvironmentSnapshot


def test_low_soil_moisture_publishes_auto_watering_request() -> None:
    plans = plan_actuation_requests(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=24.0,
            humidity=58.0,
            soil_moisture=18.0,
            light_level=12000.0,
        ),
        requested_by='mission_manager:auto',
    )

    watering = next(plan for plan in plans if plan.device_type == 'watering')
    assert watering.route == RequestRoute.AUTO.value
    assert watering.command_type == 'dispense_water'
    assert watering.auto_execute is True
    assert watering.requires_approval is False
    assert watering.device_id == 'farm_01_watering'


def test_mid_soil_moisture_creates_review_request() -> None:
    plans = plan_actuation_requests(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=24.0,
            humidity=60.0,
            soil_moisture=28.0,
            light_level=12000.0,
        ),
        requested_by='mission_manager:auto',
    )

    watering = next(plan for plan in plans if plan.device_type == 'watering')
    assert watering.route == RequestRoute.REVIEW.value
    assert watering.requires_approval is True
    assert watering.auto_execute is False


def test_humid_fungal_risk_skips_actionable_requests() -> None:
    plans = plan_actuation_requests(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=27.0,
            humidity=84.0,
            soil_moisture=20.0,
            light_level=16000.0,
        ),
        DiseaseSignal(
            class_name='tomato_gray_mold',
            disease_name='토마토잿빛곰팡이병',
            repeat_count=2,
            confidence=0.81,
        ),
        requested_by='mission_manager:auto',
    )

    assert plans == []


def test_calcium_disorder_creates_review_nutrient_request_with_payload_in_reason() -> None:
    plans = plan_actuation_requests(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=25.0,
            humidity=61.0,
            soil_moisture=37.0,
            light_level=14000.0,
        ),
        DiseaseSignal(
            class_name='blossom_end_rot',
            disease_name='토마토 배꼽썩음 증상',
            growth_stage='flowering_fruiting_stage',
            confidence=0.77,
        ),
        requested_by='mission_manager:auto',
    )

    nutrient = next(plan for plan in plans if plan.device_type == 'nutrient')
    assert nutrient.route == RequestRoute.REVIEW.value
    assert nutrient.reason.endswith('payload=nutrient_type=calcium_boost')


def test_request_signature_changes_when_route_changes() -> None:
    auto_plan = plan_actuation_requests(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=24.0,
            humidity=58.0,
            soil_moisture=18.0,
            light_level=12000.0,
        ),
        requested_by='mission_manager:auto',
    )[0]
    review_plan = plan_actuation_requests(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=24.0,
            humidity=60.0,
            soil_moisture=28.0,
            light_level=12000.0,
        ),
        requested_by='mission_manager:auto',
    )[0]

    assert request_signature(auto_plan) != request_signature(review_plan)
