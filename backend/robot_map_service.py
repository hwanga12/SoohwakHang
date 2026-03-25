import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MAPS_DIR = REPO_ROOT / "agribot_ws" / "src" / "agribot_navigation" / "maps"
CROP_INSTANCES_PATH = (
    REPO_ROOT
    / "agribot_ws"
    / "src"
    / "agribot_description"
    / "config"
    / "crop_instances.yaml"
)
WORLD_PATH = (
    REPO_ROOT
    / "agribot_ws"
    / "src"
    / "agribot_description"
    / "worlds"
    / "farm_world.sdf"
)
IOT_DEVICES_PATH = (
    REPO_ROOT
    / "agribot_ws"
    / "src"
    / "agribot_iot"
    / "config"
    / "iot_devices.yaml"
)
POSE_SNAPSHOT_PATH = (
    Path(os.environ.get("AGRIBOT_RUNTIME_DIR", "/tmp/agribot_runtime"))
    / "robot_pose_snapshot.json"
)
DEFAULT_MAP_ID = "farm_map"
MAP_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
POSE_STALE_SECONDS = 4.0

ZONE_LABELS = {
    "farm_01_west": "farm_01 · 서측 2열",
    "farm_01_center": "farm_01 · 중앙 라인",
    "farm_01_east": "farm_01 · 동측 라인",
}


def _clean_yaml_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if line.strip():
            lines.append(line)
    return lines


def _parse_scalar(value: str) -> Any:
    trimmed = value.strip().strip("'").strip('"')
    if not trimmed:
        return ""
    if trimmed in {"true", "false"}:
        return trimmed == "true"
    try:
        if "." in trimmed or "e" in trimmed.lower():
            return float(trimmed)
        return int(trimmed)
    except ValueError:
        return trimmed


def _parse_pose_text(value: str) -> dict[str, float]:
    tokens = [float(token) for token in value.split()]
    while len(tokens) < 6:
        tokens.append(0.0)
    return {
        "x": tokens[0],
        "y": tokens[1],
        "z": tokens[2],
        "roll": tokens[3],
        "pitch": tokens[4],
        "yaw": tokens[5],
    }


def _read_pgm_dimensions(image_path: Path) -> tuple[int, int]:
    raw = image_path.read_bytes()
    tokens: list[str] = []
    index = 0

    while index < len(raw) and len(tokens) < 4:
        value = raw[index]
        if value == 35:
            while index < len(raw) and raw[index] not in (10, 13):
                index += 1
            continue
        if chr(value).isspace():
            index += 1
            continue

        start = index
        while index < len(raw) and not chr(raw[index]).isspace() and raw[index] != 35:
            index += 1
        tokens.append(raw[start:index].decode("ascii"))

    if len(tokens) < 4:
        raise ValueError(f"{image_path.name} 헤더를 읽지 못했습니다.")

    return int(tokens[1]), int(tokens[2])


def _sanitize_map_id(map_id: str | None) -> str:
    resolved = map_id or DEFAULT_MAP_ID
    if not MAP_ID_PATTERN.fullmatch(resolved):
        raise ValueError("유효하지 않은 map_id 입니다.")
    return resolved


def _map_yaml_path(map_id: str) -> Path:
    path = MAPS_DIR / f"{map_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"{map_id}.yaml 파일을 찾지 못했습니다.")
    return path


def _load_map_yaml(yaml_path: Path) -> dict[str, Any]:
    lines = _clean_yaml_lines(yaml_path)
    metadata: dict[str, Any] = {}
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()
        if ":" not in stripped:
            index += 1
            continue

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if key == "origin":
            origin_values: list[float] = []
            index += 1
            while index < len(lines) and lines[index].lstrip().startswith("-"):
                origin_values.append(float(lines[index].split("-", 1)[1].strip()))
                index += 1
            metadata["origin"] = {
                "x": origin_values[0] if len(origin_values) > 0 else 0.0,
                "y": origin_values[1] if len(origin_values) > 1 else 0.0,
                "yaw": origin_values[2] if len(origin_values) > 2 else 0.0,
            }
            continue

        metadata[key] = _parse_scalar(raw_value)
        index += 1

    return metadata


