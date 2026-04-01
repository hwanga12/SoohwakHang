# 이 모듈은 수확 런타임 상태와 기록을 읽어온다.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from robot_runtime_state_service import (
    build_idle_mission_status_payload,
    harvest_action_status_file_path,
    harvest_action_status_record_file_path,
    harvest_basket_state_file_path,
    harvest_event_record_file_path,
    harvest_failure_alert_file_path,
    harvest_latest_event_file_path,
    iso_now,
    read_json_object,
    runtime_dir_from_env,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
CROP_INSTANCES_PATH = (
    REPO_ROOT
    / "agribot_ws"
    / "src"
    / "agribot_description"
    / "config"
    / "crop_instances.yaml"
)
HARVEST_EVENT_DIRNAME = "harvest_events"


def _read_optional_json(path: Path) -> dict[str, Any]:
    # optional JSON 데이터를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    if not path.exists():
        return {}
    try:
        return read_json_object(path)
    except Exception:
        return {}


def _normalize_action_status(value: Any) -> str:
    # action 상태를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(value).strip().lower()
    if normalized in {"planned", "pending"}:
        return "pending"
    if normalized == "running":
        return "running"
    if normalized in {"completed", "complete", "succeeded"}:
        return "succeeded"
    if normalized in {"failed", "error"}:
        return "failed"
    if normalized in {"canceled", "cancelled"}:
        return "canceled"
    return "idle"


def _clean_yaml_lines(path: Path) -> list[str]:
    # clean yaml lines 정보를 계산해 반환한다.
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if line.strip():
            lines.append(line)
    return lines


def _parse_scalar(value: str) -> Any:
    # scalar를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
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


def _load_ready_tomato_ids() -> set[str]:
    # ready tomato ID 목록를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    if not CROP_INSTANCES_PATH.exists():
        return set()

    lines = _clean_yaml_lines(CROP_INSTANCES_PATH)
    section: str | None = None
    current_item: dict[str, Any] | None = None
    ready_ids: set[str] = set()

    for line in lines:
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and stripped.endswith(":"):
            section = stripped[:-1]
            current_item = None
            continue

        if section != "tomatoes":
            continue

        if stripped.startswith("- "):
            if current_item and current_item.get("ready_to_harvest") and current_item.get("tomato_id"):
                ready_ids.add(str(current_item["tomato_id"]))
            current_item = {}
            stripped = stripped[2:]
            if ":" in stripped:
                key, raw_value = stripped.split(":", 1)
                current_item[key.strip()] = _parse_scalar(raw_value)
            continue

        if current_item is None or ":" not in stripped:
            continue

        key, raw_value = stripped.split(":", 1)
        current_item[key.strip()] = _parse_scalar(raw_value)

    if current_item and current_item.get("ready_to_harvest") and current_item.get("tomato_id"):
        ready_ids.add(str(current_item["tomato_id"]))
    return ready_ids


def _sort_key(payload: dict[str, Any]) -> str:
    # sort key 정보를 계산해 반환한다.
    return str(
        payload.get("occurred_at")
        or payload.get("updated_at")
        or payload.get("recorded_at")
        or ""
    )


def _read_event_payloads() -> list[dict[str, Any]]:
    # 이벤트 payloads를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    runtime_dir = runtime_dir_from_env()
    event_dir = runtime_dir / HARVEST_EVENT_DIRNAME
    payloads: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()

    if event_dir.exists():
        for path in sorted(event_dir.glob("*.json"), reverse=True):
            payload = _read_optional_json(path)
            event_id = str(payload.get("event_id") or "").strip()
            if not event_id or event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            payloads.append(payload)

    latest_payload = _read_optional_json(harvest_latest_event_file_path())
    latest_event_id = str(latest_payload.get("event_id") or "").strip()
    if latest_event_id and latest_event_id not in seen_event_ids:
        payloads.append(latest_payload)

    payloads.sort(key=_sort_key, reverse=True)
    return payloads


def read_harvest_action_status_payload(mission_id: str | None = None) -> dict[str, Any] | None:
    # harvest action 상태 payload를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    if mission_id:
        record_payload = _read_optional_json(harvest_action_status_record_file_path(mission_id))
        if record_payload:
            return record_payload

    latest_payload = _read_optional_json(harvest_action_status_file_path())
    if not latest_payload:
        return None
    if mission_id and str(latest_payload.get("mission_id") or "").strip() != str(mission_id).strip():
        return None
    return latest_payload


