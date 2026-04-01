# 이 테스트는 자율주행과 경로 계획 패키지의 harvest runtime store 동작을 검증한다.
from pathlib import Path

from agribot_navigation.harvest_runtime_store import (
    harvest_action_status_path,
    harvest_basket_state_path,
    harvest_event_record_path,
    harvest_failure_alert_path,
    harvest_latest_event_path,
    reset_harvest_runtime_session,
)


def test_reset_harvest_runtime_session_clears_runtime_files(tmp_path: Path) -> None:
    # reset harvest 런타임 데이터 session clears 런타임 데이터 files 동작과 회귀 여부를 검증한다.
    harvest_basket_state_path(tmp_path).write_text("{}", encoding="utf-8")
    harvest_latest_event_path(tmp_path).write_text("{}", encoding="utf-8")
    harvest_action_status_path(tmp_path).write_text("{}", encoding="utf-8")
    harvest_failure_alert_path(tmp_path).write_text("{}", encoding="utf-8")
    event_record_path = harvest_event_record_path("event-001", tmp_path)
    event_record_path.parent.mkdir(parents=True, exist_ok=True)
    event_record_path.write_text("{}", encoding="utf-8")

    reset_harvest_runtime_session(tmp_path)

    assert not harvest_basket_state_path(tmp_path).exists()
    assert not harvest_latest_event_path(tmp_path).exists()
    assert not harvest_action_status_path(tmp_path).exists()
    assert not harvest_failure_alert_path(tmp_path).exists()
    assert not (tmp_path / "harvest_events").exists()
    assert not (tmp_path / "harvest_action_statuses").exists()
