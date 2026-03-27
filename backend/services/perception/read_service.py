from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import joinedload

from database import SessionLocal
from models import Alert, CropObservation, Plant, Zone
from robot_map_service import _load_crop_instances


REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_PUBLIC_DIR = REPO_ROOT / "frontend" / "public"
DEFAULT_BACKEND_RUNTIME_DIR = REPO_ROOT / "artifacts" / "runtime" / "backend"

LABEL_DISPLAY_MAP = {
    "healthy_leaf": "정상 잎",
    "ripe_tomato": "수확 가능 토마토",
    "tomato_powdery_mildew": "토마토 흰가루병",
    "tomato_powdery_mildew_disease": "토마토 흰가루병",
    "tomato_gray_mold": "토마토 잿빛곰팡이병",
    "tomato_gray_mold_disease": "토마토 잿빛곰팡이병",
    "tomato_blossom_end_rot": "토마토 칼슘 결핍",
    "tomato_calcium_deficiency": "토마토 칼슘 결핍",
    "tomato_calcium_deficiency_disease": "토마토 칼슘 결핍",
    "tomato_macro_npk_deficiency": "토마토 영양 결핍",
    "tomato_macro_npk_deficiency_disease": "토마토 영양 결핍",
    "tomato_fruit_cracking": "토마토 열과",
    "tomato_fruit_cracking_disease": "토마토 열과",
}


@dataclass(frozen=True)
class RuntimeObservationRecord:
    observation_id: str
    plant_id: str
    zone_id: str
    fruit_id: str
    finding_label: str
    display_label: str
    confidence: float
    reviewed_at: str
    image_url: str
    metadata_path: Path
    image_path: Path | None
    decision_source: str
    recommended_action: str
    detail: str
    severity: str
    acknowledged_at: str
    acknowledged_by: str


def _serialize_datetime(value: datetime | None) -> str:
    return "" if value is None else value.isoformat()


def _serialize_uuid(value: UUID | str | None) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plant_display_name(plant_id: str) -> str:
    suffix = plant_id.split("_")[-1] if plant_id else ""
    return f"토마토 식물 {suffix}" if suffix else plant_id


def _zone_label(zone: Zone | None) -> str:
    if zone is None:
        return "farm_01"
    return zone.name or zone.id


def _display_label(finding_label: str) -> str:
    normalized = finding_label.strip().lower()
    return LABEL_DISPLAY_MAP.get(normalized, finding_label)


@lru_cache(maxsize=1)
def _canonical_plant_positions() -> dict[str, dict[str, float]]:
    crop_instances = _load_crop_instances()
    positions: dict[str, dict[str, float]] = {}

    for plant in crop_instances.get("plants", []):
        plant_id = str(plant.get("plant_id") or "").strip()
        pose = plant.get("pose")
        if not plant_id or not isinstance(pose, dict):
            continue
        positions[plant_id] = {
            "x": float(pose.get("x", 0.0)),
            "y": float(pose.get("y", 0.0)),
            "z": float(pose.get("z", 0.0)),
        }

    return positions


def _plant_position(plant_id: str, fallback: dict[str, Any] | None) -> dict[str, Any]:
    canonical = _canonical_plant_positions().get(plant_id.strip())
    if canonical is not None:
        return canonical
    return fallback or {"x": 0.0, "y": 0.0, "z": 0.0}


def _health_percent(finding_label: str) -> int:
    normalized = finding_label.strip().lower()
    if normalized in {"healthy_leaf", "healthy", "normal"}:
        return 96
    if "powdery" in normalized or "gray_mold" in normalized:
        return 24
    if "calcium" in normalized or "blossom_end_rot" in normalized:
        return 46
    if "macro_npk" in normalized:
        return 54
    if "crack" in normalized:
        return 61
    return 72


def _api_image_url(image_url: str) -> str:
    return image_url.strip()


def _runtime_media_url(observation_id: str) -> str:
    return f"/api/v1/media/{observation_id}"


