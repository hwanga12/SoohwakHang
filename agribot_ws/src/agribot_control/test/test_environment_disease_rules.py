from agribot_control.environment_disease_rules import (
    DecisionType,
    DiseaseSignal,
    EnvironmentSnapshot,
    evaluate_environment_disease_rules,
)


def test_dry_soil_recommends_auto_watering() -> None:
    decisions = evaluate_environment_disease_rules(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=24.0,
            humidity=58.0,
            soil_moisture=18.0,
            light_level=12000.0,
        )
    )

    watering = next(
        decision for decision in decisions if decision.device_type == 'watering'
    )
    assert watering.decision_type == DecisionType.RECOMMEND.value
    assert watering.command_type == 'dispense_water'
    assert watering.target_value == 900.0
    assert watering.auto_execute is True


def test_hot_and_bright_environment_recommends_curtain() -> None:
    decisions = evaluate_environment_disease_rules(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=33.0,
            humidity=60.0,
            soil_moisture=42.0,
            light_level=38000.0,
        )
    )

    curtain = next(
        decision for decision in decisions if decision.device_type == 'curtain'
    )
    assert curtain.command_type == 'set_curtain_position'
    assert curtain.target_value == 60.0
    assert curtain.auto_execute is True


def test_humid_fungal_repeat_holds_watering_and_enables_fan() -> None:
    decisions = evaluate_environment_disease_rules(
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
    )

    assert any(
        decision.device_type == 'watering'
        and decision.decision_type == DecisionType.HOLD.value
        for decision in decisions
    )
    fan = next(decision for decision in decisions if decision.device_type == 'fan')
    assert fan.target_value == 3.0
    assert fan.auto_execute is True
    assert all(
        not (
            decision.device_type == 'watering'
            and decision.decision_type == DecisionType.RECOMMEND.value
        )
        for decision in decisions
    )


def test_fruiting_calcium_disorder_recommends_nutrients_with_approval() -> None:
    decisions = evaluate_environment_disease_rules(
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
    )

    nutrient = next(
        decision for decision in decisions if decision.device_type == 'nutrient'
    )
    assert nutrient.command_payload == {'nutrient_type': 'calcium_boost'}
    assert nutrient.requires_approval is True
    assert nutrient.auto_execute is False
