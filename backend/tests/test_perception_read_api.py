from __future__ import annotations

from datetime import datetime, timezone
import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers import alerts, camera, media, plants


@pytest.fixture()
def runtime_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("AGRIBOT_BACKEND_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("AGRIBOT_ROBOT_CAMERA_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def _write_runtime_observation(
    runtime_dir: Path,
    *,
    observation_id: str,
    plant_id: str,
    final_label: str,
    reviewed_at: str,
    image_format: str = "jpg",
) -> Path:
    date_dir = runtime_dir / "20260326"
    date_dir.mkdir(parents=True, exist_ok=True)

    image_path = date_dir / f"{observation_id}.{image_format}"
    image_path.write_bytes(b"fake-jpeg-bytes")

    metadata_path = date_dir / f"{observation_id}.json"
    metadata_path.write_text(
        json.dumps(
            {
                "observation_id": observation_id,
                "reviewed_at": reviewed_at,
                "final_label": final_label,
                "final_confidence": 0.91,
                "decision_source": "backend_model",
                "request": {
                    "plant_id": plant_id,
                    "zone_id": "farm_01_center",
                    "preliminary_label": "powdery_mildew",
                    "image_format": image_format,
                },
                "treatment_plan": {
                    "action_required": True,
                    "reason": "병해 진단 결과를 기준으로 약재 살포 검토가 필요합니다.",
                },
                "dispatch_result": {
                    "dispatched": False,
                    "status": "awaiting_operator_review",
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return image_path


def _write_live_camera_snapshot(
    runtime_dir: Path,
    *,
    captured_at: str | None = None,
    plant_id: str = "farm01_plant_06",
    observation_id: str = "obs-runtime-01",
    image_format: str = "jpg",
) -> Path:
    camera_dir = runtime_dir / "camera"
    camera_dir.mkdir(parents=True, exist_ok=True)

    image_path = camera_dir / f"latest_frame.{image_format}"
    image_path.write_bytes(b"fake-live-camera-bytes")

    metadata_path = camera_dir / "latest_frame.json"
    metadata_path.write_text(
        json.dumps(
            {
                "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
                "frame_id": "agribot_camera",
                "image_format": image_format,
                "image_path": str(image_path),
                "plant_id": plant_id,
                "fruit_id": "farm01_tomato_06",
                "observation_id": observation_id,
                "detection": {
                    "label": "ripe_tomato",
                    "confidence": 0.97,
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return image_path


def test_perception_read_endpoints_return_runtime_observation_data(runtime_dir: Path) -> None:
    image_path = _write_runtime_observation(
        runtime_dir,
        observation_id="obs-runtime-01",
        plant_id="farm01_plant_06",
        final_label="tomato_powdery_mildew_disease",
        reviewed_at="2026-03-26T12:34:56+00:00",
    )

    alerts_payload = alerts.get_alerts()["data"]
    assert isinstance(alerts_payload, list)
    assert alerts_payload[0]["id"] == "obs-runtime-01"
    assert alerts_payload[0]["display_label"] == "토마토 흰가루병"
    assert alerts_payload[0]["image_url"] == "/api/v1/media/obs-runtime-01"
    assert alerts_payload[0]["plant_id"] == "farm01_plant_06"

    plants_payload = plants.get_plants()["data"]
    observed_plant = next(item for item in plants_payload if item["plant_id"] == "farm01_plant_06")
    assert observed_plant["latest_display_label"] == "토마토 흰가루병"
    assert observed_plant["latest_image_url"] == "/api/v1/media/obs-runtime-01"
    assert observed_plant["recommended_action"]

    observations_payload = plants.get_plant_observations("farm01_plant_06")["data"]
    assert observations_payload["plant_id"] == "farm01_plant_06"
    runtime_observation = next(
        item for item in observations_payload["items"] if item["id"] == "obs-runtime-01"
    )
    assert runtime_observation["class_name"] == "tomato_powdery_mildew_disease"
    assert runtime_observation["image_url"] == "/api/v1/media/obs-runtime-01"
    assert runtime_observation["media_asset_id"] == "obs-runtime-01"

    media_response = media.get_media("obs-runtime-01")
    assert Path(media_response.path) == image_path
    assert media_response.media_type == "image/jpeg"
    assert media_response.filename == image_path.name

    live_camera_path = _write_live_camera_snapshot(runtime_dir)
    live_camera_payload = camera.get_latest_camera_snapshot()["data"]
    assert live_camera_payload["available"] is True
    assert live_camera_payload["is_stale"] is False
    assert live_camera_payload["image_url"] == "/api/v1/camera/latest/frame"
    assert live_camera_payload["plant_id"] == "farm01_plant_06"
    assert live_camera_payload["observation_image_url"] == "/api/v1/media/obs-runtime-01"

    live_camera_response = camera.get_latest_camera_frame()
    assert Path(live_camera_response.path) == live_camera_path
    assert live_camera_response.media_type == "image/jpeg"
    assert live_camera_response.filename == live_camera_path.name


def test_alert_ack_endpoint_marks_runtime_alert_as_acknowledged(runtime_dir: Path) -> None:
    _write_runtime_observation(
        runtime_dir,
        observation_id="obs-runtime-ack",
        plant_id="farm01_plant_10",
        final_label="tomato_gray_mold_disease",
        reviewed_at="2026-03-26T15:00:00+00:00",
    )

    ack_payload = alerts.ack_alert(
        "obs-runtime-ack",
        alerts.AlertAckReq(acknowledged_by="frontend-operator"),
    )["data"]
    assert ack_payload["id"] == "obs-runtime-ack"
    assert ack_payload["acknowledged_by"] == "frontend-operator"

    alerts_payload = alerts.get_alerts()["data"]
    updated_alert = next(item for item in alerts_payload if item["id"] == "obs-runtime-ack")
    assert updated_alert["is_acked"] is True
    assert updated_alert["acknowledged_by"] == "frontend-operator"


def test_live_camera_snapshot_marks_stale_frames(runtime_dir: Path) -> None:
    _write_live_camera_snapshot(
        runtime_dir,
        captured_at="2020-01-01T00:00:00+00:00",
        observation_id="",
    )

    live_camera_payload = camera.get_latest_camera_snapshot()["data"]
    assert live_camera_payload["available"] is True
    assert live_camera_payload["is_stale"] is True
    assert live_camera_payload["observation_image_url"] == ""
