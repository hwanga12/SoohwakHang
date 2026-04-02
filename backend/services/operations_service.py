# 이 모듈은 백엔드 서비스 계층에서 operations service 책임을 담당한다.
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import joinedload

from database import SessionLocal
from models import (
    ActuationCommand,
    ActuationLog,
    Alert,
    CropObservation,
    EnvironmentSample,
    Fruit,
    HarvestEvent,
    IotDevice,
    Mission,
    Plant,
    Robot,
    Zone,
)
from ros_protocol_bridge import get_ros_protocol_bridge
from services.actuation.dispatcher import TreatmentCommandDispatcher


def _serialize_datetime(value: datetime | None) -> str:
    # datetime를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    return "" if value is None else value.isoformat()


def _serialize_uuid(value: UUID | None) -> str:
    # uuid를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    return "" if value is None else str(value)


def _plant_name(plant_id: str) -> str:
    # 작물 name 정보를 계산해 반환한다.
    suffix = plant_id.split("_")[-1] if plant_id else ""
    return f"토마토 식물 {suffix}" if suffix else plant_id


def _zone_center(bounds: dict[str, Any]) -> dict[str, float]:
    # 구역 center 정보를 계산해 반환한다.
    min_x = float(bounds.get("min_x", bounds.get("x_min", -10.0)))
    max_x = float(bounds.get("max_x", bounds.get("x_max", 10.0)))
    min_y = float(bounds.get("min_y", bounds.get("y_min", -10.0)))
    max_y = float(bounds.get("max_y", bounds.get("y_max", 10.0)))
    return {
        "x": (min_x + max_x) / 2.0,
        "y": (min_y + max_y) / 2.0,
        "z": 0.0,
        "yaw": 0.0,
        "frame_id": "map",
    }


def _command_title(command_type: str) -> str:
    # 명령 title 정보를 계산해 반환한다.
    normalized = command_type.strip().upper()
    mapping = {
        "WATERING": "급수 실행",
        "NUTRIENTS": "영양제 투입",
        "SPRAY_PESTICIDE": "약제 살포",
        "SPRAY_CALCIUM_SOLUTION": "칼슘액비 살포",
        "STOP": "장치 정지",
    }
    return mapping.get(normalized, normalized or "장치 제어")


def _normalized_device_type(device_type: str) -> str:
    # normalized 장치 type 정보를 계산해 반환한다.
    return str(device_type).strip().upper()


def _build_dispatch_reason(
    *,
    logical_command_type: str,
    device_type: str,
    recommendation_id: str | None,
) -> str:
    # dispatch reason를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    logical = logical_command_type.strip().upper()
    normalized_device_type = device_type.strip().lower()
    reason = (
        f'Manual actuation request for {normalized_device_type or "unknown"} '
        f'via {logical or "UNKNOWN"}.'
    )
    payload_items: list[str] = []
    if recommendation_id:
        payload_items.append(f'recommendation_id={recommendation_id}')

    if normalized_device_type == 'sprinkler' and logical == 'WATERING':
        payload_items.extend([
            'effect_color=blue',
            'treatment_type=water_spray',
        ])
    elif normalized_device_type == 'sprinkler' and logical == 'NUTRIENTS':
        payload_items.extend([
            'effect_color=green',
            'treatment_type=nutrient_solution_spray',
            'nutrient_type=calcium_boost',
        ])
    elif normalized_device_type == 'nutrient':
        payload_items.append('nutrient_type=calcium_boost')

    if payload_items:
        reason = f'{reason} payload={",".join(payload_items)}'
    return reason


def _build_dispatch_spec(
    *,
    device_type: str,
    logical_command_type: str,
    target_value: float,
    value_unit: str,
    recommendation_id: str | None,
) -> dict[str, str | float]:
    # dispatch spec를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    normalized_device_type = _normalized_device_type(device_type)
    normalized_command_type = logical_command_type.strip().upper()
    normalized_unit = str(value_unit).strip().lower()

    if normalized_device_type in {'WATERING', 'WATER_PUMP'} and normalized_command_type == 'WATERING':
        dispatch_device_type = 'watering'
        dispatch_command_type = 'dispense_water'
        dispatch_unit = normalized_unit or 'ml'
    elif normalized_device_type == 'NUTRIENT' and normalized_command_type == 'NUTRIENTS':
        dispatch_device_type = 'nutrient'
        dispatch_command_type = 'apply_nutrient_recipe'
        dispatch_unit = normalized_unit or 'ml'
    elif normalized_device_type == 'SPRINKLER' and normalized_command_type == 'WATERING':
        dispatch_device_type = 'sprinkler'
        dispatch_command_type = 'spray_water'
        dispatch_unit = normalized_unit or 'sec'
    elif normalized_device_type == 'SPRINKLER' and normalized_command_type == 'NUTRIENTS':
        dispatch_device_type = 'sprinkler'
        dispatch_command_type = 'spray_nutrient_solution'
        dispatch_unit = normalized_unit or 'sec'
    else:
        raise ValueError(
            '지원하지 않는 수동 제어 조합입니다: '
            f'device_type={normalized_device_type}, command_type={normalized_command_type}'
        )

    return {
        'device_type': dispatch_device_type,
        'command_type': dispatch_command_type,
        'target_value': float(target_value),
        'unit': dispatch_unit,
        'reason': _build_dispatch_reason(
            logical_command_type=normalized_command_type,
            device_type=dispatch_device_type,
            recommendation_id=recommendation_id,
        ),
    }