def _load_crop_instances() -> dict[str, Any]:
    lines = _clean_yaml_lines(CROP_INSTANCES_PATH)
    data: dict[str, Any] = {
        "plants": [],
        "tomatoes": [],
    }
    section: str | None = None
    current_item: dict[str, Any] | None = None
    current_pose: dict[str, Any] | None = None

    for line in lines:
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and stripped.endswith(":"):
            key = stripped[:-1]
            section = key if key in {"plants", "tomatoes"} else None
            current_item = None
            current_pose = None
            continue

        if section not in {"plants", "tomatoes"}:
            continue

        if stripped.startswith("- "):
            current_item = {}
            current_pose = None
            data[section].append(current_item)
            stripped = stripped[2:]
            if ":" in stripped:
                key, raw_value = stripped.split(":", 1)
                current_item[key.strip()] = _parse_scalar(raw_value)
            continue

        if current_item is None:
            continue

        if stripped == "pose:":
            current_pose = {}
            current_item["pose"] = current_pose
            continue

        if current_pose is not None and indent >= 4 and ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            current_pose[key.strip()] = _parse_scalar(raw_value)
            continue

        current_pose = None
        if ":" in stripped:
            key, raw_value = stripped.split(":", 1)
            current_item[key.strip()] = _parse_scalar(raw_value)

    return data


def _load_iot_devices() -> dict[str, dict[str, Any]]:
    lines = _clean_yaml_lines(IOT_DEVICES_PATH)
    current_zone_id = ""
    in_devices = False
    current_device: dict[str, Any] | None = None
    devices: dict[str, dict[str, Any]] = {}

    for line in lines:
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 2 and stripped.startswith("- zone_id:"):
            current_zone_id = stripped.split(":", 1)[1].strip()
            in_devices = False
            current_device = None
            continue

        if indent == 4 and stripped == "devices:":
            in_devices = True
            current_device = None
            continue

        if not in_devices:
            continue

        if indent == 6 and stripped.startswith("- device_id:"):
            device_id = stripped.split(":", 1)[1].strip()
            current_device = {
                "device_id": device_id,
                "zone_id": current_zone_id,
            }
            devices[device_id] = current_device
            continue

        if current_device is None:
            continue

        if indent >= 8 and ":" in stripped and not stripped.startswith("- "):
            key, raw_value = stripped.split(":", 1)
            current_device[key.strip()] = _parse_scalar(raw_value)

    return devices


def _load_world_semantics() -> dict[str, Any]:
    root = ET.parse(WORLD_PATH).getroot()
    world = root.find("world")
    if world is None:
        raise ValueError("farm_world.sdf에서 world 노드를 찾지 못했습니다.")

    row_guides: list[dict[str, Any]] = []
    sprinklers: list[dict[str, Any]] = []

    crop_rows = world.find("./model[@name='crop_rows']")
    if crop_rows is not None:
        for index, collision in enumerate(crop_rows.findall("./link/collision"), start=1):
            pose = _parse_pose_text(collision.findtext("pose", "0 0 0 0 0 0"))
            row_guides.append(
                {
                    "id": f"row-{index}",
                    "axis": "x",
                    "value": pose["x"],
                    "label": f"재배열 {index}",
                }
            )

    for include in world.findall("include"):
        name = include.findtext("name", "")
        uri = include.findtext("uri", "")
        if not name.startswith("sprinkler_") and not uri.endswith("sprinkler"):
            continue

        pose = _parse_pose_text(include.findtext("pose", "0 0 0 0 0 0"))
        sprinklers.append(
            {
                "id": name or f"sprinkler_{len(sprinklers)}",
                "position": {
                    "x": pose["x"],
                    "y": pose["y"],
                    "z": pose["z"],
                },
            }
        )

    return {
        "bounds": {
            "min_x": -10.0,
            "max_x": 10.0,
            "min_y": -10.0,
            "max_y": 10.0,
        },
        "row_guides": row_guides,
        "sprinklers": sprinklers,
    }


