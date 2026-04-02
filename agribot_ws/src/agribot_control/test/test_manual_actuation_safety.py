# 이 테스트는 상위 제어와 의사결정 패키지의 manual actuation safety 동작을 검증한다.
from agribot_control.manual_actuation_safety import (
    ActuationCommand,
    CommandSource,
    ManualPrioritySafetyLock,
)


def _build_command(
    *,
    source: str,
    device_type: str = 'watering',
    device_id: str = '',
    command_type: str = 'dispense_water',
    target_value: float = 900.0,
    requested_by: str = 'scheduler',
) -> ActuationCommand:
    # 명령를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return ActuationCommand(
        command_id='cmd-001',
        zone_id='farm_01',
        device_id=device_id,
        device_type=device_type,
        command_type=command_type,
        target_value=target_value,
        unit='ml' if device_type in {'watering', 'nutrient'} else 'level',
        requires_approval=False,
        auto_execute=True,
        requested_by=requested_by,
        reason='test command',
        source=source,
    )


def test_manual_command_blocks_auto_command_during_override_window() -> None:
    # manual 명령 blocks auto 명령 during override window 동작과 회귀 여부를 검증한다.
    guard = ManualPrioritySafetyLock(
        manual_override_seconds=15.0,
        duplicate_window_seconds=1.0,
        execution_lock_seconds=0.5,
        conflict_groups={'watering': 'irrigation', 'nutrient': 'irrigation'},
    )

    accepted = guard.evaluate(
        _build_command(source=CommandSource.MANUAL.value, requested_by='operator'),
        now_seconds=10.0,
    )
    blocked = guard.evaluate(
        _build_command(source=CommandSource.AUTO.value),
        now_seconds=11.0,
    )

    assert accepted.accepted is True
    assert blocked.accepted is False
    assert blocked.rule == 'R-SAFE-MANUAL-PRIORITY'


def test_duplicate_command_is_rejected_inside_duplicate_window() -> None:
    # duplicate 명령 IS rejected inside duplicate window 동작과 회귀 여부를 검증한다.
    guard = ManualPrioritySafetyLock(
        duplicate_window_seconds=2.0,
        execution_lock_seconds=0.0,
    )

    first = guard.evaluate(
        _build_command(source=CommandSource.AUTO.value),
        now_seconds=5.0,
    )
    duplicate = guard.evaluate(
        _build_command(source=CommandSource.AUTO.value),
        now_seconds=6.0,
    )

    assert first.accepted is True
    assert duplicate.accepted is False
    assert duplicate.rule == 'R-SAFE-DUPLICATE'


def test_same_device_is_locked_briefly_after_acceptance() -> None:
    # same 장치 IS locked briefly after acceptance 동작과 회귀 여부를 검증한다.
    guard = ManualPrioritySafetyLock(
        duplicate_window_seconds=0.0,
        execution_lock_seconds=4.0,
    )

    first = guard.evaluate(
        _build_command(source=CommandSource.AUTO.value),
        now_seconds=20.0,
    )
    second = guard.evaluate(
        _build_command(
            source=CommandSource.AUTO.value,
            command_type='dispense_water',
            target_value=600.0,
        ),
        now_seconds=21.0,
    )

    assert first.accepted is True
    assert second.accepted is False
    assert second.rule == 'R-SAFE-DEVICE-LOCK'


def test_conflicting_device_group_is_locked_briefly() -> None:
    # conflicting 장치 group IS locked briefly 동작과 회귀 여부를 검증한다.
    guard = ManualPrioritySafetyLock(
        duplicate_window_seconds=0.0,
        execution_lock_seconds=4.0,
        conflict_groups={'watering': 'irrigation', 'nutrient': 'irrigation'},
    )

    watering = guard.evaluate(
        _build_command(source=CommandSource.AUTO.value, device_type='watering'),
        now_seconds=30.0,
    )
    nutrient = guard.evaluate(
        _build_command(
            source=CommandSource.AUTO.value,
            device_type='nutrient',
            command_type='apply_nutrient_recipe',
            target_value=250.0,
        ),
        now_seconds=31.0,
    )

    assert watering.accepted is True
    assert nutrient.accepted is False
    assert nutrient.rule == 'R-SAFE-CONFLICT-LOCK'


def test_auto_command_is_allowed_after_override_and_locks_expire() -> None:
    # auto 명령 IS allowed after override AND locks expire 동작과 회귀 여부를 검증한다.
    guard = ManualPrioritySafetyLock(
        manual_override_seconds=5.0,
        duplicate_window_seconds=1.0,
        execution_lock_seconds=1.0,
    )

    manual = guard.evaluate(
        _build_command(source=CommandSource.MANUAL.value, requested_by='operator'),
        now_seconds=100.0,
    )
    auto = guard.evaluate(
        _build_command(source=CommandSource.AUTO.value),
        now_seconds=106.0,
    )

    assert manual.accepted is True
    assert auto.accepted is True
    assert auto.rule == 'R-SAFE-ACCEPT'
