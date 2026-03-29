from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from robot_command_bridge_service import (  # noqa: E402
    RobotCommandConflictError,
    command_file_path,
    publish_robot_command,
)
from robot_map_service import read_layers_payload, read_pose_payload, read_status_payload  # noqa: E402
from robot_runtime_state_service import (  # noqa: E402
    command_status_file_path,
    control_state_file_path,
    mission_request_file_path,
    mission_status_record_file_path,
    read_latest_command_status_payload,
)
from routers import missions, robots  # noqa: E402


@pytest.fixture(autouse=True)
def runtime_dir_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGRIBOT_RUNTIME_DIR", str(tmp_path))
    yield


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _control_state_payload(
    *,
    mode: str,
    active_activity: str,
    message: str,
    blocking_reason: str | None = None,
    resume_available: bool = False,
    resume_context: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "mode": mode,
        "is_latched": mode != "normal",
        "active_activity": active_activity,
        "blocking_reason": blocking_reason,
        "message": message,
        "resume_available": resume_available,
        "resume_context": resume_context,
        "updated_at": "2026-03-25T00:00:00+00:00",
    }


def test_publish_pause_alias_canonicalizes_and_separates_request_from_current_state() -> None:
    _write_json(
        control_state_file_path(),
        _control_state_payload(
            mode="normal",
            active_activity="manual_navigation",
            message="수동 이동 중입니다.",
        ),
    )

    response = publish_robot_command(
        robot_id="AGR-02",
        command_type="pause",
        requested_by="frontend-operator",
    )

    assert response["accepted"] is True
    assert response["request"]["status"] == "accepted"
    assert response["requested_command_type"] == "pause"
    assert response["command_type"] == "pause_motion"
    assert response["current_control_state"]["mode"] == "normal"

    command_payload = json.loads(command_file_path().read_text(encoding="utf-8"))
    assert command_payload["command_type"] == "pause_motion"
    assert command_payload["requested_command_type"] == "pause"


def test_publish_emergency_stop_rejects_when_already_latched() -> None:
    _write_json(
        control_state_file_path(),
        _control_state_payload(
            mode="emergency_stop",
            active_activity="idle",
            message="비상 정지가 이미 활성화되었습니다.",
            blocking_reason="emergency_stop",
        ),
    )

    with pytest.raises(RobotCommandConflictError, match="이미 비상 정지 상태"):
        publish_robot_command(
            robot_id="AGR-02",
            command_type="emergency_stop",
            requested_by="frontend-operator",
        )


def test_publish_resume_motion_rejects_without_latch() -> None:
    _write_json(
        control_state_file_path(),
        _control_state_payload(
            mode="normal",
            active_activity="idle",
            message="정상 제어 상태입니다.",
        ),
    )

    with pytest.raises(RobotCommandConflictError, match="제어 latch가 없습니다"):
        publish_robot_command(
            robot_id="AGR-02",
            command_type="resume",
            requested_by="frontend-operator",
        )


def test_latest_command_status_includes_control_state_fields() -> None:
    _write_json(
        control_state_file_path(),
        _control_state_payload(
            mode="paused",
            active_activity="manual_navigation",
            message="일시정지가 활성화되었습니다.",
            blocking_reason="pause_motion",
            resume_available=True,
            resume_context={
                "context_type": "manual_navigation",
                "captured_at": "2026-03-25T00:00:00+00:00",
                "command_id": "cmd-pause-01",
                "command_type": "navigate_to_pose",
                "target_pose": {
                    "x": 0.0,
                    "y": -8.6,
                    "yaw": 1.5708,
                    "frame_id": "map",
                },
            },
        ),
    )
    _write_json(
        command_file_path(),
        {
            "command_id": "cmd-pause-01",
            "command_type": "pause_motion",
            "requested_command_type": "pause",
            "robot_id": "AGR-02",
            "requested_by": "frontend-operator",
            "map_id": "farm_map",
            "preempt_current_navigation": False,
            "issued_at": "2026-03-25T00:00:01+00:00",
        },
    )
    _write_json(
        command_status_file_path(),
        {
            "command_id": "cmd-pause-01",
            "command_type": "pause_motion",
            "robot_id": "AGR-02",
            "status": "succeeded",
            "message": "일시정지가 활성화되었습니다.",
            "updated_at": "2026-03-25T00:00:02+00:00",
        },
    )

    payload = read_latest_command_status_payload()

    assert payload["requested_command_type"] == "pause"
    assert payload["control_mode"] == "paused"
    assert payload["control_resume_available"] is True
    assert payload["control_state"]["resume_context"]["context_type"] == "manual_navigation"


def test_read_status_payload_prefers_authoritative_control_state() -> None:
    _write_json(
        control_state_file_path(),
        _control_state_payload(
            mode="emergency_stop",
            active_activity="idle",
            message="비상 정지가 활성화되었습니다.",
            blocking_reason="emergency_stop",
        ),
    )

    payload = read_status_payload()

    assert payload["status"] == "비상 정지"
    assert payload["mode"] == "비상 정지"
    assert payload["mission_state"] == "비상 정지가 활성화되었습니다."
    assert payload["control_mode"] == "emergency_stop"
    assert payload["note"] == "비상 정지가 활성화되었습니다."


