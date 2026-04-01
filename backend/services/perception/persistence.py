# 이 모듈은 인지 서비스 계층에서 인지 결과를 파일이나 저장소에 기록하는 로직을 모은다한다.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from database import SessionLocal
from models import (
    ActuationCommand,
    ActuationLog,
    Alert,
    CropObservation,
    Fruit,
    IotDevice,
    Plant,
    Robot,
    Zone,
)
from robot_map_service import _load_crop_instances
from services.actuation.schemas import ActuationDispatchResult, DiseaseTreatmentPlan, Point3D
from services.ai_judgments.service import AiJudgmentService
from services.perception.schemas import ThinInferenceConfirmRequest


DEFAULT_ZONE_ID = "farm_01"


@dataclass(frozen=True)
class PersistenceRefs:
    # persistence 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    robot_row_id: str
    zone_row_id: str
    plant_row_id: str
    crop_observation_row_id: str
    disease_judgment_row_id: str | None = None
    harvest_decision_row_id: str | None = None
    actuation_command_row_id: str | None = None
    actuation_log_row_id: str | None = None
    alert_row_id: str | None = None


class ObservationPersistenceService:
    # observation 저장 서비스 관련 핵심 흐름을 한곳에 모아 제공하는 서비스 클래스다.

    def __init__(self) -> None:
        # ObservationPersistenceService 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        self._ai_judgment_service = AiJudgmentService()

    def persist_confirmation(
        self,
        *,
        request: ThinInferenceConfirmRequest,
        reviewed_at: datetime,
        final_label: str,
        final_confidence: float,
        image_path: str,
        treatment_plan: DiseaseTreatmentPlan | None,
        dispatch_result: ActuationDispatchResult | None,
        model_name: str = "tomato_disease_detector",
        model_version: str = "v1",
    ) -> PersistenceRefs:
        # confirmation을 저장한다.
        db = SessionLocal()
        try:
            zone = _get_or_create_zone(db, request.zone_id)
            robot = _get_or_create_robot(db, request.robot_id, zone_id=zone.id)
            plant = _get_or_create_plant(
                db,
                zone_id=zone.id,
                plant_id=request.plant_id,
                target_position=request.target_position,
                reviewed_at=reviewed_at,
                final_label=final_label,
            )
            fruit = _get_or_create_fruit(
                db,
                plant=plant,
                fruit_id=request.fruit_id,
                target_position=request.target_position,
                reviewed_at=reviewed_at,
                final_label=final_label,
            )

            observation = CropObservation(
                robot_id=robot.id,
                mission_id=None,
                plant_id=plant.id,
                fruit_id=None if fruit is None else fruit.id,
                finding_label=final_label,
                confidence=float(final_confidence),
                recommended_action=_recommended_action(final_label, treatment_plan),
                evidence=_build_evidence_text(
                    request=request,
                    final_label=final_label,
                    final_confidence=final_confidence,
                    treatment_plan=treatment_plan,
                ),
                image_url=image_path,
                observed_at=reviewed_at,
            )
            db.add(observation)
            db.flush()

            disease_judgment = self._ai_judgment_service.create_disease_judgment(
                db=db,
                plant_id=plant.id,
                fruit_id="" if fruit is None else fruit.id,
                zone_id=zone.id,
                model_name=model_name,
                model_version=model_version,
                raw_label=final_label,
                confidence=float(final_confidence),
                image_url=image_path,
                created_at=reviewed_at,
                evidence=_build_ai_evidence_items(
                    request=request,
                    final_label=final_label,
                    final_confidence=final_confidence,
                    treatment_plan=treatment_plan,
                ),
            )
            harvest_decision = self._ai_judgment_service.maybe_create_harvest_decision(
                db=db,
                plant_id=plant.id,
                fruit_id="" if fruit is None else fruit.id,
                zone_id=zone.id,
                created_at=reviewed_at,
            )

            alert = _build_alert(
                robot=robot,
                zone=zone,
                plant=plant,
                observation=observation,
                reviewed_at=reviewed_at,
            )
            if alert is not None:
                db.add(alert)
                db.flush()

            command = _build_actuation_command(
                db=db,
                zone=zone,
                observation=observation,
                reviewed_at=reviewed_at,
                requested_by=request.requested_by,
                treatment_plan=treatment_plan,
                dispatch_result=dispatch_result,
            )
            if command is not None:
                db.add(command)
                db.flush()
            log = _build_actuation_log(
                command=command,
                reviewed_at=reviewed_at,
                dispatch_result=dispatch_result,
            )
            if log is not None:
                db.add(log)

            db.commit()
            return PersistenceRefs(
                robot_row_id=str(robot.id),
                zone_row_id=zone.id,
                plant_row_id=plant.id,
                crop_observation_row_id=str(observation.id),
                disease_judgment_row_id=disease_judgment.id,
                harvest_decision_row_id=None if harvest_decision is None else harvest_decision.id,
                actuation_command_row_id=None if command is None else str(command.id),
                actuation_log_row_id=None if log is None else str(log.id),
                alert_row_id=None if alert is None else str(alert.id),
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def _get_or_create_zone(db: Any, zone_id: str) -> Zone:
    # OR create 구역를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    normalized_zone_id = zone_id.strip() or DEFAULT_ZONE_ID
    zone = db.query(Zone).filter(Zone.id == normalized_zone_id).first()
    if zone is not None:
        return zone

    zone = Zone(
        id=normalized_zone_id,
        name="Farm 01",
        bounds={"min_x": -10.0, "max_x": 10.0, "min_y": -10.0, "max_y": 10.0},
        description="farm_world 전체 운영 구역",
    )
    db.add(zone)
    db.flush()
    return zone


def _get_or_create_robot(db: Any, robot_name: str, *, zone_id: str) -> Robot:
    # OR create robot를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    normalized_robot_name = robot_name.strip() or "AGR-02"
    robot = db.query(Robot).filter(Robot.name == normalized_robot_name).first()
    if robot is not None:
        robot.current_zone_id = zone_id
        robot.updated_at = datetime.utcnow()
        return robot

    robot = Robot(
        name=normalized_robot_name,
        status="PATROL",
        battery_level=82.0,
        current_zone_id=zone_id,
        current_pose=None,
        updated_at=datetime.utcnow(),
    )
    db.add(robot)
    db.flush()
    return robot


def _point_to_json(point: Point3D | None) -> dict[str, float]:
    # point json 정보를 계산해 반환한다.
    if point is None:
        return {"x": 0.0, "y": 0.0, "z": 0.0}
    return {
        "x": float(point.x),
        "y": float(point.y),
        "z": float(point.z),
    }


@lru_cache(maxsize=1)
def _canonical_plant_positions() -> dict[str, dict[str, float]]:
    # 기준 작물 위치 목록 정보를 계산해 반환한다.
    crop_instances = _load_crop_instances()
    positions: dict[str, dict[str, float]] = {}

    for plant in crop_instances.get("plants", []):
        plant_id = str(plant.get("plant_id", "")).strip()
        pose = plant.get("pose")
        if not plant_id or not isinstance(pose, dict):
            continue
        positions[plant_id] = {
            "x": float(pose.get("x", 0.0)),
            "y": float(pose.get("y", 0.0)),
            "z": float(pose.get("z", 0.0)),
        }

    return positions


def _canonical_plant_position(plant_id: str) -> dict[str, float] | None:
    # 기준 작물 위치 정보를 계산해 반환한다.
    return _canonical_plant_positions().get(plant_id.strip())


def _get_or_create_plant(
    db: Any,
    *,
    zone_id: str,
    plant_id: str,
    target_position: Point3D | None,
    reviewed_at: datetime,
    final_label: str,
) -> Plant:
    # OR create 작물 개체를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    normalized_plant_id = plant_id.strip() or "farm01_plant_unknown"
    plant = db.query(Plant).filter(Plant.id == normalized_plant_id).first()
    if plant is None:
        canonical_position = _canonical_plant_position(normalized_plant_id)
        plant = Plant(
            id=normalized_plant_id,
            zone_id=zone_id,
            crop_name="tomato",
            position=canonical_position or _point_to_json(target_position),
            needs_water=False,
            ready_to_harvest=False,
            needs_nutrition=False,
            last_observed_at=reviewed_at,
        )
        db.add(plant)
        db.flush()
    else:
        canonical_position = _canonical_plant_position(normalized_plant_id)
        if canonical_position is not None:
            plant.position = canonical_position
        plant.last_observed_at = reviewed_at

    if "calcium" in final_label or "blossom_end_rot" in final_label:
        plant.needs_nutrition = True
    if "ripe" in final_label:
        plant.ready_to_harvest = True
    return plant


def _get_or_create_fruit(
    db: Any,
    *,
    plant: Plant,
    fruit_id: str,
    target_position: Point3D | None,
    reviewed_at: datetime,
    final_label: str,
) -> Fruit | None:
    # OR create fruit를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    normalized_fruit_id = fruit_id.strip()
    if not normalized_fruit_id:
        return None

    fruit = db.query(Fruit).filter(Fruit.id == normalized_fruit_id).first()
    if fruit is None:
        fruit = Fruit(
            id=normalized_fruit_id,
            plant_id=plant.id,
            position=_point_to_json(target_position),
            ripeness_stage="RIPE" if "ripe" in final_label else "TURNING",
            ready_to_harvest="ripe" in final_label,
            current_status="VISIBLE",
            last_observed_at=reviewed_at,
        )
        db.add(fruit)
        db.flush()
    else:
        if target_position is not None:
            fruit.position = _point_to_json(target_position)
        fruit.last_observed_at = reviewed_at
        if "ripe" in final_label:
            fruit.ripeness_stage = "RIPE"
            fruit.ready_to_harvest = True
    return fruit


def _recommended_action(
    final_label: str,
    treatment_plan: DiseaseTreatmentPlan | None,
) -> str:
    # recommended action 정보를 계산해 반환한다.
    normalized = final_label.strip().lower()
    if treatment_plan is not None and treatment_plan.action_required and treatment_plan.treatment_label:
        return treatment_plan.treatment_label
    if "ripe" in normalized:
        return "수확 요청"
    if normalized in {"healthy_leaf", "healthy", "normal"}:
        return "추가 관찰 유지"
    return "운영자 재확인"


def _build_evidence_text(
    *,
    request: ThinInferenceConfirmRequest,
    final_label: str,
    final_confidence: float,
    treatment_plan: DiseaseTreatmentPlan | None,
) -> str:
    # evidence text를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    evidence = (
        f"preliminary={request.preliminary_label or 'n/a'}, "
        f"final={final_label}, confidence={final_confidence:.2f}"
    )
    if request.bbox is not None:
        evidence += (
            f", bbox=({request.bbox.x1:.1f},{request.bbox.y1:.1f})-"
            f"({request.bbox.x2:.1f},{request.bbox.y2:.1f})"
        )
    if treatment_plan is not None and treatment_plan.reason:
        evidence += f", treatment_reason={treatment_plan.reason}"
    return evidence


