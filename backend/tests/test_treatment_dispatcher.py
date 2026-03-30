from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.actuation.dispatcher import TreatmentCommandDispatcher
from services.actuation.rule_engine import DiseaseTreatmentRuleEngine
from services.actuation.schemas import Point3D


def test_dispatcher_skips_no_action_plan() -> None:
    engine = DiseaseTreatmentRuleEngine()
    dispatcher = TreatmentCommandDispatcher()

    plan = engine.evaluate(
        disease_label='tomato_gray_mold',
        zone_id='farm_01',
        target_position=Point3D(x=4.0, y=3.0, z=0.05),
    )
    result = dispatcher.dispatch_plan(plan, observation_id='obs-noop')

    assert result.dispatched is False
    assert result.status == 'no_action'


def test_dispatcher_reports_successful_ros_publish(monkeypatch) -> None:
    engine = DiseaseTreatmentRuleEngine()
    dispatcher = TreatmentCommandDispatcher()

    monkeypatch.setattr(dispatcher, '_validate_runtime', lambda *args, **kwargs: None)

    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout='published', stderr='')

    monkeypatch.setattr('services.actuation.dispatcher.subprocess.run', _fake_run)

    plan = engine.evaluate(
        disease_label='tomato_powdery_mildew',
        zone_id='farm_01',
        target_position=Point3D(x=8.0, y=2.0, z=0.05),
    )
    result = dispatcher.dispatch_plan(
        plan,
        observation_id='obs-dispatch',
        requested_by='test:dispatcher',
    )

    assert result.dispatched is True
    assert result.status == 'dispatched'
    assert result.command_id == 'obs-dispatch'
    assert result.device_id == 'sprinkler_3'
    assert result.topic == '/iot/commands/dispatch'


def test_dispatcher_reports_successful_manual_ros_publish(monkeypatch) -> None:
    dispatcher = TreatmentCommandDispatcher()

    monkeypatch.setattr(dispatcher, '_validate_runtime', lambda *args, **kwargs: None)

    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout='manual-published', stderr='')

    monkeypatch.setattr('services.actuation.dispatcher.subprocess.run', _fake_run)

    result = dispatcher.dispatch_manual_command(
        command_id='manual-001',
        zone_id='farm_01',
        device_id='sprinkler_1',
        device_type='sprinkler',
        command_type='spray_water',
        target_value=3.0,
        unit='sec',
        requested_by='test:manual-dispatch',
        reason='manual payload=effect_color=blue',
    )

    assert result.dispatched is True
    assert result.status == 'dispatched'
    assert result.command_id == 'manual-001'
    assert result.device_id == 'sprinkler_1'
    assert result.topic == '/iot/commands/dispatch'