def _backend_runtime_dir() -> Path:
    return Path(
        os.environ.get("AGRIBOT_BACKEND_RUNTIME_DIR", str(DEFAULT_BACKEND_RUNTIME_DIR))
    ).expanduser()


def _resolve_local_media_path(image_url: str) -> Path | None:
    normalized = image_url.strip()
    if not normalized:
        return None
    candidate = Path(normalized).expanduser()
    if candidate.is_absolute() and candidate.exists():
        return candidate
    if normalized.startswith("/mock-images/"):
        public_path = FRONTEND_PUBLIC_DIR / normalized.removeprefix("/")
        if public_path.exists():
            return public_path
    relative_candidate = REPO_ROOT / normalized
    if relative_candidate.exists():
        return relative_candidate
    return None


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_runtime_image_path(metadata_path: Path, image_format: str) -> Path | None:
    normalized_format = str(image_format or "").strip().lstrip(".")
    if normalized_format:
        candidate = metadata_path.with_suffix(f".{normalized_format}")
        if candidate.exists():
            return candidate

    for candidate in metadata_path.parent.glob(f"{metadata_path.stem}.*"):
        if candidate.suffix.lower() == ".json":
            continue
        if candidate.exists():
            return candidate
    return None


def _runtime_detail(payload: dict[str, Any]) -> str:
    finding_label = str(
        payload.get("final_label")
        or payload.get("request", {}).get("preliminary_label")
        or ""
    ).strip().lower()
    if finding_label in {"healthy_leaf", "healthy", "normal"}:
        return "정상 생육 패턴이 확인되었습니다."
    if finding_label == "ripe_tomato":
        return "수확 가능한 토마토가 확인되었습니다."

    treatment_plan = payload.get("treatment_plan")
    dispatch_result = payload.get("dispatch_result")
    if isinstance(treatment_plan, dict):
        detail = str(treatment_plan.get("reason") or "").strip()
        if detail:
            return detail
    if isinstance(dispatch_result, dict):
        detail = str(dispatch_result.get("detail_message") or "").strip()
        if detail:
            return detail
        status = str(dispatch_result.get("status") or "").strip()
        if status:
            return status
    return ""


def _runtime_recommended_action(payload: dict[str, Any], finding_label: str) -> str:
    normalized = finding_label.strip().lower()
    if normalized in {"healthy_leaf", "healthy", "normal"}:
        return "추가 관찰 유지"
    if normalized == "ripe_tomato":
        return "수확 요청"

    treatment_plan = payload.get("treatment_plan")
    if isinstance(treatment_plan, dict) and bool(treatment_plan.get("action_required")):
        treatment_label = str(treatment_plan.get("treatment_label") or "").strip()
        if treatment_label:
            return treatment_label

    detail = _runtime_detail(payload)
    if detail:
        return detail
    if "disease" in finding_label or "powdery" in finding_label or "gray_mold" in finding_label:
        return "운영자 검토 필요"
    return "추가 관찰 유지"


def _runtime_severity(payload: dict[str, Any], finding_label: str) -> str:
    treatment_plan = payload.get("treatment_plan")
    if isinstance(treatment_plan, dict) and bool(treatment_plan.get("action_required")):
        return "warning"
    normalized = finding_label.strip().lower()
    if normalized in {"healthy_leaf", "ripe_tomato"}:
        return "info"
    if normalized:
        return "warning"
    return "info"


