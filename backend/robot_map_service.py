import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from database import SessionLocal
from models import Mission, Robot, Zone
from robot_runtime_state_service import (
    RobotRuntimeStateError,
    build_idle_command_status_payload,
    build_unavailable_control_state_payload,
    read_control_state_payload,
    read_latest_command_status_payload,
    runtime_dir_from_env,
)

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
POSE_SNAPSHOT_FILENAME = "robot_pose_snapshot.json"
DEFAULT_MAP_ID = "farm_map"
MAP_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
POSE_STALE_SECONDS = 4.0

ZONE_LABELS = {
    "farm_01": "Farm 01",
}


def _mission_sort_key(mission: Mission) -> tuple[int, str, str]:
    priority = {
        "RUNNING": 0,
        "PENDING": 1,
        "COMPLETED": 2,
        "FAILED": 3,
        "CANCELED": 4,
    }.get(str(mission.status or "").upper(), 9)
    started_ts = mission.started_at.timestamp() if mission.started_at else 0.0
    completed_ts = mission.completed_at.timestamp() if mission.completed_at else 0.0
    return (priority, -(started_ts or completed_ts), str(mission.id))


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
    del x_value
    return "farm_01"


def _pose_snapshot_path() -> Path:
    return runtime_dir_from_env() / POSE_SNAPSHOT_FILENAME


def _safe_control_state_payload() -> dict[str, Any]:
    try:
        return read_control_state_payload()
    except RobotRuntimeStateError as exc:
        return build_unavailable_control_state_payload(str(exc))


def _safe_latest_command_status_payload(
    control_state: dict[str, Any],
) -> dict[str, Any]:
    try:
        return read_latest_command_status_payload()
    except RobotRuntimeStateError as exc:
        return {
            **build_idle_command_status_payload(str(exc), control_state=control_state),
            "control_state": control_state,
            "control_mode": control_state["mode"],
            "control_is_latched": control_state["is_latched"],
            "control_active_activity": control_state["active_activity"],
            "control_blocking_reason": control_state["blocking_reason"],
            "control_message": control_state["message"],
            "control_resume_available": control_state["resume_available"],
            "control_updated_at": control_state["updated_at"],
        }


def _load_db_robot_context(robot_identifier: str | None = None) -> dict[str, Any]:
    db = SessionLocal()
    try:
        robot_query = db.query(Robot)
        robot: Robot | None = None
        if robot_identifier:
            robot = robot_query.filter(Robot.name == str(robot_identifier)).first()
        if robot is None:
            robot = robot_query.order_by(Robot.updated_at.desc().nullslast(), Robot.name.asc()).first()
        if robot is None:
            return {}

        zone: Zone | None = None
        if robot.current_zone_id:
            zone = db.query(Zone).filter(Zone.id == robot.current_zone_id).first()

        mission_rows = db.query(Mission).filter(Mission.robot_id == robot.id).all()
        mission = sorted(mission_rows, key=_mission_sort_key)[0] if mission_rows else None

        return {
            "robot_name": robot.name,
            "robot_status": str(robot.status or "").strip().upper(),
            "battery_level": robot.battery_level,
            "current_zone_id": robot.current_zone_id,
            "zone_label": zone.name if zone is not None and zone.name else ZONE_LABELS.get(robot.current_zone_id or "", ""),
            "updated_at": robot.updated_at.isoformat() if robot.updated_at else "",
            "mission_type": mission.mission_type if mission is not None else "",
            "mission_status": mission.status if mission is not None else "",
            "mission_progress_pct": mission.progress_percent if mission is not None else None,
        }
    except Exception:
        return {}
    finally:
        db.close()


def _resolve_db_status_label(db_context: dict[str, Any]) -> str:
    robot_status = str(db_context.get("robot_status") or "").upper()
    mission_status = str(db_context.get("mission_status") or "").upper()
    mission_type = str(db_context.get("mission_type") or "").upper()

    if robot_status == "ERROR":
        return "오류"
    if mission_status == "RUNNING" and mission_type == "HARVEST":
        return "수확 중"
    if mission_status == "RUNNING" and mission_type == "PATROL":
        return "순찰 중"
    if robot_status == "HARVEST":
        return "수확 중"
    if robot_status == "PATROL":
        return "순찰 중"
    if robot_status == "RETURN_HOME":
        return "홈 복귀 중"
    return "대기"


def _resolve_db_mission_state(db_context: dict[str, Any]) -> str:
    mission_type = str(db_context.get("mission_type") or "").upper()
    mission_status = str(db_context.get("mission_status") or "").upper()

    if mission_type and mission_status:
        return f"{mission_type} · {mission_status}"
    if mission_type:
        return mission_type
    return "대기 중"


def _resolve_status_label(
    *,
    pose_payload: dict[str, Any],
    control_state: dict[str, Any],
    latest_command_status: dict[str, Any],
) -> str:
    control_mode = control_state["mode"]
    active_activity = control_state["active_activity"]
    command_status = str(latest_command_status.get("status") or "").strip()
    requested_command_type = str(
        latest_command_status.get("requested_command_type")
        or latest_command_status.get("command_type")
        or ""
    ).strip()

    if control_mode == "emergency_stop":
        return "비상 정지"
    if control_mode == "paused":
        return "일시정지"
    if command_status in {"pending", "running"}:
        if requested_command_type == "return_home":
            return "홈 복귀 중"
        if requested_command_type in {"move_to_zone", "navigate_to_pose"}:
            return "수동 이동 중"
        if requested_command_type in {"pause_patrol", "pause_motion", "pause"}:
            return "일시정지 전환 중"
        if requested_command_type in {"resume_patrol", "resume_motion", "resume"}:
            return "재개 중"
        if requested_command_type == "emergency_stop":
            return "비상 정지 전환 중"
        return "명령 실행 중"
    if active_activity == "patrol":
        return "순찰 중"
    if active_activity == "manual_navigation":
        return "수동 이동 중"
    if pose_payload["source"] == "live" and float(pose_payload["linear_speed_mps"]) > 0.05:
        return "이동 중"
    return "대기" if pose_payload["source"] == "live" else "준비 데이터"