def test_read_pose_payload_keeps_last_map_pose_when_snapshot_is_stale() -> None:
    pose_snapshot_path = Path(os.environ["AGRIBOT_RUNTIME_DIR"]) / "robot_pose_snapshot.json"
    _write_json(
        pose_snapshot_path,
        {
            "robot_id": "AGR-02",
            "map_id": "farm_map",
            "pose": {
                "x": -1.9,
                "y": 4.8,
                "z": 0.0,
                "yaw": 1.57,
                "frame_id": "map",
            },
            "linear_speed_mps": 0.0,
            "updated_at": "2026-03-29T00:00:00+00:00",
            "timestamp": 1.0,
        },
    )

    payload = read_pose_payload()

    assert payload["source"] == "live"
    assert payload["pose"]["x"] == pytest.approx(-1.9)
    assert payload["pose"]["y"] == pytest.approx(4.8)
    assert "마지막 실제 좌표를 유지" in payload["note"]


def test_read_pose_payload_falls_back_when_only_non_map_frame_exists() -> None:
    pose_snapshot_path = Path(os.environ["AGRIBOT_RUNTIME_DIR"]) / "robot_pose_snapshot.json"
    _write_json(
        pose_snapshot_path,
        {
            "robot_id": "AGR-02",
            "map_id": "farm_map",
            "pose": {
                "x": -1.9,
                "y": 4.8,
                "z": 0.0,
                "yaw": 1.57,
                "frame_id": "odom",
            },
            "linear_speed_mps": 0.0,
            "updated_at": "2026-03-29T00:00:00+00:00",
            "timestamp": 1.0,
        },
    )

    payload = read_pose_payload()

    assert payload["source"] == "fallback"
    assert payload["pose"]["x"] == pytest.approx(2.0)
    assert payload["pose"]["y"] == pytest.approx(-5.9)
    assert "odom 프레임 pose만 확인" in payload["note"]


def test_robot_control_pause_endpoint_publishes_pause_motion() -> None:
    _write_json(
        control_state_file_path(),
        _control_state_payload(
            mode="normal",
            active_activity="manual_navigation",
            message="수동 이동 중입니다.",
        ),
    )

    response = robots.post_robot_pause(
        robots.RobotControlReq(
            robot_id="AGR-02",
            requested_by="frontend-operator",
        )
    )

    payload = response["data"]
    assert payload["requested_command_type"] == "pause"


def test_read_layers_payload_exposes_safe_approach_pose_for_plants() -> None:
    payload = read_layers_payload()

    plant_asset = next(
        asset for asset in payload["assets"]
        if asset["kind"] == "plant" and asset["id"] == "farm01_plant_01"
    )

    assert plant_asset["position"]["x"] == pytest.approx(-6.0)
    assert plant_asset["position"]["y"] == pytest.approx(-6.0)
    assert plant_asset["navigation_pose"]["x"] == pytest.approx(-8.0)
    assert plant_asset["navigation_pose"]["y"] == pytest.approx(-6.0)
    assert plant_asset["approach_pose"]["x"] == pytest.approx(-6.75)
    assert plant_asset["approach_pose"]["y"] == pytest.approx(-6.0)
    assert plant_asset["inspect_waypoint_id"] == "farm_01_lane_01_inspect_01"
    assert payload["command_type"] == "pause_motion"
    assert payload["request"]["accepted"] is True


def test_read_layers_payload_exposes_dual_observation_candidates_for_center_tomato_plants() -> None:
    payload = read_layers_payload()

    plant_asset = next(
        asset for asset in payload["assets"]
        if asset["kind"] == "plant" and asset["id"] == "farm01_plant_19"
    )

    observation_candidates = plant_asset["observation_candidates"]
    observation_waypoint_ids = {
        candidate["inspect_waypoint_id"]
        for candidate in observation_candidates
    }

    assert "farm_01_lane_center_inspect_05" in observation_waypoint_ids
    assert "farm_01_lane_03_inspect_05" in observation_waypoint_ids

    center_candidate = next(
        candidate for candidate in observation_candidates
        if candidate["inspect_waypoint_id"] == "farm_01_lane_center_inspect_05"
    )
    assert center_candidate["navigation_pose"]["x"] == pytest.approx(0.0)
    assert center_candidate["navigation_pose"]["y"] == pytest.approx(4.0)
    assert center_candidate["approach_pose"]["x"] == pytest.approx(1.25)
    assert center_candidate["approach_pose"]["y"] == pytest.approx(4.0)