def _build_lane_guides(plant_positions: list[dict[str, float]]) -> list[dict[str, Any]]:
    y_values = sorted({round(position["y"], 3) for position in plant_positions})
    if not y_values:
        return []

    return [
        {"id": "lane-bottom-1", "axis": "y", "value": y_values[0] - 2.0, "label": "하단 통로"},
        {"id": "lane-bottom-2", "axis": "y", "value": (y_values[0] + y_values[1]) / 2.0, "label": "하단 점검 라인"},
        {"id": "lane-mid", "axis": "y", "value": 0.0, "label": "중앙 급수 라인"},
        {"id": "lane-top-1", "axis": "y", "value": (y_values[-2] + y_values[-1]) / 2.0, "label": "상단 점검 라인"},
        {"id": "lane-top-2", "axis": "y", "value": y_values[-1] + 2.0, "label": "상단 통로"},
    ]


def read_map_payload(map_id: str | None = None) -> dict[str, Any]:
    resolved_map_id = _sanitize_map_id(map_id)
    yaml_path = _map_yaml_path(resolved_map_id)
    metadata = _load_map_yaml(yaml_path)
    image_path = yaml_path.with_name(str(metadata.get("image", f"{resolved_map_id}.pgm")))
    width, height = _read_pgm_dimensions(image_path)

    return {
        "source": "live",
        "map_id": resolved_map_id,
        "image_url": f"/api/v1/robot/map/raw?map_id={resolved_map_id}",
        "resolution": float(metadata.get("resolution", 0.05)),
        "origin": metadata.get("origin", {"x": 0.0, "y": 0.0, "yaw": 0.0}),
        "width": width,
        "height": height,
        "bounds": {
            "min_x": -10.0,
            "max_x": 10.0,
            "min_y": -10.0,
            "max_y": 10.0,
        },
    }


def image_path_for_map(map_id: str | None = None) -> Path:
    resolved_map_id = _sanitize_map_id(map_id)
    yaml_path = _map_yaml_path(resolved_map_id)
    metadata = _load_map_yaml(yaml_path)
    image_path = yaml_path.with_name(str(metadata.get("image", f"{resolved_map_id}.pgm")))
    if not image_path.exists():
        raise FileNotFoundError(f"{image_path.name} 파일을 찾지 못했습니다.")
    return image_path


def _guess_zone_id(x_value: float) -> str:
    if x_value < -1.5:
        return "farm_01_west"
    if x_value > 4.0:
        return "farm_01_east"
    return "farm_01_center"


def _fallback_pose_payload(map_id: str) -> dict[str, Any]:
    updated_at = datetime.now(timezone.utc).isoformat()
    current_zone_id = "farm_01_west"
    return {
        "source": "fallback",
        "robot_id": "AGR-02",
        "map_id": map_id,
        "current_zone_id": current_zone_id,
        "current_zone_label": ZONE_LABELS[current_zone_id],
        "pose": {
            "x": 2.0,
            "y": -5.9,
            "z": 0.0,
            "yaw": 0.0,
            "frame_id": "map",
        },
        "linear_speed_mps": 1.1,
        "updated_at": updated_at,
        "note": "런타임 pose 스냅샷이 없어 발표용 fallback 좌표를 사용합니다.",
    }


