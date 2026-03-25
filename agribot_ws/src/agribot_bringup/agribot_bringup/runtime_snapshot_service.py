import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory

DEFAULT_MAP_ID = 'farm_map'
DEFAULT_FRAME_ID = 'map'
DEFAULT_RUNTIME_DIR = Path(os.environ.get('AGRIBOT_RUNTIME_DIR', '/tmp/agribot_runtime'))
POSE_SNAPSHOT_FILENAME = 'robot_pose_snapshot.json'
SEMANTIC_LAYER_SNAPSHOT_FILENAME = 'robot_map_layers_snapshot.json'
MANUAL_COMMAND_FILENAME = 'robot_manual_command.json'
MANUAL_COMMAND_STATUS_FILENAME = 'robot_manual_command_status.json'


def runtime_dir_from_env() -> Path:
    runtime_dir = Path(os.environ.get('AGRIBOT_RUNTIME_DIR', str(DEFAULT_RUNTIME_DIR)))
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


def pose_snapshot_path(runtime_dir: Path | None = None) -> Path:
    return (runtime_dir or runtime_dir_from_env()) / POSE_SNAPSHOT_FILENAME


def semantic_layer_snapshot_path(runtime_dir: Path | None = None) -> Path:
    return (runtime_dir or runtime_dir_from_env()) / SEMANTIC_LAYER_SNAPSHOT_FILENAME


def manual_command_path(runtime_dir: Path | None = None) -> Path:
    return (runtime_dir or runtime_dir_from_env()) / MANUAL_COMMAND_FILENAME


def manual_command_status_path(runtime_dir: Path | None = None) -> Path:
    return (runtime_dir or runtime_dir_from_env()) / MANUAL_COMMAND_STATUS_FILENAME


def _package_share(package_name: str) -> Path:
    share_path = Path(get_package_share_directory(package_name))
    if share_path.exists():
        return share_path

    source_path = _source_package_root(package_name)
    if source_path is not None:
        return source_path

    return share_path


def _source_package_root(package_name: str) -> Path | None:
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        candidate = parent / 'src' / package_name
        if candidate.exists():
            return candidate
        candidate = parent / 'agribot_ws' / 'src' / package_name
        if candidate.exists():
            return candidate
    return None


def _resolve_package_file(package_name: str, *relative_parts: str) -> Path:
    share_path = _package_share(package_name)
    candidate = share_path.joinpath(*relative_parts)
    if candidate.exists():
        return candidate

    source_root = _source_package_root(package_name)
    if source_root is None:
        return candidate

    fallback = source_root.joinpath(*relative_parts)
    return fallback if fallback.exists() else candidate


def _clean_yaml_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.split('#', 1)[0].rstrip()
        if line.strip():
            lines.append(line)
    return lines


def _parse_scalar(value: str) -> Any:
    trimmed = value.strip().strip('"').strip("'")
    if not trimmed:
        return ''
    if trimmed in {'true', 'false'}:
        return trimmed == 'true'
    try:
        if '.' in trimmed or 'e' in trimmed.lower():
            return float(trimmed)
        return int(trimmed)
    except ValueError:
        return trimmed


