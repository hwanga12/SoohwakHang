from agribot_control.environment_disease_rules import DiseaseSignal, EnvironmentSnapshot
from agribot_control.watering_decision import (
    WateringDecisionState,
    evaluate_watering_decision,
    format_watering_decision_log,
)


def test_low_soil_moisture_maps_to_auto_execute() -> None:
    decision = evaluate_watering_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=25.0,
            humidity=58.0,
            soil_moisture=18.0,
            light_level=14000.0,
        )
    )

    assert decision.state == WateringDecisionState.AUTO_EXECUTE.value
    assert decision.target_value == 900.0
    assert decision.source_rule == 'R-WATER-LOW-SOIL-AUTO'
    assert decision.auto_execute is True


def test_mid_soil_moisture_requires_approval() -> None:
    decision = evaluate_watering_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=24.0,
            humidity=60.0,
            soil_moisture=28.0,
            light_level=12000.0,
        )
    )

    assert decision.state == WateringDecisionState.REQUIRES_APPROVAL.value
    assert decision.target_value == 600.0
    assert decision.requires_approval is True
    assert decision.source_rule == 'R-WATER-MID-SOIL-REVIEW'


def test_humid_fungal_repeat_holds_watering() -> None:
    decision = evaluate_watering_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=27.0,
            humidity=83.0,
            soil_moisture=19.0,
            light_level=16000.0,
        ),
        DiseaseSignal(
            class_name='tomato_powdery_mildew',
            disease_name='토마토흰가루병',
            repeat_count=2,
            confidence=0.91,
        ),
    )

    assert decision.state == WateringDecisionState.HOLD.value
    assert decision.command_type == 'hold_watering'
    assert decision.source_rule == 'R-HOLD-WATER-HUMID-FUNGAL'


def test_normal_soil_creates_no_watering_action() -> None:
    decision = evaluate_watering_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=23.0,
            humidity=55.0,
            soil_moisture=41.0,
            light_level=11000.0,
        )
    )

    assert decision.state == WateringDecisionState.NO_ACTION.value
    assert decision.command_type == 'noop'
    assert decision.source_rule == 'R-WATER-NONE'


def test_log_formatter_exposes_reason_and_context() -> None:
    decision = evaluate_watering_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=27.0,
            humidity=83.0,
            soil_moisture=19.0,
            light_level=16000.0,
        ),
        DiseaseSignal(
            class_name='tomato_gray_mold',
            disease_name='토마토잿빛곰팡이병',
            repeat_count=2,
            confidence=0.81,
        ),
    )

    log_line = format_watering_decision_log(decision)

    assert 'state=HOLD' in log_line
    assert 'rule=R-HOLD-WATER-HUMID-FUNGAL' in log_line
    assert 'disease=tomato_gray_mold/토마토잿빛곰팡이병 x2' in log_line
