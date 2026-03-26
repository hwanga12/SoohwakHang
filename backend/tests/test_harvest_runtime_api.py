from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from robot_runtime_state_service import (  # noqa: E402
    harvest_action_status_file_path,
    harvest_action_status_record_file_path,
    harvest_basket_state_file_path,
    harvest_event_record_file_path,
    harvest_latest_event_file_path,
    mission_status_record_file_path,
)
from routers import harvests, missions  # noqa: E402


@pytest.fixture(autouse=True)
def runtime_dir_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGRIBOT_RUNTIME_DIR", str(tmp_path))
    yield


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_harvest_routes_return_runtime_event_and_basket_state() -> None:
    event_payload = {
        "event_id": "harvest-event-001",
        "mission_id": "mission-harvest-001",
        "zone_id": "farm_01",
        "plant_id": "farm01_plant_03",
        "fruit_id": "farm01_plant_03_tomato_01",
        "success": True,
        "status": "succeeded",
        "failure_reason": "",
        "basket_count": 3,
        "frame_id": "map",
        "stamp": {"sec": 10, "nanosec": 20},
        "occurred_at": "2026-03-26T10:00:00+00:00",
    }
    basket_payload = {
        "zone_id": "farm_01",
        "basket_count": 3,
        "harvested_count": 3,
        "remaining_ready_count": 21,
        "last_event_id": "harvest-event-001",
        "last_harvested_fruit_id": "farm01_plant_03_tomato_01",
        "loaded_fruit_ids": [
            "farm01_plant_01_tomato_01",
            "farm01_plant_02_tomato_01",
            "farm01_plant_03_tomato_01",
        ],
        "frame_id": "map",
        "stamp": {"sec": 11, "nanosec": 22},
        "updated_at": "2026-03-26T10:00:05+00:00",
    }
    action_status_payload = {
        "mission_id": "mission-harvest-001",
        "mission_type": "HARVEST",
        "state": "RUNNING",
        "status": "running",
        "current_phase": "STOWING",
        "zone_id": "farm_01",
        "target_id": "farm01_plant_03_tomato_01",
        "progress_pct": 95.0,
        "retry_count": 0,
        "detail_message": "Loading farm01_plant_03_tomato_01 into the basket.",
        "frame_id": "map",
        "stamp": {"sec": 12, "nanosec": 23},
        "updated_at": "2026-03-26T10:00:06+00:00",
    }

    _write_json(harvest_event_record_file_path("harvest-event-001"), event_payload)
    _write_json(harvest_latest_event_file_path(), event_payload)
    _write_json(harvest_basket_state_file_path(), basket_payload)
    _write_json(harvest_action_status_file_path(), action_status_payload)
    _write_json(
        harvest_action_status_record_file_path("mission-harvest-001"),
        action_status_payload,
    )

    history_payload = harvests.get_harvests()["data"]
    assert history_payload[0]["mission_id"] == "mission-harvest-001"
    assert history_payload[0]["state"] == "진행 중"
    assert history_payload[0]["current_phase"] == "STOWING"
    assert any(item["id"] == "harvest-event-001" for item in history_payload)

    stats_payload = harvests.get_harvest_stats()["data"]
    assert stats_payload["basket_count"] == 3
    assert stats_payload["remaining_ready_count"] == 21
    assert stats_payload["last_harvested_fruit_id"] == "farm01_plant_03_tomato_01"
    assert stats_payload["mission_status"] == "running"
    assert stats_payload["current_phase"] == "STOWING"
    assert stats_payload["basket_state"].startswith("바구니 적재 3개")


def test_mission_status_endpoint_overlays_harvest_action_phase() -> None:
    _write_json(
        mission_status_record_file_path("mission-harvest-002"),
        {
            "mission_id": "mission-harvest-002",
            "command_id": "mission-harvest-002",
            "request_type": "harvest_target",
            "robot_id": "AGR-02",
            "requested_by": "frontend-operator",
            "status": "running",
            "message": "미션은 실행 중이지만 세부 phase는 아직 비어 있습니다.",
            "fruit_id": "farm01_plant_05_tomato_01",
            "plant_id": "farm01_plant_05",
            "received_at": "2026-03-26T10:10:00+00:00",
            "updated_at": "2026-03-26T10:10:01+00:00",
        },
    )
    _write_json(
        harvest_action_status_record_file_path("mission-harvest-002"),
        {
            "mission_id": "mission-harvest-002",
            "mission_type": "HARVEST",
            "state": "RUNNING",
            "status": "running",
            "current_phase": "APPROACHING",
            "zone_id": "farm_01",
            "target_id": "farm01_plant_05_tomato_01",
            "progress_pct": 35.0,
            "retry_count": 1,
            "detail_message": "Approaching farm01_plant_05_tomato_01 for harvest.",
            "frame_id": "map",
            "stamp": {"sec": 20, "nanosec": 30},
            "updated_at": "2026-03-26T10:10:05+00:00",
        },
    )

    payload = missions.get_mission_status("mission-harvest-002")["data"]

    assert payload["mission_id"] == "mission-harvest-002"
    assert payload["status"] == "running"
    assert payload["current_phase"] == "APPROACHING"
    assert payload["progress_pct"] == 35.0
    assert payload["retry_count"] == 1
    assert payload["message"] == "Approaching farm01_plant_05_tomato_01 for harvest."
    assert payload["fruit_id"] == "farm01_plant_05_tomato_01"
