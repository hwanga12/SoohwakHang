# 이 테스트는 로봇 모델과 시뮬레이션 자산 패키지의 sim time guard 동작을 검증한다.
import os
from pathlib import Path

import pytest

from agribot_description.sim_time_guard import (
    MonotonicStampFilter,
    SingletonLockError,
    acquire_singleton_lock,
    nanoseconds_to_stamp_fields,
    normalized_state_stamp_ns,
    stamp_to_nanoseconds,
)


def test_stamp_to_nanoseconds_combines_sec_and_nanosec() -> None:
    # stamp TO nanoseconds combines SEC AND nanosec 동작과 회귀 여부를 검증한다.
    assert stamp_to_nanoseconds(3, 25) == 3_000_000_025


def test_nanoseconds_to_stamp_fields_splits_sec_and_nanosec() -> None:
    # nanoseconds TO stamp fields splits SEC AND nanosec 동작과 회귀 여부를 검증한다.
    assert nanoseconds_to_stamp_fields(3_000_000_025) == (3, 25)


def test_monotonic_stamp_filter_accepts_only_strictly_increasing_stamps() -> None:
    # monotonic stamp filter accepts only strictly increasing stamps 동작과 회귀 여부를 검증한다.
    filter_state = MonotonicStampFilter()

    assert filter_state.accept(100) is True
    assert filter_state.accept(101) is True
    assert filter_state.accept(101) is False
    assert filter_state.accept(99) is False
    assert filter_state.last_stamp_ns == 101


def test_normalized_state_stamp_uses_latest_clock_when_state_lags() -> None:
    # normalized 상태 stamp uses latest clock when 상태 lags 동작과 회귀 여부를 검증한다.
    assert normalized_state_stamp_ns(
        source_stamp_ns=5_000_000_000,
        latest_clock_stamp_ns=7_000_000_000,
        last_published_stamp_ns=None,
    ) == 7_000_000_000


def test_normalized_state_stamp_stays_strictly_increasing() -> None:
    # normalized 상태 stamp stays strictly increasing 동작과 회귀 여부를 검증한다.
    assert normalized_state_stamp_ns(
        source_stamp_ns=7_000_000_000,
        latest_clock_stamp_ns=7_000_000_000,
        last_published_stamp_ns=7_000_000_000,
    ) == 7_000_000_001


def test_acquire_singleton_lock_rejects_duplicate_owner(tmp_path: Path) -> None:
    # acquire singleton lock rejects duplicate owner 동작과 회귀 여부를 검증한다.
    lock_path = tmp_path / 'sim_time_guard.lock'
    first_lock_fd = acquire_singleton_lock(lock_path)

    try:
        with pytest.raises(SingletonLockError):
            acquire_singleton_lock(lock_path)
    finally:
        os.close(first_lock_fd)