def read_harvest_history_payload(limit: int = 20) -> list[dict[str, Any]]:
    # harvest 이력 payload를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    events = _read_event_payloads()
    action_status = read_harvest_action_status_payload()
    rows: list[dict[str, Any]] = []

    if action_status and _normalize_action_status(action_status.get("status") or action_status.get("state")) in {"pending", "running"}:
        mission_id = str(action_status.get("mission_id") or "").strip()
        current_phase = str(action_status.get("current_phase") or "").strip()
        fruit_id = str(action_status.get("target_id") or "").strip()
        rows.append(
            {
                "id": mission_id or "harvest-active",
                "route_id": mission_id or "harvest-active",
                "batch_id": mission_id or "harvest-active",
                "name": fruit_id or "수확 진행 중",
                "summary": (
                    str(action_status.get("detail_message") or "").strip()
                    or f"{fruit_id or '수확 대상'} 접근 및 적재 시퀀스를 진행 중입니다."
                ),
                "detail": str(action_status.get("detail_message") or "").strip(),
                "state": "진행 중",
                "status": "running",
                "mission_id": mission_id,
                "fruit_id": fruit_id,
                "plant_id": str(action_status.get("plant_id") or "").strip(),
                "current_phase": current_phase,
                "updated_at": str(action_status.get("updated_at") or "").strip() or iso_now(),
            }
        )

    for payload in events[:limit]:
        mission_id = str(payload.get("mission_id") or "").strip()
        fruit_id = str(payload.get("fruit_id") or "").strip()
        plant_id = str(payload.get("plant_id") or "").strip()
        success = bool(payload.get("success"))
        basket_count = int(payload.get("basket_count") or 0)
        occurred_at = str(payload.get("occurred_at") or "").strip()
        rows.append(
            {
                "id": str(payload.get("event_id") or mission_id or fruit_id or "harvest-event").strip(),
                "route_id": mission_id or fruit_id or "harvest-history",
                "batch_id": mission_id or fruit_id or "harvest-history",
                "name": fruit_id or "수확 이벤트",
                "summary": (
                    f"{fruit_id or '수확 대상'} 수확 {'성공' if success else '실패'}"
                    f" · 바구니 {basket_count}개 적재"
                ),
                "detail": (
                    f"{plant_id or '식물 미상'}에서 {fruit_id or 'fruit 미상'}를 "
                    f"{'성공적으로 적재했습니다.' if success else str(payload.get('failure_reason') or '수확에 실패했습니다.')}"
                ),
                "state": "완료" if success else "실패",
                "status": "succeeded" if success else "failed",
                "mission_id": mission_id,
                "fruit_id": fruit_id,
                "plant_id": plant_id,
                "basket_count": basket_count,
                "harvested_at": occurred_at,
                "failure_reason": str(payload.get("failure_reason") or "").strip(),
                "success": success,
            }
        )

    return rows[:limit]