def _resolve_mode_label(control_state: dict[str, Any]) -> str:
    control_mode = control_state["mode"]
    active_activity = control_state["active_activity"]
    if control_mode == "emergency_stop":
        return "비상 정지"
    if control_mode == "paused":
        return "일시정지"
    if active_activity == "manual_navigation":
        return "수동 제어"
    if active_activity == "patrol":
        return "자율 순찰"
    return "정상"


def _resolve_mission_state(
    *,
    pose_payload: dict[str, Any],
    control_state: dict[str, Any],
    latest_command_status: dict[str, Any],
) -> str:
    command_status = str(latest_command_status.get("status") or "").strip()
    if command_status in {"pending", "running"}:
        return str(latest_command_status.get("message") or "").strip() or "명령 실행 중"
    if control_state["mode"] in {"paused", "emergency_stop"}:
        return str(control_state.get("message") or "").strip() or "제어 latch 활성화"
    if control_state["active_activity"] == "patrol":
        return "순찰 실행 중"
    if control_state["active_activity"] == "manual_navigation":
        return "수동 이동 중"
    if pose_payload["source"] == "live":
        return "대기 중"
    return "live pose 연동 대기"


def _status_updated_at(
    *,
    pose_payload: dict[str, Any],
    control_state: dict[str, Any],
    latest_command_status: dict[str, Any],
) -> str:
    for value in (
        latest_command_status.get("updated_at"),
        control_state.get("updated_at"),
        pose_payload.get("updated_at"),
    ):
        if isinstance(value, str) and value.strip():
            return value
    return datetime.now(timezone.utc).isoformat()


def _fallback_pose_payload(map_id: str) -> dict[str, Any]:
    updated_at = datetime.now(timezone.utc).isoformat()
    current_zone_id = "farm_01"
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
    pose_snapshot_path = _pose_snapshot_path()

    try:
        payload = json.loads(pose_snapshot_path.read_text(encoding="utf-8"))
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
    control_state = _safe_control_state_payload()
    latest_command_status = _safe_latest_command_status_payload(control_state)
    db_context = _load_db_robot_context(pose_payload.get("robot_id"))
    source = (
        "live"
        if pose_payload["source"] == "live"
        or control_state["available"]
        or latest_command_status["available"]
        else "fallback"
    )
    status = _resolve_status_label(
        pose_payload=pose_payload,
        control_state=control_state,
        latest_command_status=latest_command_status,
    )
    mission_state = _resolve_mission_state(
        pose_payload=pose_payload,
        control_state=control_state,
        latest_command_status=latest_command_status,
    )
    if source == "fallback" and db_context:
        status = _resolve_db_status_label(db_context)
        mission_state = _resolve_db_mission_state(db_context)
    note = (
        str(control_state.get("message") or "").strip()
        if control_state["mode"] in {"paused", "emergency_stop"}
        else str(latest_command_status.get("message") or "").strip()
        if str(latest_command_status.get("status") or "").strip() in {"pending", "running", "failed"}
        else pose_payload["note"]
    )
    current_zone_id = (
        str(db_context.get("current_zone_id") or "").strip() or pose_payload["current_zone_id"]
    )
    zone_label = (
        str(db_context.get("zone_label") or "").strip()
        or ZONE_LABELS.get(current_zone_id, pose_payload["current_zone_label"])
    )
    battery_level = db_context.get("battery_level")
    battery = None
    if isinstance(battery_level, (int, float)):
        battery = f"{float(battery_level):.0f}%"

    return {
        "source": source,
        "robot_id": str(db_context.get("robot_name") or pose_payload["robot_id"]),
        "status": status,
        "mission_state": mission_state,
        "mode": _resolve_mode_label(control_state),
        "battery": battery,
        "battery_level": battery_level,
        "battery_eta": None,
        "speed_mps": f"{pose_payload['linear_speed_mps']:.2f}m/s",
        "speed_mps_value": float(pose_payload["linear_speed_mps"]),
        "mission_progress_pct": db_context.get("mission_progress_pct"),
        "eta": None,
        "waypoint_id": None,
        "next_waypoint": None,
        "next_target_crop_id": None,
        "current_zone_id": current_zone_id,
        "zone_label": zone_label,
        "updated_at": _status_updated_at(
            pose_payload=pose_payload,
            control_state=control_state,
            latest_command_status=latest_command_status,
        ),
        "note": note,
        "pose_source": pose_payload["source"],
        "current_control_state": control_state,
        "control_mode": control_state["mode"],
        "control_is_latched": control_state["is_latched"],
        "control_active_activity": control_state["active_activity"],
        "control_blocking_reason": control_state["blocking_reason"],
        "control_resume_available": control_state["resume_available"],
        "control_message": control_state["message"],
        "control_updated_at": control_state["updated_at"],
        "latest_command": latest_command_status,
        "latest_command_id": latest_command_status.get("command_id"),
        "latest_command_status": latest_command_status.get("status"),
        "latest_command_type": latest_command_status.get("command_type"),
        "latest_requested_command_type": latest_command_status.get("requested_command_type"),
        "latest_command_message": latest_command_status.get("message"),
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
