from __future__ import annotations

from pathlib import Path
from typing import Any

from robot_map_service import REPO_ROOT, ZONE_LABELS, read_layers_payload, read_map_payload

PATROL_WAYPOINTS_PATH = (
    REPO_ROOT
    / "agribot_ws"
    / "src"
    / "agribot_navigation"
    / "config"
    / "patrol_waypoints.yaml"
)

ZONE_BOUNDARY_WEST_MAX_X = -1.5
ZONE_BOUNDARY_CENTER_MAX_X = 4.0

ZONE_METADATA = {
    "farm_01_west": {
        "name": "Farm 01 서측 재배열",
        "description": "서측 작물열 진입과 점검을 위한 대표 이동 구역입니다.",
        "representative_waypoint_id": "farm_01_lane_01_south_entry",
    },
    "farm_01_center": {
        "name": "Farm 01 중앙 운영 라인",
        "description": "홈 포즈와 중앙 급수 라인을 공유하는 기준 이동 구역입니다.",
        "representative_waypoint_id": "farm_01_home",
    },
    "farm_01_east": {
        "name": "Farm 01 동측 재배열",
        "description": "동측 작물열 진입과 복귀를 위한 대표 이동 구역입니다.",
        "representative_waypoint_id": "farm_01_lane_04_south_turn",
    },
}


class ZoneResolutionError(ValueError):
    pass


def zone_label_for_id(zone_id: str) -> str:
    return ZONE_LABELS.get(zone_id, zone_id)


def guess_zone_id_for_x(x_value: float) -> str:
    if x_value < ZONE_BOUNDARY_WEST_MAX_X:
        return "farm_01_west"
    if x_value > ZONE_BOUNDARY_CENTER_MAX_X:
        return "farm_01_east"
    return "farm_01_center"


def _load_waypoint_poses() -> dict[str, dict[str, float]]:
    lines = PATROL_WAYPOINTS_PATH.read_text(encoding="utf-8").splitlines()
    waypoint_id = ""
    current_pose: dict[str, float] | None = None
    waypoints: dict[str, dict[str, float]] = {}

    for raw_line in lines:
        stripped = raw_line.strip()
        if stripped.startswith("- waypoint_id:"):
            waypoint_id = stripped.split(":", 1)[1].strip()
            current_pose = {}
            waypoints[waypoint_id] = current_pose
            continue

        if not waypoint_id or current_pose is None:
            continue

        if stripped.startswith("x:"):
            current_pose["x"] = float(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("y:"):
            current_pose["y"] = float(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("z:"):
            current_pose["z"] = float(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("yaw:"):
            current_pose["yaw"] = float(stripped.split(":", 1)[1].strip())

    return waypoints


def _zone_bounds(map_bounds: dict[str, float]) -> dict[str, dict[str, float]]:
    min_x = float(map_bounds["min_x"])
    max_x = float(map_bounds["max_x"])
    min_y = float(map_bounds["min_y"])
    max_y = float(map_bounds["max_y"])

    return {
        "farm_01_west": {
            "min_x": min_x,
            "max_x": min(ZONE_BOUNDARY_WEST_MAX_X, max_x),
            "min_y": min_y,
            "max_y": max_y,
        },
        "farm_01_center": {
            "min_x": max(min_x, ZONE_BOUNDARY_WEST_MAX_X),
            "max_x": min(ZONE_BOUNDARY_CENTER_MAX_X, max_x),
            "min_y": min_y,
            "max_y": max_y,
        },
        "farm_01_east": {
            "min_x": max(min_x, ZONE_BOUNDARY_CENTER_MAX_X),
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
        },
    }


def _representative_pose_for_zone(
    zone_id: str,
    *,
    frame_id: str,
    waypoint_poses: dict[str, dict[str, float]],
) -> dict[str, Any]:
    metadata = ZONE_METADATA[zone_id]
    waypoint_id = metadata["representative_waypoint_id"]
    pose = waypoint_poses.get(waypoint_id)
    if pose is None:
        raise ZoneResolutionError(f"대표 waypoint를 찾지 못했습니다: {waypoint_id}")

    return {
        "x": float(pose["x"]),
        "y": float(pose["y"]),
        "z": float(pose.get("z", 0.0)),
        "yaw": float(pose.get("yaw", 0.0)),
        "frame_id": frame_id,
    }


def read_zones_payload(map_id: str | None = None) -> list[dict[str, Any]]:
    map_payload = read_map_payload(map_id)
    layers_payload = read_layers_payload(map_id)
    waypoint_poses = _load_waypoint_poses()
    zone_bounds = _zone_bounds(map_payload["bounds"])

    plant_counts = {zone_id: 0 for zone_id in ZONE_METADATA}
    for asset in layers_payload.get("assets", []):
        if asset.get("kind") != "plant":
            continue
        position = asset.get("position", {})
        zone_id = guess_zone_id_for_x(float(position.get("x", 0.0)))
        plant_counts[zone_id] += 1

    zones: list[dict[str, Any]] = []
    for zone_id, metadata in ZONE_METADATA.items():
        representative_pose = _representative_pose_for_zone(
            zone_id,
            frame_id=str(map_payload["origin"].get("frame_id", "map"))
            if isinstance(map_payload.get("origin"), dict)
            else "map",
            waypoint_poses=waypoint_poses,
        )
        representative_pose["frame_id"] = "map"
        zones.append(
            {
                "id": zone_id,
                "name": metadata["name"],
                "label": zone_label_for_id(zone_id),
                "description": metadata["description"],
                "representative_waypoint_id": metadata["representative_waypoint_id"],
                "representative_pose": representative_pose,
                "bounds": zone_bounds[zone_id],
                "plant_count": plant_counts[zone_id],
                "map_id": map_payload["map_id"],
            }
        )

    return zones


def resolve_zone_payload(zone_id: str, map_id: str | None = None) -> dict[str, Any]:
    for zone in read_zones_payload(map_id):
        if zone["id"] == zone_id:
            return zone
    raise ZoneResolutionError(f"알 수 없는 zone_id 입니다: {zone_id}")


def resolve_zone_representative_pose(zone_id: str, map_id: str | None = None) -> dict[str, Any]:
    return resolve_zone_payload(zone_id, map_id)["representative_pose"]