def _runtime_observation_records() -> list[RuntimeObservationRecord]:
    runtime_dir = _backend_runtime_dir()
    if not runtime_dir.exists():
        return []

    records: list[RuntimeObservationRecord] = []
    for metadata_path in sorted(runtime_dir.rglob("*.json"), reverse=True):
        payload = _read_json_file(metadata_path)
        if payload is None:
            continue

        observation_id = str(payload.get("observation_id") or "").strip()
        request = payload.get("request")
        if not observation_id or not isinstance(request, dict):
            continue

        finding_label = str(
            payload.get("final_label")
            or request.get("preliminary_label")
            or ""
        ).strip()
        image_path = _resolve_runtime_image_path(
            metadata_path,
            str(request.get("image_format") or ""),
        )

        records.append(
            RuntimeObservationRecord(
                observation_id=observation_id,
                plant_id=str(request.get("plant_id") or "").strip(),
                zone_id=str(request.get("zone_id") or "farm_01").strip(),
                fruit_id=str(request.get("fruit_id") or "").strip(),
                finding_label=finding_label,
                display_label=_display_label(finding_label),
                confidence=float(payload.get("final_confidence") or 0.0),
                reviewed_at=str(payload.get("reviewed_at") or "").strip(),
                image_url=_runtime_media_url(observation_id),
                metadata_path=metadata_path,
                image_path=image_path,
                decision_source=str(payload.get("decision_source") or "runtime_metadata").strip(),
                recommended_action=_runtime_recommended_action(payload, finding_label),
                detail=_runtime_detail(payload),
                severity=_runtime_severity(payload, finding_label),
                acknowledged_at=str(payload.get("acknowledged_at") or "").strip(),
                acknowledged_by=str(payload.get("acknowledged_by") or "").strip(),
            )
        )

    records.sort(key=lambda item: item.reviewed_at, reverse=True)
    return records


def _runtime_record_by_observation_id(observation_id: str) -> RuntimeObservationRecord | None:
    normalized_id = str(observation_id).strip()
    if not normalized_id:
        return None
    for record in _runtime_observation_records():
        if record.observation_id == normalized_id:
            return record
    return None


def _runtime_observation_item(record: RuntimeObservationRecord) -> dict[str, Any]:
    return {
        "id": record.observation_id,
        "class_name": record.finding_label,
        "label": record.finding_label,
        "display_label": record.display_label,
        "reviewed_at": record.reviewed_at,
        "image_url": record.image_url,
        "media_asset_id": record.observation_id,
        "decision_source": record.decision_source,
        "health_percent": _health_percent(record.finding_label),
        "detail": record.detail or record.recommended_action,
        "treatment_plan": {
            "reason": record.detail or record.recommended_action,
        },
    }


def _rollback_quietly(db: Any) -> None:
    try:
        db.rollback()
    except Exception:
        pass