def _build_ai_evidence_items(
    *,
    request: ThinInferenceConfirmRequest,
    final_label: str,
    final_confidence: float,
    treatment_plan: DiseaseTreatmentPlan | None,
) -> list[str]:
    # AI evidence items를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    evidence = [
        f"사전 감지 라벨 {request.preliminary_label or 'n/a'}",
        f"최종 확정 라벨 {final_label}",
        f"모델 신뢰도 {final_confidence:.2f}",
    ]
    if request.bbox is not None:
        evidence.append(
            "bbox="
            f"({request.bbox.x1:.1f},{request.bbox.y1:.1f})-"
            f"({request.bbox.x2:.1f},{request.bbox.y2:.1f})"
        )
    if treatment_plan is not None and treatment_plan.reason:
        evidence.append(f"조치 근거 {treatment_plan.reason}")
    return evidence


def _build_alert(
    *,
    robot: Robot,
    zone: Zone,
    plant: Plant,
    observation: CropObservation,
    reviewed_at: datetime,
) -> Alert | None:
    # alert를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    normalized = observation.finding_label.strip().lower()
    if normalized in {"healthy_leaf", "healthy", "normal", "ripe_tomato"}:
        return None

    severity = "WARNING"
    if "powdery" in normalized or "gray_mold" in normalized:
        severity = "CRITICAL"

    return Alert(
        robot_id=robot.id,
        zone_id=zone.id,
        plant_id=plant.id,
        observation_id=observation.id,
        alert_type="DISEASE",
        severity=severity,
        message=f"{plant.id} 에서 {observation.finding_label} 감지",
        image_url=observation.image_url,
        acknowledged_at=None,
        acknowledged_by=None,
        detected_at=reviewed_at,
    )