def read_harvest_stats_payload() -> dict[str, Any]:
    # harvest stats payload를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    basket_state = _read_optional_json(harvest_basket_state_file_path())
    latest_event = _read_optional_json(harvest_latest_event_file_path())
    action_status = read_harvest_action_status_payload() or {}
    failure_alert = _read_optional_json(harvest_failure_alert_file_path())
    events = _read_event_payloads()
    ready_tomato_ids = _load_ready_tomato_ids()

    successful_events = [payload for payload in events if bool(payload.get("success"))]
    failed_events = [payload for payload in events if payload.get("success") is False]
    latest_successful_event = successful_events[0] if successful_events else {}
    harvested_fruit_ids = {
        str(payload.get("fruit_id") or "").strip()
        for payload in successful_events
        if str(payload.get("fruit_id") or "").strip()
    }

    basket_count = int(
        basket_state.get("basket_count")
        or latest_successful_event.get("basket_count")
        or len(basket_state.get("loaded_fruit_ids") or [])
        or 0
    )
    remaining_ready_count = int(
        basket_state.get("remaining_ready_count")
        if basket_state.get("remaining_ready_count") is not None
        else max(0, len(ready_tomato_ids) - len(harvested_fruit_ids))
    )
    last_harvested_fruit_id = str(
        basket_state.get("last_harvested_fruit_id")
        or latest_successful_event.get("fruit_id")
        or ""
    ).strip()
    total_events = len(successful_events) + len(failed_events)
    success_rate = (
        "0.0%"
        if total_events == 0
        else f"{(len(successful_events) / total_events) * 100:.1f}%"
    )
    current_phase = str(action_status.get("current_phase") or "").strip()
    mission_status = _normalize_action_status(action_status.get("status") or action_status.get("state"))

    return {
        "source": "runtime_file",
        "today_harvest_kg": f"{len(successful_events)}개",
        "today_weight_kg": f"{len(successful_events)}개",
        "basket_fill_rate": f"{basket_count}개 적재",
        "basket_state": (
            f"바구니 적재 {basket_count}개"
            + (f" · {current_phase}" if current_phase and mission_status in {"pending", "running"} else "")
        ),
        "success_rate": success_rate,
        "failed_count": f"{len(failed_events)}건",
        "next_swap_eta": "교체 권장" if basket_count >= 5 else f"ready {remaining_ready_count}개 남음",
        "basket_count": basket_count,
        "harvested_count": int(basket_state.get("harvested_count") or len(successful_events)),
        "remaining_ready_count": remaining_ready_count,
        "last_harvested_fruit_id": last_harvested_fruit_id,
        "last_event_id": str(basket_state.get("last_event_id") or latest_event.get("event_id") or "").strip(),
        "loaded_fruit_ids": list(basket_state.get("loaded_fruit_ids") or []),
        "mission_status": mission_status,
        "current_phase": current_phase,
        "active_mission_id": str(action_status.get("mission_id") or "").strip(),
        "active_target_id": str(action_status.get("target_id") or "").strip(),
        "detail_message": str(action_status.get("detail_message") or "").strip(),
        "failure_reason": (
            str(failure_alert.get("failure_reason") or "").strip()
            if mission_status == "failed"
            else ""
        ),
    }


def merge_mission_status_with_harvest_action(
    mission_id: str,
    base_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    # 여러 입력에서 얻은 미션 상태 with harvest action를 하나로 병합한다.
    action_payload = read_harvest_action_status_payload(mission_id)
    if action_payload is None:
        if base_payload is None:
            raise FileNotFoundError(f"mission status 파일을 찾지 못했습니다: {mission_id}")
        return base_payload

    merged = dict(base_payload or build_idle_mission_status_payload())
    normalized_status = _normalize_action_status(action_payload.get("status") or action_payload.get("state"))
    detail_message = str(action_payload.get("detail_message") or "").strip()

    merged.update(
        {
            "available": True,
            "mission_id": str(action_payload.get("mission_id") or merged.get("mission_id") or mission_id).strip(),
            "command_id": str(action_payload.get("mission_id") or merged.get("command_id") or mission_id).strip(),
            "mission_type": str(action_payload.get("mission_type") or merged.get("mission_type") or "HARVEST").strip(),
            "state": str(action_payload.get("state") or merged.get("state") or "").strip(),
            "current_phase": str(action_payload.get("current_phase") or "").strip(),
            "progress_pct": action_payload.get("progress_pct"),
            "retry_count": action_payload.get("retry_count"),
            "detail_message": detail_message or merged.get("detail_message"),
            "zone_id": str(action_payload.get("zone_id") or merged.get("zone_id") or "").strip(),
            "target_id": str(action_payload.get("target_id") or merged.get("target_id") or "").strip(),
            "status": normalized_status,
            "message": detail_message or merged.get("message"),
            "operator_message": detail_message or merged.get("operator_message"),
            "updated_at": str(action_payload.get("updated_at") or merged.get("updated_at") or iso_now()).strip(),
        }
    )

    if not merged.get("request_type"):
        merged["request_type"] = "harvest_target"
    if not merged.get("requested_type"):
        merged["requested_type"] = merged["request_type"]
    if not merged.get("fruit_id") and merged.get("target_id"):
        merged["fruit_id"] = merged["target_id"]
    if not merged.get("tomato_id") and merged.get("fruit_id"):
        merged["tomato_id"] = merged["fruit_id"]

    return merged
