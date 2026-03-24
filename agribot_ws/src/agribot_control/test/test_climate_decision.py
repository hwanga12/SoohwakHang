from agribot_control.climate_decision import (
    DeviceDecisionState,
    evaluate_curtain_decision,
    evaluate_fan_decision,
    format_device_decision_log,
)
from agribot_control.environment_disease_rules import DiseaseSignal, EnvironmentSnapshot


def test_hot_and_bright_environment_closes_curtain_strongly() -> None:
    decision = evaluate_curtain_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=33.0,
            humidity=61.0,
            soil_moisture=40.0,
            light_level=38000.0,
        )
    )

    assert decision.state == DeviceDecisionState.AUTO_EXECUTE.value
    assert decision.command_type == 'set_curtain_position'
    assert decision.target_value == 60.0
    assert decision.source_rule == 'R-CURTAIN-HOT-BRIGHT-STRONG'


def test_moderate_hot_bright_environment_closes_curtain_partially() -> None:
    decision = evaluate_curtain_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=29.5,
            humidity=58.0,
            soil_moisture=36.0,
            light_level=27000.0,
        )
    )

    assert decision.state == DeviceDecisionState.AUTO_EXECUTE.value
    assert decision.target_value == 35.0
    assert decision.source_rule == 'R-CURTAIN-HOT-BRIGHT-MODERATE'


def test_curtain_no_action_when_conditions_are_normal() -> None:
    decision = evaluate_curtain_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=24.0,
            humidity=55.0,
            soil_moisture=36.0,
            light_level=14000.0,
        )
    )

    assert decision.state == DeviceDecisionState.NO_ACTION.value
    assert decision.command_type == 'noop'
    assert decision.source_rule == 'R-CURTAIN-NONE'


def test_hot_humid_environment_selects_fan_level_two() -> None:
    decision = evaluate_fan_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=31.0,
            humidity=78.0,
            soil_moisture=33.0,
            light_level=17000.0,
        )
    )

    assert decision.state == DeviceDecisionState.AUTO_EXECUTE.value
    assert decision.command_type == 'set_fan_level'
    assert decision.target_value == 2.0
    assert decision.source_rule == 'R-FAN-HOT-HUMID'


def test_humid_fungal_repeat_selects_fan_level_three() -> None:
    decision = evaluate_fan_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=27.0,
            humidity=84.0,
            soil_moisture=24.0,
            light_level=17000.0,
        ),
        DiseaseSignal(
            class_name='tomato_gray_mold',
            disease_name='토마토잿빛곰팡이병',
            repeat_count=2,
            confidence=0.82,
        ),
    )

    assert decision.state == DeviceDecisionState.AUTO_EXECUTE.value
    assert decision.target_value == 3.0
    assert decision.source_rule == 'R-FAN-HUMID-FUNGAL'


def test_fan_no_action_when_conditions_are_normal() -> None:
    decision = evaluate_fan_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=24.0,
            humidity=58.0,
            soil_moisture=35.0,
            light_level=13000.0,
        )
    )

    assert decision.state == DeviceDecisionState.NO_ACTION.value
    assert decision.command_type == 'noop'
    assert decision.source_rule == 'R-FAN-NONE'


def test_device_log_formatter_exposes_rule_and_context() -> None:
    decision = evaluate_fan_decision(
        EnvironmentSnapshot(
            zone_id='farm_01',
            temperature=27.0,
            humidity=84.0,
            soil_moisture=24.0,
            light_level=17000.0,
        ),
        DiseaseSignal(
            class_name='tomato_powdery_mildew',
            disease_name='토마토흰가루병',
            repeat_count=2,
            confidence=0.91,
        ),
    )

    log_line = format_device_decision_log(decision)

    assert 'Fan decision:' in log_line
    assert 'rule=R-FAN-HUMID-FUNGAL' in log_line
    assert 'disease=tomato_powdery_mildew/토마토흰가루병 x2' in log_line