class ObservationReadService:
    def list_alerts(self) -> list[dict[str, Any]]:
        runtime_records = _runtime_observation_records()
        runtime_rows = [
            {
                "id": record.observation_id,
                "observation_id": record.observation_id,
                "severity": record.severity,
                "level": record.severity,
                "title": record.display_label or record.finding_label,
                "message": record.detail or f"{record.display_label or record.finding_label} 감지",
                "detail": record.detail or record.recommended_action,
                "description": record.detail or record.recommended_action,
                "action": record.recommended_action,
                "location": f"{_plant_display_name(record.plant_id)} · {record.zone_id}",
                "zone_id": record.zone_id,
                "plant_id": record.plant_id,
                "label": record.finding_label,
                "display_label": record.display_label,
                "image_url": record.image_url,
                "detected_at": record.reviewed_at,
                "created_at": record.reviewed_at,
                "time": record.reviewed_at,
                "is_acked": bool(record.acknowledged_at),
                "acknowledged_at": record.acknowledged_at,
                "acknowledged_by": record.acknowledged_by,
            }
            for record in runtime_records
        ]

        db = SessionLocal()
        try:
            try:
                alerts = (
                    db.query(Alert)
                    .options(
                        joinedload(Alert.zone),
                        joinedload(Alert.plant),
                        joinedload(Alert.observation),
                    )
                    .order_by(Alert.detected_at.desc())
                    .all()
                )
            except OperationalError:
                _rollback_quietly(db)
                return runtime_rows
            runtime_ids = {row["id"] for row in runtime_rows}
            db_rows: list[dict[str, Any]] = []
            for alert in alerts:
                alert_id = _serialize_uuid(alert.id)
                if alert_id in runtime_ids:
                    continue
                observation = alert.observation
                finding_label = "" if observation is None else observation.finding_label
                image_url = alert.image_url or ("" if observation is None else observation.image_url) or ""
                db_rows.append(
                    {
                        "id": alert_id,
                        "observation_id": _serialize_uuid(alert.observation_id),
                        "severity": alert.severity,
                        "level": alert.severity,
                        "title": alert.message,
                        "message": alert.message,
                        "detail": alert.message,
                        "description": alert.message,
                        "action": (
                            "" if observation is None else observation.recommended_action
                        ) or "운영자 확인 필요",
                        "location": f"{_plant_display_name(alert.plant_id or '')} · {_zone_label(alert.zone)}",
                        "zone_id": alert.zone_id or "",
                        "plant_id": alert.plant_id or "",
                        "label": finding_label,
                        "display_label": _display_label(finding_label) if finding_label else "",
                        "image_url": _api_image_url(image_url),
                        "detected_at": _serialize_datetime(alert.detected_at),
                        "created_at": _serialize_datetime(alert.detected_at),
                        "time": _serialize_datetime(alert.detected_at),
                        "is_acked": alert.acknowledged_at is not None,
                        "acknowledged_at": _serialize_datetime(alert.acknowledged_at),
                        "acknowledged_by": alert.acknowledged_by or "",
                    }
                )
            return runtime_rows + db_rows
        finally:
            db.close()

    def list_plants(self) -> list[dict[str, Any]]:
        runtime_records = _runtime_observation_records()
        db = SessionLocal()
        try:
            try:
                plants = (
                    db.query(Plant)
                    .options(
                        joinedload(Plant.zone),
                        joinedload(Plant.fruits),
                        joinedload(Plant.observations),
                    )
                    .order_by(Plant.id.asc())
                    .all()
                )
            except OperationalError:
                _rollback_quietly(db)
                plants = []
            rows = {
                plant.id: {
                    "id": plant.id,
                    "plant_id": plant.id,
                    "name": _plant_display_name(plant.id),
                    "crop_name": plant.crop_name,
                    "target_fruit_id": "" if not plant.fruits else plant.fruits[0].id,
                    "fruit_id": "" if not plant.fruits else plant.fruits[0].id,
                    "zone_id": plant.zone_id,
                    "zone_label": _zone_label(plant.zone),
                    "position": _plant_position(plant.id, plant.position),
                    "last_observed_at": _serialize_datetime(plant.last_observed_at),
                    "health_score": None,
                    "health": 92,
                    "status": "관측 대기",
                    "latest_label": "",
                    "latest_display_label": "",
                    "latest_image_url": "",
                    "recommended_action": (
                        "수확 요청 가능"
                        if plant.ready_to_harvest
                        else "급수 우선 확인"
                        if plant.needs_water
                        else "추가 관찰 유지"
                    ),
                    "ready_to_harvest": plant.ready_to_harvest,
                    "needs_water": plant.needs_water,
                    "needs_nutrition": plant.needs_nutrition,
                }
                for plant in plants
            }

            for plant in plants:
                latest_observation = max(
                    plant.observations,
                    key=lambda item: item.observed_at or datetime.min,
                    default=None,
                )
                if latest_observation is None:
                    continue
                latest_label = latest_observation.finding_label
                rows[plant.id].update(
                    {
                        "health_score": _health_percent(latest_label) / 100.0,
                        "health": _health_percent(latest_label),
                        "status": _display_label(latest_label),
                        "latest_label": latest_label,
                        "latest_display_label": _display_label(latest_label),
                        "latest_image_url": _api_image_url(latest_observation.image_url or ""),
                        "recommended_action": latest_observation.recommended_action or rows[plant.id]["recommended_action"],
                    }
                )

            latest_runtime_by_plant: dict[str, RuntimeObservationRecord] = {}
            for record in runtime_records:
                if not record.plant_id or record.plant_id in latest_runtime_by_plant:
                    continue
                latest_runtime_by_plant[record.plant_id] = record

            for plant_id, record in latest_runtime_by_plant.items():
                row = rows.get(plant_id)
                if row is None:
                    row = {
                        "id": plant_id,
                        "plant_id": plant_id,
                        "name": _plant_display_name(plant_id),
                        "crop_name": "tomato",
                        "target_fruit_id": record.fruit_id,
                        "fruit_id": record.fruit_id,
                        "zone_id": record.zone_id,
                        "zone_label": record.zone_id or "farm_01",
                        "position": _plant_position(plant_id, None),
                        "last_observed_at": record.reviewed_at,
                        "health_score": None,
                        "health": 92,
                        "status": "관측 대기",
                        "latest_label": "",
                        "latest_display_label": "",
                        "latest_image_url": "",
                        "recommended_action": "추가 관찰 유지",
                        "ready_to_harvest": False,
                        "needs_water": False,
                        "needs_nutrition": False,
                    }
                    rows[plant_id] = row

                row.update(
                    {
                        "target_fruit_id": row.get("target_fruit_id") or record.fruit_id,
                        "fruit_id": row.get("fruit_id") or record.fruit_id,
                        "zone_id": record.zone_id or row["zone_id"],
                        "zone_label": record.zone_id or row["zone_label"],
                        "last_observed_at": record.reviewed_at or row["last_observed_at"],
                        "health_score": _health_percent(record.finding_label) / 100.0,
                        "health": _health_percent(record.finding_label),
                        "status": record.display_label,
                        "latest_label": record.finding_label,
                        "latest_display_label": record.display_label,
                        "latest_image_url": record.image_url,
                        "recommended_action": record.recommended_action,
                    }
                )

            return [rows[plant_id] for plant_id in sorted(rows)]
        finally:
            db.close()

    def get_plant_detail(self, plant_id: str) -> dict[str, Any]:
        observation_feed = self.get_plant_observations(plant_id)
        latest = observation_feed["items"][0] if observation_feed["items"] else None

        db = SessionLocal()
        try:
            try:
                plant = (
                    db.query(Plant)
                    .options(joinedload(Plant.zone), joinedload(Plant.fruits))
                    .filter(Plant.id == plant_id)
                    .first()
                )
            except OperationalError:
                _rollback_quietly(db)
                plant = None

            if plant is None:
                return {
                    "id": plant_id,
                    "plant_id": plant_id,
                    "name": _plant_display_name(plant_id),
                    "zone_id": observation_feed["zone_id"],
                    "zone_label": observation_feed["zone_label"],
                    "position": _plant_position(plant_id, None),
                    "latest_observation": latest,
                    "observation_count": len(observation_feed["items"]),
                    "target_fruit_id": None,
                }

            return {
                "id": plant.id,
                "plant_id": plant.id,
                "name": _plant_display_name(plant.id),
                "zone_id": plant.zone_id,
                "zone_label": _zone_label(plant.zone),
                "position": _plant_position(plant.id, plant.position),
                "latest_observation": latest,
                "observation_count": len(observation_feed["items"]),
                "target_fruit_id": "" if not plant.fruits else plant.fruits[0].id,
            }
        finally:
            db.close()

    def get_plant_observations(self, plant_id: str) -> dict[str, Any]:
        runtime_records = _runtime_observation_records()
        runtime_items = [
            _runtime_observation_item(record)
            for record in runtime_records
            if record.plant_id == plant_id
        ]

        db = SessionLocal()
        try:
            db_items: list[dict[str, Any]] = []
            try:
                plant = (
                    db.query(Plant)
                    .options(joinedload(Plant.zone))
                    .filter(Plant.id == plant_id)
                    .first()
                )
                if plant is not None:
                    observations = (
                        db.query(CropObservation)
                        .options(joinedload(CropObservation.fruit))
                        .filter(CropObservation.plant_id == plant_id)
                        .order_by(CropObservation.observed_at.desc())
                        .all()
                    )
                    db_items = [
                        {
                            "id": _serialize_uuid(observation.id),
                            "class_name": observation.finding_label,
                            "label": observation.finding_label,
                            "display_label": _display_label(observation.finding_label),
                            "reviewed_at": _serialize_datetime(observation.observed_at),
                            "image_url": _api_image_url(observation.image_url or ""),
                            "media_asset_id": _serialize_uuid(observation.id),
                            "decision_source": "database",
                            "health_percent": _health_percent(observation.finding_label),
                            "detail": observation.evidence or observation.recommended_action or "",
                            "treatment_plan": {
                                "reason": observation.evidence or observation.recommended_action or "",
                            },
                        }
                        for observation in observations
                    ]
            except OperationalError:
                _rollback_quietly(db)
                plant = None

            if plant is None and not runtime_items:
                raise FileNotFoundError(f"알 수 없는 plant_id 입니다: {plant_id}")

            items_by_id = {item["id"]: item for item in db_items}
            for item in runtime_items:
                items_by_id[item["id"]] = item

            items = list(items_by_id.values())
            items.sort(key=lambda item: str(item.get("reviewed_at") or ""), reverse=True)

            zone_id = plant.zone_id if plant is not None else (
                next(
                    (
                        record.zone_id
                        for record in runtime_records
                        if record.plant_id == plant_id and record.zone_id
                    ),
                    "farm_01",
                )
            )
            zone_label = _zone_label(plant.zone) if plant is not None else zone_id

            return {
                "plant_id": plant_id,
                "plant_name": _plant_display_name(plant_id),
                "zone_id": zone_id,
                "zone_label": zone_label,
                "items": items,
            }
        finally:
            db.close()

    def resolve_media_path(self, asset_id: str) -> Path:
        runtime_record = _runtime_record_by_observation_id(asset_id)
        if runtime_record is not None and runtime_record.image_path is not None:
            return runtime_record.image_path

        db = SessionLocal()
        try:
            observation_uuid = _parse_uuid(asset_id)
            observation = (
                db.query(CropObservation)
                .filter(CropObservation.id == observation_uuid)
                .first()
            )
            image_url = observation.image_url if observation is not None else ""
            if not image_url:
                alert = db.query(Alert).filter(Alert.id == _parse_uuid(asset_id)).first()
                image_url = "" if alert is None else alert.image_url or ""

            resolved = _resolve_local_media_path(image_url)
            if resolved is not None:
                return resolved
            raise FileNotFoundError(f"이미지 파일을 찾지 못했습니다: {image_url or asset_id}")
        finally:
            db.close()

    def media_response_meta(self, asset_id: str) -> dict[str, str]:
        image_path = self.resolve_media_path(asset_id)
        return {
            "filename": image_path.name,
            "media_type": mimetypes.guess_type(image_path.name)[0] or "application/octet-stream",
        }

    def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> dict[str, str]:
        runtime_record = _runtime_record_by_observation_id(alert_id)
        if runtime_record is not None:
            payload = _read_json_file(runtime_record.metadata_path)
            if payload is None:
                raise FileNotFoundError(f"알 수 없는 alert_id 입니다: {alert_id}")

            acknowledged_at = _utc_now_iso()
            payload["acknowledged_by"] = acknowledged_by.strip() or "unknown"
            payload["acknowledged_at"] = acknowledged_at
            runtime_record.metadata_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return {
                "id": runtime_record.observation_id,
                "acknowledged_by": str(payload["acknowledged_by"]),
                "acknowledged_at": acknowledged_at,
            }

        db = SessionLocal()
        try:
            alert = db.query(Alert).filter(Alert.id == _parse_uuid(alert_id)).first()
            if alert is None:
                raise FileNotFoundError(f"알 수 없는 alert_id 입니다: {alert_id}")
            alert.acknowledged_by = acknowledged_by.strip() or "unknown"
            alert.acknowledged_at = datetime.utcnow()
            db.commit()
            return {
                "id": _serialize_uuid(alert.id),
                "acknowledged_by": alert.acknowledged_by,
                "acknowledged_at": _serialize_datetime(alert.acknowledged_at),
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
