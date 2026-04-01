# 이 모듈은 로봇 이동 미리보기 데이터를 읽어온다.
from __future__ import annotations

import json
from typing import Any

from robot_runtime_state_service import navigation_path_snapshot_file_path


def _sanitize_map_id(map_id: str | None) -> str:
    # sanitize 지도 id 정보를 계산해 반환한다.
    normalized = str(map_id or '').strip()
    return normalized or 'farm_map'


def _fallback_navigation_preview_payload(map_id: str) -> dict[str, Any]:
    # 대체값 주행 미리보기 페이로드 정보를 계산해 반환한다.
    return {
        'source': 'fallback',
        'available': False,
        'robot_id': 'AGR-02',
        'map_id': map_id,
        'frame_id': 'map',
        'preview_kind': 'none',
        'points': [],
        'active_topic': None,
        'updated_at': '',
        'note': '실시간 예상 경로 스냅샷이 아직 없습니다.',
    }


def _normalize_navigation_preview_points(raw_points: Any) -> list[dict[str, Any]]:
    # navigation 미리보기 데이터 points를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    if not isinstance(raw_points, list):
        return []

    normalized_points: list[dict[str, Any]] = []
    for item in raw_points:
        if not isinstance(item, dict):
            continue
        try:
            normalized_points.append(
                {
                    'x': float(item.get('x', 0.0)),
                    'y': float(item.get('y', 0.0)),
                    'z': float(item.get('z', 0.0)),
                    'yaw': float(item.get('yaw', 0.0)),
                    'frame_id': str(item.get('frame_id', 'map')).strip() or 'map',
                }
            )
        except (TypeError, ValueError):
            continue

    return normalized_points


def read_navigation_preview_payload(map_id: str | None = None) -> dict[str, Any]:
    # navigation 미리보기 데이터 payload를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    resolved_map_id = _sanitize_map_id(map_id)
    snapshot_path = navigation_path_snapshot_file_path()

    try:
        payload = json.loads(snapshot_path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return _fallback_navigation_preview_payload(resolved_map_id)
    except (OSError, json.JSONDecodeError):
        return _fallback_navigation_preview_payload(resolved_map_id)

    points = _normalize_navigation_preview_points(payload.get('active_points'))
    preview_kind = str(payload.get('preview_kind', 'none')).strip() or 'none'
    active_topic = str(payload.get('active_topic', '')).strip() or None
    updated_at = str(payload.get('updated_at', '')).strip()

    if len(points) < 2:
        fallback = _fallback_navigation_preview_payload(resolved_map_id)
        fallback['note'] = '활성 예상 경로가 없어 preview 선을 숨깁니다.'
        return fallback

    return {
        'source': 'live',
        'available': True,
        'robot_id': str(payload.get('robot_id', 'AGR-02')).strip() or 'AGR-02',
        'map_id': str(payload.get('map_id', resolved_map_id)).strip() or resolved_map_id,
        'frame_id': str(payload.get('frame_id', 'map')).strip() or 'map',
        'preview_kind': preview_kind,
        'points': points,
        'active_topic': active_topic,
        'updated_at': updated_at,
        'note': 'Nav2가 계산한 현재 예상 주행 경로를 반영 중입니다.',
    }