def test_publish_navigate_command_keeps_all_observation_candidates_in_bridge_payload() -> None:
    response = publish_robot_command(
        robot_id="AGR-02",
        command_type="navigate_to_pose",
        requested_by="frontend-operator",
        target_pose={
            "x": 4.0,
            "y": 4.0,
            "z": 0.0,
            "yaw": 1.5708,
            "frame_id": "map",
        },
        payload={
            "plant_id": "farm01_plant_19",
            "inspect_waypoint_id": "farm_01_lane_03_inspect_05",
            "inspect_waypoint_ids": [
                "farm_01_lane_03_inspect_05",
                "farm_01_lane_center_inspect_05",
            ],
        },
    )

    command_payload = json.loads(command_file_path().read_text(encoding="utf-8"))

    assert response["accepted"] is True
    assert command_payload["payload"]["plant_id"] == "farm01_plant_19"
    assert command_payload["payload"]["inspect_waypoint_id"] == "farm_01_lane_03_inspect_05"
    assert command_payload["payload"]["inspect_waypoint_ids"] == [
        "farm_01_lane_03_inspect_05",
        "farm_01_lane_center_inspect_05",
    ]


def test_missions_patrol_stop_endpoint_publishes_pause_patrol() -> None:
    _write_json(
        control_state_file_path(),
        _control_state_payload(
            mode="normal",
            active_activity="patrol",
            message="순찰 중입니다.",
        ),
    )

    response = missions.stop_patrol(
        missions.PatrolStopReq(
            robot_id="AGR-02",
            requested_by="frontend-operator",
            reason="ui_pause",
        )
    )

    payload = response["data"]
    assert payload["requested_command_type"] == "pause_patrol"
    assert payload["command_type"] == "pause_patrol"


def test_missions_return_home_endpoint_publishes_return_home() -> None:
    response = missions.return_home(
        missions.ReturnHomeReq(
            robot_id="AGR-02",
            requested_by="frontend-operator",
        )
    )

    payload = response["data"]
    assert payload["requested_command_type"] == "return_home"
    assert payload["command_type"] == "return_home"


def test_missions_patrol_start_endpoint_writes_runtime_bridge_request() -> None:
    response = missions.start_patrol(
        missions.PatrolStartReq(
            mission_id="mission-patrol-router-001",
            robot_id="AGR-02",
            zone_ids=["farm_01_west", "farm_01_center"],
            loop_count=1,
            requested_by="frontend-operator",
            patrol_mode="diagnosis",
        )
    )

    payload = response["data"]
    request_payload = json.loads(mission_request_file_path().read_text(encoding="utf-8"))

    assert payload["mission_id"] == "mission-patrol-router-001"
    assert payload["request_type"] == "start_patrol"
    assert payload["status_endpoint"] == "/api/v1/missions/mission-patrol-router-001"
    assert request_payload["zone_ids"] == ["farm_01_west", "farm_01_center"]
    assert request_payload["patrol_mode"] == "diagnosis"


def test_missions_harvest_endpoint_writes_runtime_bridge_request() -> None:
    response = missions.harvest_mission(
        missions.HarvestReq(
            mission_id="mission-harvest-router-001",
            robot_id="AGR-02",
            plant_id="farm01_plant_03",
            fruit_id="farm01_plant_03_tomato_01",
            requested_by="frontend-operator",
        )
    )

    payload = response["data"]
    request_payload = json.loads(mission_request_file_path().read_text(encoding="utf-8"))

    assert payload["mission_id"] == "mission-harvest-router-001"
    assert payload["request_type"] == "harvest_target"
    assert request_payload["plant_id"] == "farm01_plant_03"
    assert request_payload["tomato_id"] == "farm01_plant_03_tomato_01"


def test_get_mission_status_endpoint_reads_record_file() -> None:
    _write_json(
        mission_status_record_file_path("mission-harvest-router-002"),
        {
            "mission_id": "mission-harvest-router-002",
            "command_id": "mission-harvest-router-002",
            "request_type": "harvest_target",
            "robot_id": "AGR-02",
            "requested_by": "frontend-operator",
            "status": "running",
            "message": "Harvest target 접근 중입니다.",
            "fruit_id": "farm01_plant_03_tomato_01",
            "tomato_id": "farm01_plant_03_tomato_01",
            "updated_at": "2026-03-25T00:00:00+00:00",
        },
    )

    response = missions.get_mission_status("mission-harvest-router-002")

    payload = response["data"]
    assert payload["mission_id"] == "mission-harvest-router-002"
    assert payload["status"] == "running"
    assert payload["fruit_id"] == "farm01_plant_03_tomato_01"


def test_robot_commands_resume_returns_409_for_invalid_transition() -> None:
    _write_json(
        control_state_file_path(),
        _control_state_payload(
            mode="normal",
            active_activity="idle",
            message="정상 제어 상태입니다.",
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        robots.post_robot_command(
            robots.RobotCommandReq(
                robot_id="AGR-02",
                requested_by="frontend-operator",
                command_type="resume",
            )
        )

    assert exc_info.value.status_code == 409
    assert "제어 latch" in str(exc_info.value.detail)