def _get_or_create_device(
    db: Any,
    *,
    device_id: str,
    zone_id: str,
) -> IotDevice:
    # OR create 장치를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    device = db.query(IotDevice).filter(IotDevice.id == device_id).first()
    if device is not None:
        return device

    device = IotDevice(
        id=device_id,
        zone_id=zone_id,
        device_type="SPRINKLER" if "sprinkler" in device_id else "WATER_PUMP",
        display_name=device_id,
        control_mode="AUTO",
        current_state="OFF",
        current_value=0.0,
        value_unit="sec",
        is_online=True,
        last_seen_at=datetime.utcnow(),
    )
    db.add(device)
    db.flush()
    return device


def _build_actuation_command(
    *,
    db: Any,
    zone: Zone,
    observation: CropObservation,
    reviewed_at: datetime,
    requested_by: str,
    treatment_plan: DiseaseTreatmentPlan | None,
    dispatch_result: ActuationDispatchResult | None,
) -> ActuationCommand | None:
    # actuation 명령를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    if treatment_plan is None or dispatch_result is None:
        return None
    if not treatment_plan.action_required or treatment_plan.command_payload is None:
        return None

    device_id = (
        dispatch_result.device_id
        or (treatment_plan.selected_sprinkler.device_id if treatment_plan.selected_sprinkler else "")
        or str(treatment_plan.command_payload.get("device_id", ""))
    )
    if not device_id:
        return None

    device = _get_or_create_device(db, device_id=device_id, zone_id=zone.id)
    target_value = treatment_plan.command_payload.get("target_value")
    return ActuationCommand(
        device_id=device.id,
        zone_id=zone.id,
        mission_id=None,
        observation_id=observation.id,
        command_type=str(treatment_plan.command_payload.get("command_type", "SPRAY_PESTICIDE")).upper(),
        command_status=str(dispatch_result.status or "REQUESTED").upper(),
        target_value=None if target_value is None else float(target_value),
        value_unit=str(treatment_plan.command_payload.get("unit", "sec")),
        requested_by=requested_by.strip() or "backend:inference",
        request_source="AI_CONFIRMATION",
        requested_at=reviewed_at,
    )


def _build_actuation_log(
    *,
    command: ActuationCommand | None,
    reviewed_at: datetime,
    dispatch_result: ActuationDispatchResult | None,
) -> ActuationLog | None:
    # actuation LOG를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    if command is None or dispatch_result is None:
        return None

    result = "SUCCESS" if dispatch_result.dispatched else "FAILED"
    return ActuationLog(
        command_id=command.id,
        device_id=command.device_id,
        result=result,
        result_message=dispatch_result.detail_message,
        state_after="ON" if dispatch_result.dispatched else "ERROR",
        actual_value=command.target_value,
        value_unit=command.value_unit,
        started_at=reviewed_at,
        finished_at=reviewed_at,
    )