def _result_tone(result: str) -> str:
    # 결과 톤 정보를 계산해 반환한다.
    normalized = result.strip().upper()
    if normalized in {"FAILED", "TIMEOUT"}:
        return "critical"
    if normalized in {"REQUESTED", "SENT", "ACKED"}:
        return "warning"
    return "healthy"


def _mission_sort_key(mission: Mission) -> tuple[int, str, str]:
    # 미션 sort key 정보를 계산해 반환한다.
    priority = {
        "RUNNING": 0,
        "PENDING": 1,
        "COMPLETED": 2,
        "FAILED": 3,
        "CANCELED": 4,
    }.get(str(mission.status or "").upper(), 9)
    started_ts = mission.started_at.timestamp() if mission.started_at else 0.0
    completed_ts = mission.completed_at.timestamp() if mission.completed_at else 0.0
    return (priority, -(started_ts or completed_ts), _serialize_uuid(mission.id))


def _select_focus_mission(missions: list[Mission]) -> Mission | None:
    # focus 미션 가운데 필요한 대상을 고른다.
    if not missions:
        return None
    return sorted(missions, key=_mission_sort_key)[0]


class OperationsService:
    # 운영 서비스 관련 핵심 흐름을 한곳에 모아 제공하는 서비스 클래스다.
    _manual_command_dispatcher = TreatmentCommandDispatcher()

    def list_zones(self) -> list[dict[str, Any]]:
        # 구역 목록를 모아 순회하기 쉬운 형태로 정리한다.
        db = SessionLocal()
        try:
            zones = db.query(Zone).options(joinedload(Zone.plants)).order_by(Zone.id.asc()).all()
            return [
                {
                    "id": zone.id,
                    "name": zone.name,
                    "label": zone.name,
                    "description": zone.description or f"{zone.name} 운영 구역",
                    "representative_pose": _zone_center(zone.bounds or {}),
                    "bounds": zone.bounds or {},
                    "plant_count": len(zone.plants),
                    "map_id": "farm_map",
                }
                for zone in zones
            ]
        finally:
            db.close()

    def get_dashboard_summary(self) -> dict[str, Any]:
        # dashboard summary를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        db = SessionLocal()
        try:
            latest_robot = db.query(Robot).order_by(Robot.updated_at.desc()).first()
            active_mission = _select_focus_mission(db.query(Mission).all())
            critical_alerts = db.query(Alert).filter(Alert.acknowledged_at.is_(None)).count()
            total_plants = db.query(Plant).count()
            ready_fruits = db.query(Fruit).filter(Fruit.ready_to_harvest.is_(True)).count()
            return {
                "robot_uptime_pct": "98%",
                "active_task": (
                    f"{active_mission.mission_type} · {active_mission.status}"
                    if active_mission is not None
                    else "대기 중"
                ),
                "critical_alert_count": critical_alerts,
                "plant_count": total_plants,
                "ready_fruit_count": ready_fruits,
                "robot_name": "" if latest_robot is None else latest_robot.name,
            }
        finally:
            db.close()

    def get_latest_environment(self) -> dict[str, Any]:
        # latest environment를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        bridge_payload = get_ros_protocol_bridge().get_latest_environment_data()
        if bridge_payload is not None:
            soil_moisture = float(bridge_payload.get("soil_moisture", 0.0) or 0.0)
            return {
                "source": "ros_topic",
                "zone_id": bridge_payload.get("zone_id"),
                "temperature": bridge_payload.get("temperature"),
                "humidity": bridge_payload.get("humidity"),
                "soil_moisture": bridge_payload.get("soil_moisture"),
                "temperature_delta": "",
                "humidity_delta": "",
                "soil_status": "안정" if soil_moisture >= 32.0 else "주의",
                "recommendation": (
                    "급수 유지"
                    if soil_moisture >= 32.0
                    else "토양 수분이 낮아 급수 권장이 필요합니다."
                ),
                "recorded_at": bridge_payload.get("updated_at", ""),
            }

        db = SessionLocal()
        try:
            latest = (
                db.query(EnvironmentSample)
                .order_by(EnvironmentSample.recorded_at.desc())
                .first()
            )
            previous = (
                db.query(EnvironmentSample)
                .order_by(EnvironmentSample.recorded_at.desc())
                .offset(1)
                .first()
            )
            if latest is None:
                return {}

            def _delta(current: float | None, before: float | None) -> str:
                # delta 정보를 계산해 반환한다.
                if current is None or before is None:
                    return ""
                diff = current - before
                sign = "+" if diff >= 0 else ""
                return f"{sign}{diff:.1f}"

            recommendation = "급수 유지"
            if latest.soil_moisture is not None and latest.soil_moisture < 32.0:
                recommendation = "토양 수분이 낮아 급수 권장이 필요합니다."

            return {
                "zone_id": latest.zone_id,
                "temperature": latest.temperature,
                "humidity": latest.humidity,
                "soil_moisture": latest.soil_moisture,
                "temperature_delta": _delta(latest.temperature, None if previous is None else previous.temperature),
                "humidity_delta": _delta(latest.humidity, None if previous is None else previous.humidity),
                "soil_status": "안정" if (latest.soil_moisture or 0) >= 32 else "주의",
                "recommendation": recommendation,
                "recorded_at": _serialize_datetime(latest.recorded_at),
            }
        finally:
            db.close()

    def get_environment_history(self, limit: int = 20) -> list[dict[str, Any]]:
        # environment 이력를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        db = SessionLocal()
        try:
            rows = (
                db.query(EnvironmentSample)
                .order_by(EnvironmentSample.recorded_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": _serialize_uuid(sample.id),
                    "zone_id": sample.zone_id,
                    "temperature": sample.temperature,
                    "humidity": sample.humidity,
                    "soil_moisture": sample.soil_moisture,
                    "recorded_at": _serialize_datetime(sample.recorded_at),
                }
                for sample in rows
            ]
        finally:
            db.close()

    def list_iot_devices(self) -> list[dict[str, Any]]:
        # IoT 장치 목록를 모아 순회하기 쉬운 형태로 정리한다.
        db = SessionLocal()
        try:
            devices = db.query(IotDevice).order_by(IotDevice.id.asc()).all()
            return [
                {
                    "id": device.id,
                    "device_id": device.id,
                    "zone_id": device.zone_id,
                    "device_type": device.device_type,
                    "display_name": device.display_name,
                    "control_mode": device.control_mode,
                    "current_state": device.current_state,
                    "current_value": device.current_value,
                    "value_unit": device.value_unit,
                    "is_online": device.is_online,
                    "last_seen_at": _serialize_datetime(device.last_seen_at),
                }
                for device in devices
            ]
        finally:
            db.close()

    def list_recommendations(self) -> list[dict[str, Any]]:
        # recommendations를 모아 순회하기 쉬운 형태로 정리한다.
        db = SessionLocal()
        try:
            latest_env = (
                db.query(EnvironmentSample)
                .order_by(EnvironmentSample.recorded_at.desc())
                .first()
            )
            recommendation_rows: list[dict[str, Any]] = []
            if latest_env is not None and (latest_env.soil_moisture or 0.0) < 32.0:
                recommendation_rows.append(
                    {
                        "id": "reco-water-001",
                        "title": "급수 권장",
                        "detail": f"토양 수분 {latest_env.soil_moisture:.1f}% 로 낮아 400ml 급수가 권장됩니다.",
                        "priority": "HIGH",
                        "status": "PENDING",
                        "zone_id": latest_env.zone_id,
                        "device_id": "farm_01_watering",
                    }
                )

            nutrition_targets = (
                db.query(Plant)
                .filter(Plant.needs_nutrition.is_(True))
                .order_by(Plant.id.asc())
                .all()
            )
            if nutrition_targets:
                recommendation_rows.append(
                    {
                        "id": "reco-nutrient-001",
                        "title": "영양제 보정 권장",
                        "detail": f"{len(nutrition_targets)}개 식물에서 영양 보정이 필요합니다.",
                        "priority": "MEDIUM",
                        "status": "PENDING",
                        "zone_id": nutrition_targets[0].zone_id,
                        "device_id": "farm_01_nutrient",
                    }
                )

            return recommendation_rows
        finally:
            db.close()

    def create_manual_command(
        self,
        *,
        zone_id: str,
        device_id: str,
        command_type: str,
        target_value: float,
        value_unit: str,
        requested_by: str,
        request_source: str,
        recommendation_id: str | None = None,
    ) -> dict[str, Any]:
        # manual 명령를 새로 만들어 다음 처리 단계로 넘긴다.
        db = SessionLocal()
        try:
            device = db.query(IotDevice).filter(IotDevice.id == device_id).first()
            if device is None:
                raise FileNotFoundError(f"알 수 없는 device_id 입니다: {device_id}")

            dispatch_spec = _build_dispatch_spec(
                device_type=device.device_type,
                logical_command_type=command_type,
                target_value=target_value,
                value_unit=value_unit,
                recommendation_id=recommendation_id,
            )

            command = ActuationCommand(
                device_id=device.id,
                zone_id=zone_id,
                mission_id=None,
                observation_id=None,
                command_type=command_type,
                command_status="REQUESTED",
                target_value=target_value,
                value_unit=value_unit,
                requested_by=requested_by,
                request_source=request_source,
            )
            db.add(command)
            db.flush()

            dispatch_result = self._manual_command_dispatcher.dispatch_manual_command(
                command_id=_serialize_uuid(command.id),
                zone_id=zone_id,
                device_id=device.id,
                device_type=str(dispatch_spec["device_type"]),
                command_type=str(dispatch_spec["command_type"]),
                target_value=float(dispatch_spec["target_value"]),
                unit=str(dispatch_spec["unit"]),
                requested_by=requested_by,
                reason=str(dispatch_spec["reason"]),
            )
            command.command_status = "DISPATCHED" if dispatch_result.dispatched else "FAILED"

            log = ActuationLog(
                command_id=command.id,
                device_id=device.id,
                result="SUCCESS" if dispatch_result.dispatched else "FAILED",
                result_message=(
                    dispatch_result.detail_message
                    or (
                        f"{_command_title(command_type)} 완료"
                        + (f" · recommendation={recommendation_id}" if recommendation_id else "")
                    )
                ),
                state_after="ON" if dispatch_result.dispatched and target_value > 0 else "OFF",
                actual_value=target_value,
                value_unit=value_unit,
                started_at=datetime.utcnow(),
                finished_at=datetime.utcnow(),
            )
            db.add(log)

            if dispatch_result.dispatched:
                device.current_state = "ON" if target_value > 0 else "OFF"
                device.current_value = target_value
                device.value_unit = value_unit
                device.last_seen_at = datetime.utcnow()
            db.commit()

            return {
                "command_id": _serialize_uuid(command.id),
                "device_id": device.id,
                "device_name": device.display_name,
                "command_type": command.command_type,
                "command_status": command.command_status,
                "message": (
                    dispatch_result.detail_message
                    or f"{device.display_name} 제어 요청을 기록했습니다."
                ),
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def approve_recommendation(
        self,
        recommendation_id: str,
        *,
        reviewed_by: str,
        auto_execute: bool,
    ) -> dict[str, Any]:
        # approve recommendation 정보를 계산해 반환한다.
        recommendations = {item["id"]: item for item in self.list_recommendations()}
        recommendation = recommendations.get(recommendation_id)
        if recommendation is None:
            raise FileNotFoundError(f"알 수 없는 recommendation_id 입니다: {recommendation_id}")

        if not auto_execute:
            return {
                "id": recommendation_id,
                "status": "APPROVED",
                "message": f"{recommendation['title']} 승인 완료",
            }

        command_type = "WATERING" if "water" in recommendation_id else "NUTRIENTS"
        target_value = 400.0 if command_type == "WATERING" else 120.0
        value_unit = "ml"
        command = self.create_manual_command(
            zone_id=recommendation["zone_id"],
            device_id=recommendation["device_id"],
            command_type=command_type,
            target_value=target_value,
            value_unit=value_unit,
            requested_by=reviewed_by,
            request_source="recommendation_approval",
            recommendation_id=recommendation_id,
        )
        return {
            "id": recommendation_id,
            "status": "AUTO_EXECUTED",
            "message": f"{recommendation['title']} 승인 후 즉시 실행했습니다.",
            "command": command,
        }

    def list_actuation_history(self, limit: int = 20) -> list[dict[str, Any]]:
        # actuation 이력를 모아 순회하기 쉬운 형태로 정리한다.
        db = SessionLocal()
        try:
            logs = (
                db.query(ActuationLog)
                .options(joinedload(ActuationLog.device), joinedload(ActuationLog.command))
                .order_by(ActuationLog.finished_at.desc().nullslast(), ActuationLog.started_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": _serialize_uuid(log.id),
                    "command_id": _serialize_uuid(log.command_id),
                    "device_id": log.device_id,
                    "device_name": "" if log.device is None else log.device.display_name,
                    "command_type": "" if log.command is None else log.command.command_type,
                    "command_status": "" if log.command is None else log.command.command_status,
                    "result": log.result,
                    "result_message": log.result_message,
                    "state_after": log.state_after,
                    "actual_value": log.actual_value,
                    "value_unit": log.value_unit,
                    "started_at": _serialize_datetime(log.started_at),
                    "finished_at": _serialize_datetime(log.finished_at),
                }
                for log in logs
            ]
        finally:
            db.close()

    def list_harvest_history(self, limit: int = 20) -> list[dict[str, Any]]:
        # harvest 이력를 모아 순회하기 쉬운 형태로 정리한다.
        db = SessionLocal()
        try:
            events = (
                db.query(HarvestEvent)
                .options(joinedload(HarvestEvent.fruit), joinedload(HarvestEvent.plant))
                .order_by(HarvestEvent.harvested_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": _serialize_uuid(event.id),
                    "route_id": _serialize_uuid(event.mission_id) or event.fruit_id or event.plant_id,
                    "batch_id": _serialize_uuid(event.mission_id) or event.fruit_id or event.plant_id,
                    "name": event.fruit_id or event.plant_id,
                    "summary": (
                        f"{event.fruit_id or event.plant_id} 수확 {'성공' if event.success else '실패'}"
                    ),
                    "detail": event.fail_reason or f"{_plant_name(event.plant_id)}에서 수확 이벤트가 기록되었습니다.",
                    "state": "완료" if event.success else "실패",
                    "status": "succeeded" if event.success else "failed",
                    "mission_id": _serialize_uuid(event.mission_id),
                    "fruit_id": event.fruit_id,
                    "plant_id": event.plant_id,
                    "current_phase": "STOWING" if event.success else "FAILED",
                    "updated_at": _serialize_datetime(event.harvested_at),
                    "basket_count": event.basket_count,
                    "success": event.success,
                }
                for event in events
            ]
        finally:
            db.close()

    def get_harvest_stats(self) -> dict[str, Any]:
        # harvest stats를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        db = SessionLocal()
        try:
            events = db.query(HarvestEvent).order_by(HarvestEvent.harvested_at.desc()).all()
            successful = [event for event in events if event.success]
            failed = [event for event in events if not event.success]
            ready_count = db.query(Fruit).filter(Fruit.ready_to_harvest.is_(True)).count()
            latest = successful[0] if successful else None
            basket_count = 0 if latest is None or latest.basket_count is None else latest.basket_count
            active_mission = (
                db.query(Mission)
                .filter(Mission.mission_type == "HARVEST", Mission.status.in_(["PENDING", "RUNNING"]))
                .order_by(Mission.started_at.desc().nullslast())
                .first()
            )
            return {
                "today_weight_kg": f"{len(successful)}개",
                "today_harvest_kg": f"{len(successful)}개",
                "basket_fill_rate": f"{basket_count}개 적재",
                "basket_state": f"바구니 적재 {basket_count}개",
                "success_rate": (
                    "0.0%"
                    if not events
                    else f"{(len(successful) / len(events)) * 100:.1f}%"
                ),
                "failed_count": f"{len(failed)}건",
                "next_swap_eta": "교체 권장" if basket_count >= 5 else f"ready {ready_count}개 남음",
                "basket_count": basket_count,
                "remaining_ready_count": ready_count,
                "last_harvested_fruit_id": "" if latest is None or latest.fruit_id is None else latest.fruit_id,
                "mission_status": "" if active_mission is None else active_mission.status.lower(),
                "current_phase": "PICKING" if active_mission is not None else "",
                "active_mission_id": _serialize_uuid(None if active_mission is None else active_mission.id),
                "active_target_id": "" if active_mission is None else active_mission.target_fruit_id or "",
                "detail_message": (
                    "수확 미션 진행 중" if active_mission is not None else "최근 수확 이벤트 기준 통계"
                ),
                "loaded_fruit_ids": [event.fruit_id for event in successful if event.fruit_id],
            }
        finally:
            db.close()
