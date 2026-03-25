from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from database import SessionLocal
from models import ActuationLog, CropObservation, Plant, Robot, Zone
from services.actuation.schemas import ActuationDispatchResult, DiseaseTreatmentPlan, Point3D
from services.perception.schemas import ThinInferenceConfirmRequest


_ZONE_ALIASES = {
    'farm_01': 'farm_01',
    'greenhouse_01': 'farm_01',
}


@dataclass(frozen=True)
class PersistenceRefs:
    robot_row_id: int
    zone_row_id: int
    plant_row_id: int
    crop_observation_row_id: int
    actuation_log_row_id: int | None = None


class ObservationPersistenceService:
    """Persist backend-confirmed disease observations and any resulting treatment logs."""

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
    ) -> PersistenceRefs:
        db = SessionLocal()
        try:
            zone = _get_or_create_zone(db, request.zone_id)
            robot = _get_or_create_robot(db, request.robot_id)
            plant = _get_or_create_plant(
                db,
                zone=zone,
                plant_name=request.plant_id,
                target_position=request.target_position,
                reviewed_at=reviewed_at,
            )
            observation = CropObservation(
                robot_id=robot.id,
                plant_id=plant.id,
                misson_id=None,
                class_name=final_label,
                confidence=float(final_confidence),
                health_score=_estimate_health_score(final_label),
                image_url=image_path,
                observed_at=reviewed_at,
            )
            db.add(observation)
            actuation_log = _build_actuation_log(
                robot=robot,
                zone=zone,
                reviewed_at=reviewed_at,
                treatment_plan=treatment_plan,
                dispatch_result=dispatch_result,
            )
            if actuation_log is not None:
                db.add(actuation_log)

            db.commit()
            db.refresh(observation)
            if actuation_log is not None:
                db.refresh(actuation_log)

            return PersistenceRefs(
                robot_row_id=int(robot.id),
                zone_row_id=int(zone.id),
                plant_row_id=int(plant.id),
                crop_observation_row_id=int(observation.id),
                actuation_log_row_id=None if actuation_log is None else int(actuation_log.id),
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def _get_or_create_zone(db: Any, zone_name: str) -> Zone:
    normalized_zone_name = _normalize_zone_name(zone_name)
    zone = db.query(Zone).filter(Zone.name == normalized_zone_name).first()
    if zone is not None:
        return zone

    zone = Zone(
        name=normalized_zone_name,
        bounds=None,
    )
    db.add(zone)
    db.flush()
    return zone


def _get_or_create_robot(db: Any, robot_name: str) -> Robot:
    normalized_robot_name = robot_name.strip() or 'agribot'
    robot = db.query(Robot).filter(Robot.name == normalized_robot_name).first()
    if robot is not None:
        return robot

    robot = Robot(
        name=normalized_robot_name,
        status='IDLE',
        battery=None,
        current_pose=None,
    )
    db.add(robot)
    db.flush()
    return robot


def _get_or_create_plant(
    db: Any,
    *,
    zone: Zone,
    plant_name: str,
    target_position: Point3D | None,
    reviewed_at: datetime,
) -> Plant:
    normalized_plant_name = plant_name.strip() or f'{zone.name}_unknown_target'
    plant = (
        db.query(Plant)
        .filter(Plant.zone_id == zone.id, Plant.name == normalized_plant_name)
        .first()
    )
    if plant is None:
        plant = Plant(
            zone_id=zone.id,
            position=_point_to_json(target_position),
            health_score=None,
            growth_stage='',
            name=normalized_plant_name,
            read_water=None,
            ready_harvest=None,
            last_observed=reviewed_at,
        )
        db.add(plant)
        db.flush()
    else:
        if target_position is not None:
            plant.position = _point_to_json(target_position)
        plant.last_observed = reviewed_at

    return plant


def _build_actuation_log(
    *,
    robot: Robot,
    zone: Zone,
    reviewed_at: datetime,
    treatment_plan: DiseaseTreatmentPlan | None,
    dispatch_result: ActuationDispatchResult | None,
) -> ActuationLog | None:
    if treatment_plan is None or dispatch_result is None:
        return None
    if not treatment_plan.action_required:
        return None

    command_payload = treatment_plan.command_payload or {}
    target_value = command_payload.get('target_value')
    amount_ml = float(target_value) if target_value is not None else None

    return ActuationLog(
        robot_id=robot.id,
        zone_id=zone.id,
        action_type=str(
            command_payload.get('command_type')
            or treatment_plan.treatment_type
            or 'treatment'
        ),
        amount_ml=amount_ml,
        executed_at=reviewed_at,
        success=bool(dispatch_result.dispatched),
    )


def _point_to_json(point: Point3D | None) -> dict[str, float] | None:
    if point is None:
        return None
    return {
        'x': float(point.x),
        'y': float(point.y),
        'z': float(point.z),
    }


def _normalize_zone_name(zone_name: str) -> str:
    normalized = zone_name.strip().lower()
    if not normalized:
        return 'farm_01'
    return _ZONE_ALIASES.get(normalized, normalized)


def _estimate_health_score(label: str) -> float:
    normalized = label.strip().lower()
    if not normalized:
        return 0.0
    if normalized in {'healthy', 'healthy_leaf', 'normal', 'normal_leaf'}:
        return 1.0
    if 'powdery' in normalized or 'gray_mold' in normalized:
        return 0.15
    if 'calcium' in normalized:
        return 0.35
    if 'crack' in normalized:
        return 0.45
    return 0.25