def _parse_pose_text(value: str) -> dict[str, float]:
    tokens = [float(token) for token in value.split()]
    while len(tokens) < 6:
        tokens.append(0.0)
    return {
        'x': tokens[0],
        'y': tokens[1],
        'z': tokens[2],
        'roll': tokens[3],
        'pitch': tokens[4],
        'yaw': tokens[5],
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
        tokens.append(raw[start:index].decode('ascii'))

    if len(tokens) < 4:
        raise ValueError(f'{image_path.name} 헤더를 읽지 못했습니다.')

    return int(tokens[1]), int(tokens[2])


def read_map_metadata(map_id: str = DEFAULT_MAP_ID) -> dict[str, Any]:
    yaml_path = _resolve_package_file('agribot_navigation', 'maps', f'{map_id}.yaml')
    if not yaml_path.exists():
        raise FileNotFoundError(f'{yaml_path} 파일을 찾지 못했습니다.')

    metadata: dict[str, Any] = {}
    lines = _clean_yaml_lines(yaml_path)
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if ':' not in stripped:
            index += 1
            continue

        key, raw_value = stripped.split(':', 1)
        key = key.strip()
        raw_value = raw_value.strip()

        if key == 'origin':
            origin_values: list[float] = []
            index += 1
            while index < len(lines) and lines[index].lstrip().startswith('-'):
                origin_values.append(float(lines[index].split('-', 1)[1].strip()))
                index += 1
            metadata['origin'] = {
                'x': origin_values[0] if len(origin_values) > 0 else 0.0,
                'y': origin_values[1] if len(origin_values) > 1 else 0.0,
                'yaw': origin_values[2] if len(origin_values) > 2 else 0.0,
            }
            continue

        metadata[key] = _parse_scalar(raw_value)
        index += 1

    image_path = yaml_path.with_name(str(metadata.get('image', f'{map_id}.pgm')))
    width, height = _read_pgm_dimensions(image_path)

    return {
        'map_id': map_id,
        'frame_id': DEFAULT_FRAME_ID,
        'image_path': str(image_path),
        'resolution': float(metadata.get('resolution', 0.05)),
        'origin': metadata.get('origin', {'x': 0.0, 'y': 0.0, 'yaw': 0.0}),
        'width': width,
        'height': height,
    }


def _load_crop_instances() -> dict[str, Any]:
    crop_instances_path = _resolve_package_file('agribot_description', 'config', 'crop_instances.yaml')
    lines = _clean_yaml_lines(crop_instances_path)
    data: dict[str, Any] = {
        'plants': [],
        'tomatoes': [],
    }
    section: str | None = None
    current_item: dict[str, Any] | None = None
    current_pose: dict[str, Any] | None = None

    for line in lines:
        indent = len(line) - len(line.lstrip(' '))
        stripped = line.strip()

        if indent == 0 and stripped.endswith(':'):
            key = stripped[:-1]
            section = key if key in {'plants', 'tomatoes'} else None
            current_item = None
            current_pose = None
            continue

        if section not in {'plants', 'tomatoes'}:
            continue

        if stripped.startswith('- '):
            current_item = {}
            current_pose = None
            data[section].append(current_item)
            stripped = stripped[2:]
            if ':' in stripped:
                key, raw_value = stripped.split(':', 1)
                current_item[key.strip()] = _parse_scalar(raw_value)
            continue

        if current_item is None:
            continue

        if stripped == 'pose:':
            current_pose = {}
            current_item['pose'] = current_pose
            continue

        if current_pose is not None and indent >= 4 and ':' in stripped:
            key, raw_value = stripped.split(':', 1)
            current_pose[key.strip()] = _parse_scalar(raw_value)
            continue

        current_pose = None
        if ':' in stripped:
            key, raw_value = stripped.split(':', 1)
            current_item[key.strip()] = _parse_scalar(raw_value)

    return data


def _load_iot_devices() -> dict[str, dict[str, Any]]:
    iot_devices_path = _resolve_package_file('agribot_iot', 'config', 'iot_devices.yaml')
    lines = _clean_yaml_lines(iot_devices_path)
    current_zone_id = ''
    in_devices = False
    current_device: dict[str, Any] | None = None
    devices: dict[str, dict[str, Any]] = {}

    for line in lines:
        indent = len(line) - len(line.lstrip(' '))
        stripped = line.strip()

        if indent == 2 and stripped.startswith('- zone_id:'):
            current_zone_id = stripped.split(':', 1)[1].strip()
            in_devices = False
            current_device = None
            continue

        if indent == 4 and stripped == 'devices:':
            in_devices = True
            current_device = None
            continue

        if not in_devices:
            continue

        if indent == 6 and stripped.startswith('- device_id:'):
            device_id = stripped.split(':', 1)[1].strip()
            current_device = {
                'device_id': device_id,
                'zone_id': current_zone_id,
            }
            devices[device_id] = current_device
            continue

        if current_device is None:
            continue

        if indent >= 8 and ':' in stripped and not stripped.startswith('- '):
            key, raw_value = stripped.split(':', 1)
            current_device[key.strip()] = _parse_scalar(raw_value)

    return devices


def _load_world_semantics() -> dict[str, Any]:
    world_path = _resolve_package_file('agribot_description', 'worlds', 'farm_world.sdf')
    root = ET.parse(world_path).getroot()
    world = root.find('world')
    if world is None:
        raise ValueError('farm_world.sdf에서 world 노드를 찾지 못했습니다.')

    row_guides: list[dict[str, Any]] = []
    sprinklers: list[dict[str, Any]] = []

    crop_rows = world.find("./model[@name='crop_rows']")
    if crop_rows is not None:
        for index, collision in enumerate(crop_rows.findall('./link/collision'), start=1):
            pose = _parse_pose_text(collision.findtext('pose', '0 0 0 0 0 0'))
            row_guides.append({
                'id': f'row-{index}',
                'axis': 'x',
                'value': pose['x'],
                'label': f'재배열 {index}',
            })

    for include in world.findall('include'):
        name = include.findtext('name', '')
        uri = include.findtext('uri', '')
        if not name.startswith('sprinkler_') and not uri.endswith('sprinkler'):
            continue

        pose = _parse_pose_text(include.findtext('pose', '0 0 0 0 0 0'))
        sprinklers.append({
            'id': name or f'sprinkler_{len(sprinklers)}',
            'position': {
                'x': pose['x'],
                'y': pose['y'],
                'z': pose['z'],
            },
        })

    return {
        'bounds': {
            'min_x': -10.0,
            'max_x': 10.0,
            'min_y': -10.0,
            'max_y': 10.0,
        },
        'row_guides': row_guides,
        'sprinklers': sprinklers,
    }


def _build_lane_guides(plant_positions: list[dict[str, float]]) -> list[dict[str, Any]]:
    y_values = sorted({round(position['y'], 3) for position in plant_positions})
    if not y_values:
        return []

    return [
        {'id': 'lane-bottom-1', 'axis': 'y', 'value': y_values[0] - 2.0, 'label': '하단 통로'},
        {
            'id': 'lane-bottom-2',
            'axis': 'y',
            'value': (y_values[0] + y_values[1]) / 2.0,
            'label': '하단 점검 라인',
        },
        {'id': 'lane-mid', 'axis': 'y', 'value': 0.0, 'label': '중앙 급수 라인'},
        {
            'id': 'lane-top-1',
            'axis': 'y',
            'value': (y_values[-2] + y_values[-1]) / 2.0,
            'label': '상단 점검 라인',
        },
        {'id': 'lane-top-2', 'axis': 'y', 'value': y_values[-1] + 2.0, 'label': '상단 통로'},
    ]


def build_semantic_layer_snapshot(map_id: str = DEFAULT_MAP_ID) -> dict[str, Any]:
    crop_instances = _load_crop_instances()
    world = _load_world_semantics()
    devices = _load_iot_devices()
    map_metadata = read_map_metadata(map_id)

    tomato_lookup = {
        tomato['plant_id']: tomato
        for tomato in crop_instances.get('tomatoes', [])
        if isinstance(tomato, dict) and tomato.get('plant_id')
    }
    watering_device = devices.get('farm_01_watering', {})

    plant_assets: list[dict[str, Any]] = []
    plant_positions: list[dict[str, float]] = []
    for plant in crop_instances.get('plants', []):
        if not isinstance(plant, dict):
            continue

        pose = plant.get('pose', {})
        x_value = float(pose.get('x', 0.0))
        y_value = float(pose.get('y', 0.0))
        plant_positions.append({'x': x_value, 'y': y_value})
        plant_id = str(plant.get('plant_id', ''))
        linked_tomato = tomato_lookup.get(plant_id, {})

        plant_assets.append({
            'id': plant_id,
            'linked_id': linked_tomato.get('tomato_id'),
            'kind': 'plant',
            'label': str(plant.get('display_name', plant_id)),
            'short_label': plant_id[-2:],
            'zone_id': str(plant.get('zone_id', 'farm_01')),
            'description': '작물 관찰 및 수확 후보 탐색 대상 식물',
            'position': {
                'x': x_value,
                'y': y_value,
                'z': float(pose.get('z', 0.0)),
            },
            'status': 'normal',
        })

    sprinkler_assets = [
        {
            'id': sprinkler['id'],
            'linked_id': watering_device.get('device_id'),
            'kind': 'sprinkler',
            'label': f'급수 포인트 {index + 1}',
            'short_label': f'W{index + 1}',
            'zone_id': watering_device.get('zone_id', 'farm_01'),
            'description': f"{watering_device.get('display_name', 'Watering Pump')}와 연결된 급수 포인트",
            'position': sprinkler['position'],
            'status': 'normal',
        }
        for index, sprinkler in enumerate(world['sprinklers'])
    ]

    return {
        'source': 'static_config',
        'map_id': map_id,
        'frame_id': map_metadata['frame_id'],
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'bounds': world['bounds'],
        'row_guides': world['row_guides'],
        'lane_guides': _build_lane_guides(plant_positions),
        'assets': plant_assets + sprinkler_assets,
        'counts': {
            'plants': len(plant_assets),
            'sprinklers': len(sprinkler_assets),
        },
        'device_bindings': {
            'watering': watering_device,
        },
    }


def build_pose_snapshot_payload(
    *,
    map_id: str,
    robot_id: str,
    x_value: float,
    y_value: float,
    z_value: float,
    yaw_value: float,
    frame_id: str,
    linear_speed_mps: float,
    source_mode: str,
) -> dict[str, Any]:
    timestamp = time.time()
    return {
        'robot_id': robot_id,
        'map_id': map_id,
        'pose': {
            'x': float(x_value),
            'y': float(y_value),
            'z': float(z_value),
            'yaw': float(yaw_value),
            'frame_id': frame_id,
        },
        'linear_speed_mps': float(linear_speed_mps),
        'source_mode': source_mode,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'timestamp': timestamp,
    }


def build_manual_command_status_payload(
    *,
    command_id: str | None,
    command_type: str | None,
    robot_id: str,
    status: str,
    message: str,
    map_id: str = DEFAULT_MAP_ID,
    requested_by: str = '',
    frame_id: str = DEFAULT_FRAME_ID,
    error: str | None = None,
    target_pose: dict[str, Any] | None = None,
    home_waypoint_id: str | None = None,
    received_at: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    updated_at = datetime.now(timezone.utc).isoformat()
    return {
        'command_id': command_id,
        'command_type': command_type,
        'robot_id': robot_id,
        'requested_by': requested_by or None,
        'map_id': map_id,
        'frame_id': frame_id,
        'status': status,
        'message': message,
        'error': error,
        'target_pose': target_pose,
        'home_waypoint_id': home_waypoint_id,
        'received_at': received_at,
        'started_at': started_at,
        'completed_at': completed_at,
        'updated_at': updated_at,
    }


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'{path.name} 최상위 payload는 JSON object여야 합니다.')
    return payload


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + '.tmp')
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temp_path.replace(path)
