from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

from database import SessionLocal
from models import CropObservation, Plant
from robot_map_service import read_layers_payload
from zone_service import zone_label_for_id


REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_RUNTIME_RELATIVE_PATH = Path('artifacts/runtime/backend')
_DEFAULT_LABEL_CONTRACT_RELATIVE_PATH = Path('artifacts/models/tomato_disease/v1/label_contract.json')
_DEFAULT_ACK_FILENAME = 'alert_ack_state.json'


@dataclass(frozen=True)
class ObservationRecord:
    asset_id: str
    observation_id: str
    plant_id: str
    plant_name: str
    zone_id: str
    zone_label: str
    position: dict[str, float] | None
    final_label: str
    display_label: str
    confidence: float
    health_score_raw: float
    health_percent: int
    image_path: str
    image_url: str
    reviewed_at: str
    decision_source: str
    treatment_plan: dict[str, Any] | None
    dispatch_result: dict[str, Any] | None


class ObservationReadService:
    def __init__(self) -> None:
        runtime_dir = os.environ.get('AGRIBOT_BACKEND_RUNTIME_DIR', '').strip()
        self._runtime_dir = (
            Path(runtime_dir).expanduser()
            if runtime_dir
            else REPO_ROOT / _DEFAULT_RUNTIME_RELATIVE_PATH
        )
        self._display_names = _read_display_names()
        self._ack_path = self._runtime_dir / _DEFAULT_ACK_FILENAME
        self._plant_catalog = _read_plant_catalog()

    def list_alerts(self) -> list[dict[str, Any]]:
        ack_state = self._read_ack_state()
        alerts: list[dict[str, Any]] = []
        for observation in self.list_observations():
            severity = _severity_for_label(observation.final_label)
            summary_label = observation.display_label or observation.final_label or '병해'
            message = f'{summary_label} 감지'
            acknowledged_at = ack_state.get(observation.asset_id, {})

            alerts.append(
                {
                    'id': observation.asset_id,
                    'observation_id': observation.observation_id,
                    'severity': severity,
                    'level': severity,
                    'title': message,
                    'message': message,
                    'detail': _build_alert_detail(observation),
                    'description': _build_alert_detail(observation),
                    'action': _build_alert_action(observation.final_label),
                    'location': f'{observation.plant_name} · {observation.zone_label}',
                    'zone_id': observation.zone_id,
                    'plant_id': observation.plant_id,
                    'label': observation.final_label,
                    'display_label': observation.display_label,
                    'image_url': observation.image_url,
                    'media_asset_id': observation.asset_id,
                    'detected_at': observation.reviewed_at,
                    'created_at': observation.reviewed_at,
                    'time': observation.reviewed_at,
                    'decision_source': observation.decision_source,
                    'is_acked': bool(acknowledged_at),
                    'acknowledged_at': acknowledged_at.get('acknowledged_at', ''),
                    'acknowledged_by': acknowledged_at.get('acknowledged_by', ''),
                }
            )

        return alerts

    def list_plants(self) -> list[dict[str, Any]]:
        latest_by_plant_id: dict[str, ObservationRecord] = {}
        for observation in self.list_observations():
            latest_by_plant_id.setdefault(observation.plant_id, observation)

        plant_ids = sorted(set(self._plant_catalog) | set(latest_by_plant_id))
        rows: list[dict[str, Any]] = []
        for plant_id in plant_ids:
            plant = self._plant_catalog.get(plant_id, {})
            latest = latest_by_plant_id.get(plant_id)
            display_name = plant.get('name') or (latest.plant_name if latest is not None else plant_id)
            zone_id = plant.get('zone_id') or (latest.zone_id if latest is not None else 'farm_01')
            zone_label = plant.get('zone_label') or (
                latest.zone_label if latest is not None else zone_label_for_id(zone_id)
            )
            rows.append(
                {
                    'id': plant_id,
                    'plant_id': plant_id,
                    'name': display_name,
                    'crop_name': 'tomato',
                    'target_fruit_id': plant.get('target_fruit_id', ''),
                    'fruit_id': plant.get('target_fruit_id', ''),
                    'zone_id': zone_id,
                    'zone_label': zone_label,
                    'position': plant.get('position') or (None if latest is None else latest.position),
                    'last_observed_at': '' if latest is None else latest.reviewed_at,
                    'health_score': 1.0 if latest is None else round(latest.health_percent / 100.0, 2),
                    'health': 100 if latest is None else latest.health_percent,
                    'status': '관측 대기' if latest is None else latest.display_label,
                    'latest_label': '' if latest is None else latest.final_label,
                    'latest_display_label': '' if latest is None else latest.display_label,
                    'latest_image_path': '' if latest is None else latest.image_path,
                    'latest_image_url': '' if latest is None else latest.image_url,
                    'recommended_action': (
                        '추가 관찰 유지' if latest is None else _build_alert_action(latest.final_label)
                    ),
                    'ready_to_harvest': False,
                    'needs_water': False,
                }
            )

        return rows

    def get_plant_detail(self, plant_id: str) -> dict[str, Any]:
        normalized_plant_id = plant_id.strip()
        plant = self._plant_catalog.get(normalized_plant_id)
        observations_payload = self.get_plant_observations(normalized_plant_id)
        observations = observations_payload['items']
        latest = observations[0] if observations else None

        if plant is None and not observations:
            raise FileNotFoundError(f'알 수 없는 plant_id 입니다: {plant_id}')

        return {
            'id': normalized_plant_id,
            'plant_id': normalized_plant_id,
            'name': (
                '' if plant is None else plant['name']
            ) or _read_string(latest.get('plant_name') if isinstance(latest, dict) else '') or normalized_plant_id,
            'zone_id': (
                '' if plant is None else plant['zone_id']
            ) or _read_string(latest.get('zone_id') if isinstance(latest, dict) else '') or 'farm_01',
            'zone_label': (
                '' if plant is None else plant['zone_label']
            ) or _read_string(latest.get('zone_label') if isinstance(latest, dict) else '') or zone_label_for_id('farm_01'),
            'position': (
                None if plant is None else plant.get('position')
            ) or (latest.get('position') if isinstance(latest, dict) else None),
            'latest_observation': latest,
            'observation_count': len(observations),
            'target_fruit_id': '' if plant is None else plant.get('target_fruit_id', ''),
        }

    def get_plant_observations(self, plant_id: str) -> dict[str, Any]:
        normalized_plant_id = plant_id.strip()
        plant = self._plant_catalog.get(normalized_plant_id)
        items = [
            self._serialize_observation(observation)
            for observation in self.list_observations()
            if observation.plant_id == normalized_plant_id
        ]

        if plant is None and not items:
            raise FileNotFoundError(f'알 수 없는 plant_id 입니다: {plant_id}')

        return {
            'plant_id': normalized_plant_id,
            'plant_name': '' if plant is None else plant['name'],
            'zone_id': '' if plant is None else plant['zone_id'],
            'zone_label': '' if plant is None else plant['zone_label'],
            'items': items,
        }

    def resolve_media_path(self, asset_id: str) -> Path:
        for observation in self.list_observations():
            if observation.asset_id != asset_id:
                continue
            image_path = Path(observation.image_path)
            if image_path.exists():
                return image_path
            raise FileNotFoundError(f'이미지 파일을 찾지 못했습니다: {image_path}')
        raise FileNotFoundError(f'알 수 없는 media asset_id 입니다: {asset_id}')

    def media_response_meta(self, asset_id: str) -> dict[str, str]:
        image_path = self.resolve_media_path(asset_id)
        media_type = mimetypes.guess_type(image_path.name)[0] or 'application/octet-stream'
        return {
            'filename': image_path.name,
            'media_type': media_type,
        }

    def acknowledge_alert(self, asset_id: str, acknowledged_by: str) -> dict[str, str]:
        payload = self._read_ack_state()
        acknowledged_at = datetime.now(timezone.utc).isoformat()
        payload[asset_id] = {
            'acknowledged_by': acknowledged_by.strip() or 'unknown',
            'acknowledged_at': acknowledged_at,
        }
        self._ack_path.parent.mkdir(parents=True, exist_ok=True)
        self._ack_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding='utf-8',
        )
        return {
            'id': asset_id,
            'acknowledged_by': payload[asset_id]['acknowledged_by'],
            'acknowledged_at': acknowledged_at,
        }

    def list_observations(self) -> list[ObservationRecord]:
        metadata_by_asset_id = self._read_runtime_metadata()
        database_rows = self._read_database_rows()
        observations: list[ObservationRecord] = []

        for row in database_rows:
            asset_id = _asset_id_from_path(row['image_path'])
            metadata = metadata_by_asset_id.pop(asset_id, None)
            plant_id = row['plant_id']
            plant = self._plant_catalog.get(plant_id, {})
            final_label = _read_string(metadata.get('final_label')) or row['final_label']
            display_label = self._display_names.get(final_label, final_label)
            reviewed_at = _read_string(metadata.get('reviewed_at')) or row['reviewed_at']

            observations.append(
                ObservationRecord(
                    asset_id=asset_id,
                    observation_id=_read_string(metadata.get('observation_id')) or asset_id,
                    plant_id=plant_id,
                    plant_name=plant.get('name', row['plant_name']),
                    zone_id=plant.get('zone_id', row['zone_id']),
                    zone_label=plant.get('zone_label', zone_label_for_id(row['zone_id'])),
                    position=plant.get('position'),
                    final_label=final_label,
                    display_label=display_label,
                    confidence=_read_float(metadata.get('final_confidence'), row['confidence']),
                    health_score_raw=_read_float(row['health_score'], 0.0),
                    health_percent=_health_percent(row['health_score']),
                    image_path=row['image_path'],
                    image_url=_build_media_url(asset_id),
                    reviewed_at=reviewed_at,
                    decision_source=_read_string(metadata.get('decision_source')) or 'database',
                    treatment_plan=_read_dict(metadata.get('treatment_plan')),
                    dispatch_result=_read_dict(metadata.get('dispatch_result')),
                )
            )

        if not observations:
            for asset_id, metadata in metadata_by_asset_id.items():
                observations.append(self._build_runtime_observation(asset_id, metadata))
        else:
            for asset_id, metadata in metadata_by_asset_id.items():
                if any(item.asset_id == asset_id for item in observations):
                    continue
                observations.append(self._build_runtime_observation(asset_id, metadata))

        observations.sort(key=lambda item: item.reviewed_at, reverse=True)
        return observations

    def _build_runtime_observation(
        self,
        asset_id: str,
        metadata: dict[str, Any],
    ) -> ObservationRecord:
        request = _read_dict(metadata.get('request'))
        plant_id = _read_string(request.get('plant_id'))
        plant = self._plant_catalog.get(plant_id, {})
        resolved_label = (
            _read_string(metadata.get('final_label'))
            or _read_string(request.get('preliminary_label'))
            or 'unknown'
        )
        image_path = _derive_image_path(metadata, self._runtime_dir)
        return ObservationRecord(
            asset_id=asset_id,
            observation_id=_read_string(metadata.get('observation_id')) or asset_id,
            plant_id=plant_id,
            plant_name=plant.get('name', plant_id or '이름 없는 식물'),
            zone_id=plant.get('zone_id', _read_string(request.get('zone_id')) or 'farm_01'),
            zone_label=plant.get(
                'zone_label',
                zone_label_for_id(_read_string(request.get('zone_id')) or 'farm_01'),
            ),
            position=plant.get('position'),
            final_label=resolved_label,
            display_label=self._display_names.get(resolved_label, resolved_label),
            confidence=_read_float(metadata.get('final_confidence'), 0.0),
            health_score_raw=_health_score_from_label(resolved_label),
            health_percent=_health_percent(_health_score_from_label(resolved_label)),
            image_path=str(image_path),
            image_url=_build_media_url(asset_id),
            reviewed_at=_read_string(metadata.get('reviewed_at')),
            decision_source=_read_string(metadata.get('decision_source')) or 'runtime_metadata',
            treatment_plan=_read_dict(metadata.get('treatment_plan')),
            dispatch_result=_read_dict(metadata.get('dispatch_result')),
        )

    def _read_runtime_metadata(self) -> dict[str, dict[str, Any]]:
        metadata_by_asset_id: dict[str, dict[str, Any]] = {}
        if not self._runtime_dir.exists():
            return metadata_by_asset_id

        for metadata_path in sorted(self._runtime_dir.glob('*/*.json'), reverse=True):
            if metadata_path.name == _DEFAULT_ACK_FILENAME:
                continue
            try:
                payload = json.loads(metadata_path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            asset_id = _read_string(payload.get('observation_id')) or metadata_path.stem
            if asset_id:
                payload['_metadata_path'] = str(metadata_path)
                metadata_by_asset_id[asset_id] = payload

        return metadata_by_asset_id

    def _read_database_rows(self) -> list[dict[str, Any]]:
        db = SessionLocal()
        try:
            rows = (
                db.query(CropObservation, Plant)
                .join(Plant, CropObservation.plant_id == Plant.id)
                .order_by(CropObservation.observed_at.desc(), CropObservation.id.desc())
                .all()
            )
        except Exception:
            db.rollback()
            return []
        finally:
            db.close()

        serialized_rows: list[dict[str, Any]] = []
        for observation, plant in rows:
            image_path = _read_string(observation.image_url)
            if not image_path:
                continue
            serialized_rows.append(
                {
                    'image_path': image_path,
                    'plant_id': _read_string(plant.name),
                    'plant_name': _read_string(plant.name) or f'Plant {plant.id}',
                    'zone_id': 'farm_01',
                    'final_label': _read_string(observation.class_name),
                    'confidence': float(observation.confidence or 0.0),
                    'health_score': float(observation.health_score or 0.0),
                    'reviewed_at': _isoformat(observation.observed_at),
                }
            )
        return serialized_rows

    def _read_ack_state(self) -> dict[str, dict[str, str]]:
        if not self._ack_path.exists():
            return {}
        try:
            payload = json.loads(self._ack_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _serialize_observation(observation: ObservationRecord) -> dict[str, Any]:
        return {
            'id': observation.asset_id,
            'observation_id': observation.observation_id,
            'plant_id': observation.plant_id,
            'plant_name': observation.plant_name,
            'zone_id': observation.zone_id,
            'zone_label': observation.zone_label,
            'position': observation.position,
            'label': observation.final_label,
            'class_name': observation.final_label,
            'display_label': observation.display_label,
            'confidence': observation.confidence,
            'health_score': observation.health_score_raw,
            'health_percent': observation.health_percent,
            'image_path': observation.image_path,
            'image_url': observation.image_url,
            'media_asset_id': observation.asset_id,
            'reviewed_at': observation.reviewed_at,
            'detected_at': observation.reviewed_at,
            'decision_source': observation.decision_source,
            'treatment_plan': observation.treatment_plan,
            'dispatch_result': observation.dispatch_result,
        }


def _build_media_url(asset_id: str) -> str:
    return f'/api/v1/media/{asset_id}'


def _derive_image_path(metadata: dict[str, Any], runtime_dir: Path) -> Path:
    metadata_path_raw = _read_string(metadata.get('_metadata_path'))
    request = _read_dict(metadata.get('request'))
    image_format = _read_string(request.get('image_format')) or 'jpg'
    suffix = '.jpg' if image_format == 'jpeg' else f'.{image_format}'
    if metadata_path_raw:
        metadata_path = Path(metadata_path_raw)
        return metadata_path.with_suffix(suffix)
    observation_id = _read_string(metadata.get('observation_id'))
    return runtime_dir / datetime.now().strftime('%Y%m%d') / f'{observation_id}{suffix}'


def _read_plant_catalog() -> dict[str, dict[str, Any]]:
    try:
        layers = read_layers_payload()
    except Exception:
        return {}

    catalog: dict[str, dict[str, Any]] = {}
    for asset in layers.get('assets', []):
        if asset.get('kind') != 'plant':
            continue
        plant_id = _read_string(asset.get('id'))
        if not plant_id:
            continue
        position = _read_dict(asset.get('position'))
        catalog[plant_id] = {
            'name': _read_string(asset.get('label')) or plant_id,
            'zone_id': _read_string(asset.get('zone_id')) or 'farm_01',
            'zone_label': zone_label_for_id(_read_string(asset.get('zone_id')) or 'farm_01'),
            'position': {
                'x': _read_float(position.get('x'), 0.0),
                'y': _read_float(position.get('y'), 0.0),
                'z': _read_float(position.get('z'), 0.0),
            },
            'target_fruit_id': _read_string(asset.get('linked_id')),
        }
    return catalog


def _read_display_names() -> dict[str, str]:
    contract_path = REPO_ROOT / _DEFAULT_LABEL_CONTRACT_RELATIVE_PATH
    if not contract_path.exists():
        return {}
    try:
        payload = json.loads(contract_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    display_names = payload.get('display_names_ko')
    return display_names if isinstance(display_names, dict) else {}


def _build_alert_detail(observation: ObservationRecord) -> str:
    detail = (
        f'{observation.plant_name}에서 {observation.display_label}이 감지되었습니다. '
        f'신뢰도 {observation.confidence:.2f} 기준으로 저장된 사진을 확인하세요.'
    )
    if observation.treatment_plan and observation.treatment_plan.get('reason'):
        return f"{detail} {observation.treatment_plan['reason']}"
    return detail


def _build_alert_action(final_label: str) -> str:
    normalized = final_label.lower()
    if 'powdery' in normalized:
        return '약재 살포 후보와 위치를 검토하세요.'
    if 'calcium' in normalized:
        return '영양제 보강 필요 여부를 함께 확인하세요.'
    if 'crack' in normalized:
        return '수확 제외 또는 상태 관찰 여부를 결정하세요.'
    return '현장 사진과 진단 결과를 먼저 검토하세요.'


def _severity_for_label(final_label: str) -> str:
    normalized = final_label.lower()
    if 'powdery' in normalized or 'gray_mold' in normalized:
        return 'critical'
    return 'warning'


def _asset_id_from_path(image_path: str) -> str:
    return Path(image_path).stem


def _health_percent(raw_score: float | None) -> int:
    score = 0.0 if raw_score is None else float(raw_score)
    if score <= 1.0:
        return max(0, min(100, int(round(score * 100))))
    return max(0, min(100, int(round(score))))


def _health_score_from_label(final_label: str) -> float:
    normalized = final_label.strip().lower()
    if 'powdery' in normalized or 'gray_mold' in normalized:
        return 0.15
    if 'calcium' in normalized:
        return 0.35
    if 'crack' in normalized:
        return 0.45
    if 'healthy' in normalized or 'normal' in normalized:
        return 1.0
    return 0.25


def _read_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _read_string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ''
    return str(value).strip()


def _read_float(value: Any, fallback: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return fallback
    return fallback


def _isoformat(value: Any) -> str:
    if value is None:
        return ''
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return _read_string(value)
