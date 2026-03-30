from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from robot_command_bridge_service import (  # noqa: E402
    RobotCommandValidationError,
    command_file_path,
    publish_robot_command,
    read_latest_command_status_payload,
)
from robot_runtime_state_service import control_state_file_path  # noqa: E402
from zone_service import read_zones_payload, resolve_zone_representative_pose  # noqa: E402


@pytest.fixture(autouse=True)
def runtime_dir_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGRIBOT_RUNTIME_DIR", str(tmp_path))
    yield


def test_read_zones_payload_returns_real_zone_catalog() -> None:
    zones = read_zones_payload()

    assert [zone["id"] for zone in zones] == [
        "farm_01_west",
        "farm_01_center",
        "farm_01_east",
    ]
    assert zones[0]["representative_waypoint_id"] == "farm_01_lane_01_south_entry"
    assert zones[1]["representative_pose"]["frame_id"] == "map"
    assert zones[2]["plant_count"] > 0


def test_resolve_zone_representative_pose_uses_patrol_waypoint_pose() -> None:
    pose = resolve_zone_representative_pose("farm_01_east")

    assert pose["frame_id"] == "map"
    assert pose["x"] == 8.0
    assert pose["y"] == -8.6


def test_publish_move_to_zone_resolves_to_navigate_to_pose_bridge() -> None:
    response = publish_robot_command(
        robot_id="AGR-02",
        command_type="move_to_zone",
        requested_by="frontend-operator",
        target_zone_id="farm_01_center",
    )

    assert response["accepted"] is True
    assert response["requested_command_type"] == "move_to_zone"
    assert response["command_type"] == "navigate_to_pose"
    assert response["target_zone"]["id"] == "farm_01_center"
    assert response["preempt_current_navigation"] is True

    command_payload = json.loads(command_file_path().read_text(encoding="utf-8"))
    assert command_payload["command_type"] == "navigate_to_pose"
    assert command_payload["requested_command_type"] == "move_to_zone"
    assert command_payload["preempt_current_navigation"] is True
    assert command_payload["payload"]["target_pose"]["frame_id"] == "map"


def test_publish_navigate_to_pose_rejects_non_map_frame() -> None:
    with pytest.raises(RobotCommandValidationError, match="frame_id 는 map 만 허용"):
        publish_robot_command(
            robot_id="AGR-02",
            command_type="navigate_to_pose",
            requested_by="frontend-operator",
            target_pose={
                "x": 0.0,
                "y": -8.6,
                "yaw": 1.5708,
                "frame_id": "odom",
            },
        )


def test_publish_navigate_to_pose_allows_explicit_preempt_override() -> None:
    response = publish_robot_command(
        robot_id="AGR-02",
        command_type="navigate_to_pose",
        requested_by="frontend-operator",
        preempt_current_navigation=False,
        target_pose={
            "x": 0.0,
            "y": -8.6,
            "yaw": 1.5708,
            "frame_id": "map",
        },
    )

    assert response["preempt_current_navigation"] is False

    command_payload = json.loads(command_file_path().read_text(encoding="utf-8"))
    assert command_payload["preempt_current_navigation"] is False


def test_publish_pause_patrol_defaults_preempt_to_false() -> None:
    control_state_file_path().write_text(
        json.dumps(
            {
                "mode": "normal",
                "is_latched": False,
                "active_activity": "patrol",
                "message": "순찰 중입니다.",
                "resume_available": False,
                "resume_context": None,
                "updated_at": "2026-03-25T00:00:00+00:00",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    response = publish_robot_command(
        robot_id="AGR-02",
        command_type="pause_patrol",
        requested_by="frontend-operator",
    )

    assert response["preempt_current_navigation"] is False

    command_payload = json.loads(command_file_path().read_text(encoding="utf-8"))
    assert command_payload["preempt_current_navigation"] is False


def test_read_latest_command_status_payload_returns_idle_when_missing() -> None:
    payload = read_latest_command_status_payload()

    assert payload["available"] is False
    assert payload["status"] == "idle"
