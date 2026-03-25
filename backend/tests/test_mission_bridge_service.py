from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from mission_bridge_service import (  # noqa: E402
    MissionBridgeConflictError,
    publish_harvest_target_mission,
    publish_patrol_start_mission,
    read_mission_status_payload,
)
from robot_runtime_state_service import (  # noqa: E402
    mission_request_file_path,
    mission_status_file_path,
    mission_status_record_file_path,
)


@pytest.fixture(autouse=True)
def runtime_dir_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGRIBOT_RUNTIME_DIR", str(tmp_path))
    yield


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_publish_patrol_start_mission_writes_runtime_request_contract() -> None:
    response = publish_patrol_start_mission(
        robot_id="AGR-02",
        zone_ids=["farm_01_west", "farm_01_center"],
        loop_count=2,
        requested_by="frontend-operator",
        patrol_mode="diagnosis",
        mission_id="mission-patrol-001",
    )

    request_payload = json.loads(mission_request_file_path().read_text(encoding="utf-8"))

    assert response["accepted"] is True
    assert response["mission_id"] == "mission-patrol-001"
    assert response["request_type"] == "start_patrol"
    assert response["status_endpoint"] == "/api/v1/missions/mission-patrol-001"
    assert request_payload["command_id"] == "mission-patrol-001"
    assert request_payload["zone_ids"] == ["farm_01_west", "farm_01_center"]
    assert request_payload["loop_count"] == 2
    assert request_payload["patrol_mode"] == "diagnosis"


def test_publish_harvest_target_mission_writes_plant_and_fruit_ids() -> None:
    response = publish_harvest_target_mission(
        robot_id="AGR-02",
        plant_id="farm01_plant_03",
        fruit_id="farm01_plant_03_tomato_01",
        requested_by="frontend-operator",
        mission_id="mission-harvest-001",
    )

    request_payload = json.loads(mission_request_file_path().read_text(encoding="utf-8"))

    assert response["mission_id"] == "mission-harvest-001"
    assert response["request_type"] == "harvest_target"
    assert request_payload["plant_id"] == "farm01_plant_03"
    assert request_payload["fruit_id"] == "farm01_plant_03_tomato_01"
    assert request_payload["tomato_id"] == "farm01_plant_03_tomato_01"


def test_publish_operator_mission_rejects_when_latest_mission_is_running() -> None:
    _write_json(
        mission_status_file_path(),
        {
            "mission_id": "mission-live-001",
            "command_id": "mission-live-001",
            "request_type": "start_patrol",
            "robot_id": "AGR-02",
            "status": "running",
            "message": "순찰 실행 중입니다.",
            "updated_at": "2026-03-25T00:00:00+00:00",
        },
    )

    with pytest.raises(MissionBridgeConflictError, match="완료되지 않은 operator mission"):
        publish_patrol_start_mission(
            robot_id="AGR-02",
            zone_ids=["farm_01_west"],
            loop_count=1,
            requested_by="frontend-operator",
            patrol_mode="diagnosis",
        )


def test_read_mission_status_payload_prefers_mission_record_file() -> None:
    _write_json(
        mission_status_record_file_path("mission-harvest-002"),
        {
            "mission_id": "mission-harvest-002",
            "command_id": "mission-harvest-002",
            "request_type": "harvest_target",
            "robot_id": "AGR-02",
            "requested_by": "frontend-operator",
            "status": "succeeded",
            "message": "Harvest route completed.",
            "plant_id": "farm01_plant_03",
            "fruit_id": "farm01_plant_03_tomato_01",
            "tomato_id": "farm01_plant_03_tomato_01",
            "updated_at": "2026-03-25T00:00:01+00:00",
        },
    )

    payload = read_mission_status_payload("mission-harvest-002")

    assert payload["mission_id"] == "mission-harvest-002"
    assert payload["status"] == "succeeded"
    assert payload["fruit_id"] == "farm01_plant_03_tomato_01"
