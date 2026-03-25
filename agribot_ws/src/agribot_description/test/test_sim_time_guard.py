from agribot_description.sim_time_guard import MonotonicStampFilter, stamp_to_nanoseconds


def test_stamp_to_nanoseconds_combines_sec_and_nanosec() -> None:
    assert stamp_to_nanoseconds(3, 25) == 3_000_000_025


def test_monotonic_stamp_filter_accepts_only_strictly_increasing_stamps() -> None:
    filter_state = MonotonicStampFilter()

    assert filter_state.accept(100) is True
    assert filter_state.accept(101) is True
    assert filter_state.accept(101) is False
    assert filter_state.accept(99) is False
    assert filter_state.last_stamp_ns == 101