def read_pose_payload(map_id: str | None = None) -> dict[str, Any]:
    resolved_map_id = _sanitize_map_id(map_id)

    try:
        payload = json.loads(POSE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _fallback_pose_payload(resolved_map_id)
    except (OSError, json.JSONDecodeError):
        return _fallback_pose_payload(resolved_map_id)

    pose = payload.get("pose")
    if not isinstance(pose, dict):
        return _fallback_pose_payload(resolved_map_id)

    timestamp = payload.get("timestamp")
    is_recent = isinstance(timestamp, (int, float)) and (time.time() - float(timestamp) <= POSE_STALE_SECONDS)
    frame_id = str(pose.get("frame_id", "")).strip() or "map"
    if frame_id != "map" or not is_recent:
        fallback = _fallback_pose_payload(resolved_map_id)
        fallback["note"] = (
            f"{frame_id} 프레임 또는 오래된 pose만 확인되어 fallback 좌표를 유지합니다."
        )
        return fallback

    x_value = float(pose.get("x", 0.0))
    current_zone_id = _guess_zone_id(x_value)
    return {
        "source": "live",
        "robot_id": str(payload.get("robot_id", "AGR-02")),
        "map_id": str(payload.get("map_id", resolved_map_id)),
        "current_zone_id": current_zone_id,
        "current_zone_label": ZONE_LABELS[current_zone_id],
        "pose": {
            "x": x_value,
            "y": float(pose.get("y", 0.0)),
            "z": float(pose.get("z", 0.0)),
            "yaw": float(pose.get("yaw", 0.0)),
            "frame_id": frame_id,
        },
        "linear_speed_mps": float(payload.get("linear_speed_mps", 0.0)),
        "updated_at": str(payload.get("updated_at", datetime.now(timezone.utc).isoformat())),
        "note": "map 프레임 pose 스냅샷을 반영 중입니다.",
    }


def read_status_payload(map_id: str | None = None) -> dict[str, Any]:
    pose_payload = read_pose_payload(map_id)
    is_live = pose_payload["source"] == "live"

    return {
        "source": pose_payload["source"],
        "robot_id": pose_payload["robot_id"],
        "status": "이동 중" if is_live else "준비 데이터",
        "mission_state": "정적 지도 기반 자율 주행" if is_live else "live pose 연동 대기",
        "mode": "자율 순찰",
        "battery": "82%",
        "battery_eta": "충전 없이 2시간 10분 운행 예상",
        "speed_mps": f"{pose_payload['linear_speed_mps']:.2f}m/s",
        "mission_progress_pct": 76 if is_live else 58,
        "eta": "예상 완료 12분 30초",
        "waypoint_id": "inspection_b12",
        "next_waypoint": "inspection_b13",
        "next_target_crop_id": "farm01_plant_06_tomato_01",
        "current_zone_id": pose_payload["current_zone_id"],
        "zone_label": pose_payload["current_zone_label"],
        "updated_at": pose_payload["updated_at"],
        "note": pose_payload["note"],
    }


def read_layers_payload(map_id: str | None = None) -> dict[str, Any]:
    resolved_map_id = _sanitize_map_id(map_id)
    crop_instances = _load_crop_instances()
    world = _load_world_semantics()
    devices = _load_iot_devices()
    tomato_lookup = {
        tomato["plant_id"]: tomato
        for tomato in crop_instances.get("tomatoes", [])
        if isinstance(tomato, dict) and tomato.get("plant_id")
    }

    plant_assets: list[dict[str, Any]] = []
    plant_positions: list[dict[str, float]] = []
    for plant in crop_instances.get("plants", []):
        if not isinstance(plant, dict):
            continue

        pose = plant.get("pose", {})
        x_value = float(pose.get("x", 0.0))
        y_value = float(pose.get("y", 0.0))
        plant_positions.append({"x": x_value, "y": y_value})
        plant_id = str(plant.get("plant_id", ""))
        linked_tomato = tomato_lookup.get(plant_id, {})

        plant_assets.append(
            {
                "id": plant_id,
                "linked_id": linked_tomato.get("tomato_id"),
                "kind": "plant",
                "label": str(plant.get("display_name", plant_id)),
                "short_label": plant_id[-2:],
                "zone_id": str(plant.get("zone_id", "farm_01")),
                "description": "작물 관찰 및 수확 후보 탐색 대상 식물",
                "position": {
                    "x": x_value,
                    "y": y_value,
                    "z": float(pose.get("z", 0.0)),
                },
                "status": "normal",
            }
        )

    watering_device = devices.get("farm_01_watering", {})
    sprinkler_assets = [
        {
            "id": sprinkler["id"],
            "linked_id": watering_device.get("device_id"),
            "kind": "sprinkler",
            "label": f"급수 포인트 {index + 1}",
            "short_label": f"W{index + 1}",
            "zone_id": watering_device.get("zone_id", "farm_01"),
            "description": (
                f"{watering_device.get('display_name', 'Watering Pump')}와 연결된 급수 포인트"
            ),
            "position": sprinkler["position"],
            "status": "normal",
        }
        for index, sprinkler in enumerate(world["sprinklers"])
    ]

    return {
        "source": "live",
        "map_id": resolved_map_id,
        "bounds": world["bounds"],
        "row_guides": world["row_guides"],
        "lane_guides": _build_lane_guides(plant_positions),
        "assets": plant_assets + sprinkler_assets,
        "counts": {
            "plants": len(plant_assets),
            "sprinklers": len(sprinkler_assets),
        },
    }
