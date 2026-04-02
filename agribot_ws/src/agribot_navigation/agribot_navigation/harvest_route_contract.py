# 이 모듈은 자율주행과 경로 계획 패키지에서 harvest route contract 기능을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True)
class HarvestRouteRequest:
    # harvest 경로 요청 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    tomato_id: str
    plant_id: str = ''
    mission_id: str = ''
    requested_by: str = ''
    trigger: str = 'manual_request'
    inspect_waypoint_id: str = ''
    inspect_waypoint_ids: tuple[str, ...] = ()


def _normalize_text(value: Any) -> str:
    # text를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    if value is None:
        return ''
    normalized = str(value).strip()
    if normalized.lower() in {'none', 'null'}:
        return ''
    return normalized


def parse_harvest_route_request(
    raw_data: str,
    *,
    default_trigger: str = 'manual_request',
) -> HarvestRouteRequest | None:
    # harvest 경로 요청 데이터를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    payload_text = str(raw_data).strip()
    if not payload_text:
        return None

    if not payload_text.startswith('{'):
        return HarvestRouteRequest(
            tomato_id=payload_text,
            trigger=default_trigger,
        )

    try:
        raw_payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(raw_payload, dict):
        return None

    tomato_id = (
        _normalize_text(raw_payload.get('tomato_id'))
        or _normalize_text(raw_payload.get('fruit_id'))
        or _normalize_text(raw_payload.get('target_id'))
    )
    if not tomato_id:
        return None

    return HarvestRouteRequest(
        tomato_id=tomato_id,
        plant_id=_normalize_text(raw_payload.get('plant_id')),
        mission_id=_normalize_text(raw_payload.get('mission_id')),
        requested_by=_normalize_text(raw_payload.get('requested_by')),
        trigger=_normalize_text(raw_payload.get('trigger')) or default_trigger,
        inspect_waypoint_id=_normalize_text(raw_payload.get('inspect_waypoint_id')),
        inspect_waypoint_ids=tuple(
            str(item).strip()
            for item in raw_payload.get('inspect_waypoint_ids', [])
            if str(item).strip()
        ),
    )
