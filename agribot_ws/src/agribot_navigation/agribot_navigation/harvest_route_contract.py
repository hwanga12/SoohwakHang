"""harvest_route_node 요청 payload를 한 계약으로 파싱하기 위한 보조 모듈."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True)
class HarvestRouteRequest:
    tomato_id: str
    plant_id: str = ''
    mission_id: str = ''
    requested_by: str = ''
    trigger: str = 'manual_request'


def _normalize_text(value: Any) -> str:
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
    )
