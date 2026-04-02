from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from database import Base, SQLALCHEMY_DATABASE_URL, SessionLocal, engine
from models import (
    ActuationCommand,
    ActuationLog,
    Alert,
    AiJudgment,
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
from robot_map_service import _load_crop_instances, _load_iot_devices, read_map_payload
from services.ai_judgments.policy import (
    build_disease_interpretation,
    build_harvest_decision_interpretation,
    build_ripeness_interpretation,
)

ROBOT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
PATROL_MISSION_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
DEFAULT_ZONE_ID = "farm_01"
DEFAULT_ROBOT_NAME = "AGR-02"


@dataclass(frozen=True)
class DiseaseScenario:
    finding_label: str
    recommended_action: str
    evidence: str
    device_id: str
    command_type: str
    target_value: float
    value_unit: str
    severity: str


DISEASE_SCENARIOS: dict[str, DiseaseScenario] = {
    "farm01_plant_06": DiseaseScenario(
        finding_label="tomato_powdery_mildew",
        recommended_action="약제 살포",
        evidence="잎 표면 흰가루 패턴과 가장자리 변색이 확인되었습니다.",
        device_id="sprinkler_1",
        command_type="SPRAY_PESTICIDE",
        target_value=3.0,
        value_unit="sec",
        severity="CRITICAL",
    ),
    "farm01_plant_15": DiseaseScenario(
        finding_label="tomato_gray_mold",
        recommended_action="약제 살포",
        evidence="과실 주변 회색 곰팡이성 패턴이 확인되었습니다.",
        device_id="sprinkler_2",
        command_type="SPRAY_PESTICIDE",
        target_value=3.5,
        value_unit="sec",
        severity="CRITICAL",
    ),
    "farm01_plant_22": DiseaseScenario(
        finding_label="tomato_blossom_end_rot",
        recommended_action="칼슘액비 살포",
        evidence="과실 하단 흑변과 칼슘 결핍 패턴이 확인되었습니다.",
        device_id="sprinkler_1",
        command_type="SPRAY_CALCIUM_SOLUTION",
        target_value=2.5,
        value_unit="sec",
        severity="WARNING",
    ),
}

HARVESTED_FRUITS = {
    "farm01_plant_01_tomato_01": True,
    "farm01_plant_03_tomato_01": True,
    "farm01_plant_19_tomato_01": False,
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="새 greenhouse 스키마를 생성하고 데모 데이터를 적재합니다.")
    parser.add_argument("--dry-run", action="store_true", help="DB 변경 없이 요약만 출력합니다.")
    return parser.parse_args()


def _serialize_dt(value: datetime | None) -> str:
    return "" if value is None else value.isoformat()


def _device_type(raw_type: str) -> str:
    mapping = {
        "watering": "WATER_PUMP",
        "nutrient": "NUTRIENT",
        "sprinkler": "SPRINKLER",
    }
    return mapping.get(raw_type.strip().lower(), raw_type.strip().upper())


def _device_unit(raw_type: str) -> str:
    mapping = {
        "watering": "ml",
        "nutrient": "ml",
        "sprinkler": "sec",
    }
    return mapping.get(raw_type.strip().lower(), "unit")


def _device_initial_state(raw_type: str) -> str:
    return "OFF"


def _display_name(plant_id: str) -> str:
    suffix = plant_id.split("_")[-1]
    return f"토마토 식물 {suffix}"


def _uuid5(label: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"agribot-demo:{label}")


def _fruit_status(fruit_id: str) -> tuple[str, bool]:
    if fruit_id in HARVESTED_FRUITS:
        success = HARVESTED_FRUITS[fruit_id]
        return ("HARVESTED" if success else "LOST", False)
    if fruit_id in {
        "farm01_plant_02_tomato_01",
        "farm01_plant_04_tomato_01",
        "farm01_plant_11_tomato_01",
        "farm01_plant_12_tomato_01",
    }:
        return ("VISIBLE", True)
    return ("VISIBLE", False)


def _ripeness_stage(fruit_id: str) -> str:
    if fruit_id in HARVESTED_FRUITS or fruit_id in {
        "farm01_plant_02_tomato_01",
        "farm01_plant_04_tomato_01",
        "farm01_plant_11_tomato_01",
        "farm01_plant_12_tomato_01",
    }:
        return "RIPE"
    return "TURNING"


def _ripeness_label(*, ready_to_harvest: bool) -> str:
    return "ripe" if ready_to_harvest else "turning"


def _reset_schema(db: Any) -> None:
    db.execute(
        text(
            """
            DROP TABLE IF EXISTS
                actuation_logs,
                actuation_commands,
                ai_judgments,
                alerts,
                harvest_events,
                crop_observations,
                missions,
                missons,
                fruits,
                plants,
                environment_samples,
                iot_devices,
                robots,
                zones
            CASCADE
            """
        )
    )
    db.commit()


def _build_dataset() -> dict[str, Any]:
    crop_catalog = _load_crop_instances()
    device_catalog = _load_iot_devices()
    map_payload = read_map_payload("farm_map")
    now = datetime.utcnow().replace(microsecond=0)

    zone = Zone(
        id=DEFAULT_ZONE_ID,
        name="Farm 01",
        bounds=map_payload["bounds"],
        description="farm_world 전체를 하나의 운영 구역으로 사용합니다.",
    )
    robot = Robot(
        id=ROBOT_ID,
        name=DEFAULT_ROBOT_NAME,
        status="PATROL",
        battery_level=82.0,
        current_zone_id=DEFAULT_ZONE_ID,
        current_pose={"x": 0.0, "y": -8.6, "z": 0.0, "yaw": 1.57, "frame_id": "map"},
        updated_at=now,
    )
    patrol_mission = Mission(
        id=PATROL_MISSION_ID,
        robot_id=ROBOT_ID,
        mission_type="PATROL",
        target_zone_id=DEFAULT_ZONE_ID,
        target_plant_id=None,
        target_fruit_id=None,
        status="RUNNING",
        progress_percent=68,
        started_at=now - timedelta(minutes=18),
        completed_at=None,
    )

    devices: list[IotDevice] = []
    for device_id, payload in sorted(device_catalog.items()):
        raw_type = str(payload.get("device_type", "")).strip()
        devices.append(
            IotDevice(
                id=device_id,
                zone_id=str(payload.get("zone_id", DEFAULT_ZONE_ID)),
                device_type=_device_type(raw_type),
                display_name=str(payload.get("display_name", device_id)),
                control_mode="AUTO",
                current_state=_device_initial_state(raw_type),
                current_value=0.0,
                value_unit=_device_unit(raw_type),
                is_online=True,
                last_seen_at=now,
            )
        )

    plants: list[Plant] = []
    fruits: list[Fruit] = []
    observations: list[CropObservation] = []
    alerts: list[Alert] = []
    ai_judgments: list[AiJudgment] = []
    actuation_commands: list[ActuationCommand] = []
    actuation_logs: list[ActuationLog] = []
    harvest_events: list[HarvestEvent] = []
    missions: list[Mission] = [patrol_mission]
    environment_samples: list[EnvironmentSample] = []

    tomatoes_by_plant = {
        str(item.get("parent_plant_id", "")): item
        for item in crop_catalog.get("tomatoes", [])
        if isinstance(item, dict)
    }

    for sample_index in range(6):
        recorded_at = now - timedelta(minutes=(5 - sample_index) * 5)
        environment_samples.append(
            EnvironmentSample(
                id=_uuid5(f"env-{sample_index}"),
                zone_id=DEFAULT_ZONE_ID,
                temperature=24.2 + sample_index * 0.4,
                humidity=57.5 + sample_index * 1.2,
                soil_moisture=28.0 + sample_index * 0.8,
                recorded_at=recorded_at,
            )
        )

    basket_count = 0
    for index, plant_payload in enumerate(crop_catalog.get("plants", []), start=1):
        if not isinstance(plant_payload, dict):
            continue

        plant_id = str(plant_payload.get("plant_id", "")).strip()
        pose = dict(plant_payload.get("pose", {}))
        tomato_payload = tomatoes_by_plant.get(plant_id, {})
        fruit_id = str(tomato_payload.get("tomato_id", "")).strip()
        fruit_pose = dict(tomato_payload.get("pose", {}))
        scenario = DISEASE_SCENARIOS.get(plant_id)
        fruit_status, ready_to_harvest = _fruit_status(fruit_id)
        ripeness_stage = _ripeness_stage(fruit_id)
        needs_nutrition = scenario is not None and "칼슘" in scenario.recommended_action
        needs_water = index % 5 == 0
        last_observed_at = now - timedelta(minutes=max(1, 26 - index))

        plants.append(
            Plant(
                id=plant_id,
                zone_id=DEFAULT_ZONE_ID,
                crop_name="tomato",
                position={
                    "x": float(pose.get("x", 0.0)),
                    "y": float(pose.get("y", 0.0)),
                    "z": float(pose.get("z", 0.75)),
                    "yaw": float(pose.get("yaw", 0.0)),
                },
                needs_water=needs_water,
                ready_to_harvest=ready_to_harvest,
                needs_nutrition=needs_nutrition,
                last_observed_at=last_observed_at,
            )
        )

        fruits.append(
            Fruit(
                id=fruit_id,
                plant_id=plant_id,
                position={
                    "x": float(fruit_pose.get("x", pose.get("x", 0.0))),
                    "y": float(fruit_pose.get("y", pose.get("y", 0.0))),
                    "z": float(fruit_pose.get("z", 1.05)),
                },
                ripeness_stage=ripeness_stage,
                ready_to_harvest=ready_to_harvest,
                current_status=fruit_status,
                last_observed_at=last_observed_at,
            )
        )

        if scenario is None:
            finding_label = "ripe_tomato" if ready_to_harvest else "healthy_leaf"
            recommended_action = "수확 요청 가능" if ready_to_harvest else "추가 관찰 유지"
            evidence = "정상 생육 패턴이 확인되었습니다."
            image_url = "/mock-images/healthy-default.jpg"
        else:
            finding_label = scenario.finding_label
            recommended_action = scenario.recommended_action
            evidence = scenario.evidence
            image_url = "/mock-images/disease-closeup.png"

        observation_id = _uuid5(f"obs:{plant_id}")
        observations.append(
            CropObservation(
                id=observation_id,
                robot_id=ROBOT_ID,
                mission_id=PATROL_MISSION_ID,
                plant_id=plant_id,
                fruit_id=fruit_id,
                finding_label=finding_label,
                confidence=0.97 if scenario is not None else 0.94,
                recommended_action=recommended_action,
                evidence=evidence,
                image_url=image_url,
                observed_at=last_observed_at,
            )
        )

        disease_raw_label = scenario.finding_label if scenario is not None else "healthy_leaf"
        disease_confidence = 0.97 if scenario is not None else 0.94
        disease_interpretation = build_disease_interpretation(
            disease_raw_label,
            disease_confidence,
            extra_evidence=[
                evidence,
                f"plant_id={plant_id}",
                f"fruit_id={fruit_id}",
            ],
        )
        ai_judgments.append(
            AiJudgment(
                id=_uuid5(f"ai:disease:{plant_id}"),
                plant_id=plant_id,
                fruit_id=fruit_id,
                zone_id=DEFAULT_ZONE_ID,
                judgment_type="DISEASE",
                model_name="tomato_disease_detector",
                model_version="v1",
                raw_label=disease_raw_label,
                canonical_code=disease_interpretation.canonical_code,
                confidence=disease_confidence,
                risk_level=disease_interpretation.risk_level,
                recommended_action_code=disease_interpretation.recommended_action_code,
                requires_approval=disease_interpretation.requires_approval,
                payload_json=disease_interpretation.payload_json,
                image_url=image_url,
                created_at=last_observed_at + timedelta(seconds=5),
            )
        )

        ripeness_raw_label = _ripeness_label(ready_to_harvest=ready_to_harvest)
        ripeness_confidence = 0.94
        ripeness_interpretation = build_ripeness_interpretation(
            ripeness_raw_label,
            ripeness_confidence,
            extra_evidence=[
                f"fruit_status={fruit_status}",
                f"ripeness_stage={ripeness_stage}",
            ],
        )
        ai_judgments.append(
            AiJudgment(
                id=_uuid5(f"ai:ripeness:{fruit_id}"),
                plant_id=plant_id,
                fruit_id=fruit_id,
                zone_id=DEFAULT_ZONE_ID,
                judgment_type="RIPENESS",
                model_name="ripeness_classifier_v1",
                model_version="v1",
                raw_label=ripeness_raw_label,
                canonical_code=ripeness_interpretation.canonical_code,
                confidence=ripeness_confidence,
                risk_level=ripeness_interpretation.risk_level,
                recommended_action_code=ripeness_interpretation.recommended_action_code,
                requires_approval=ripeness_interpretation.requires_approval,
                payload_json=ripeness_interpretation.payload_json,
                image_url=image_url,
                created_at=last_observed_at + timedelta(seconds=10),
            )
        )

        harvest_interpretation = build_harvest_decision_interpretation(
            disease_judgment={
                "canonical_code": disease_interpretation.canonical_code,
                "risk_level": disease_interpretation.risk_level,
            },
            ripeness_judgment={
                "canonical_code": ripeness_interpretation.canonical_code,
                "risk_level": ripeness_interpretation.risk_level,
            },
        )
        if harvest_interpretation is not None:
            ai_judgments.append(
                AiJudgment(
                    id=_uuid5(f"ai:harvest:{fruit_id}"),
                    plant_id=plant_id,
                    fruit_id=fruit_id,
                    zone_id=DEFAULT_ZONE_ID,
                    judgment_type="HARVEST_DECISION",
                    model_name="harvest_decision_fusion",
                    model_version="v1",
                    raw_label=harvest_interpretation.canonical_code,
                    canonical_code=harvest_interpretation.canonical_code,
                    confidence=min(disease_confidence, ripeness_confidence),
                    risk_level=harvest_interpretation.risk_level,
                    recommended_action_code=harvest_interpretation.recommended_action_code,
                    requires_approval=harvest_interpretation.requires_approval,
                    payload_json=harvest_interpretation.payload_json,
                    image_url=image_url,
                    created_at=last_observed_at + timedelta(seconds=15),
                )
            )

        if scenario is not None:
            alert_id = _uuid5(f"alert:{plant_id}")
            alerts.append(
                Alert(
                    id=alert_id,
                    robot_id=ROBOT_ID,
                    zone_id=DEFAULT_ZONE_ID,
                    plant_id=plant_id,
                    observation_id=observation_id,
                    alert_type="DISEASE",
                    severity=scenario.severity,
                    message=f"{_display_name(plant_id)} 에서 {scenario.finding_label} 이 감지되었습니다.",
                    image_url="/mock-images/disease-closeup.png",
                    acknowledged_at=None,
                    acknowledged_by=None,
                    detected_at=last_observed_at + timedelta(seconds=30),
                )
            )

            command_id = _uuid5(f"command:{plant_id}")
            actuation_commands.append(
                ActuationCommand(
                    id=command_id,
                    device_id=scenario.device_id,
                    zone_id=DEFAULT_ZONE_ID,
                    mission_id=PATROL_MISSION_ID,
                    observation_id=observation_id,
                    command_type=scenario.command_type,
                    command_status="COMPLETED",
                    target_value=scenario.target_value,
                    value_unit=scenario.value_unit,
                    requested_by="backend:demo-seed",
                    request_source="AI_CONFIRMATION",
                    requested_at=last_observed_at + timedelta(minutes=2),
                )
            )
            actuation_logs.append(
                ActuationLog(
                    id=_uuid5(f"log:{plant_id}"),
                    command_id=command_id,
                    device_id=scenario.device_id,
                    result="SUCCESS",
                    result_message=f"{scenario.recommended_action} 완료",
                    state_after="ON",
                    actual_value=scenario.target_value,
                    value_unit=scenario.value_unit,
                    started_at=last_observed_at + timedelta(minutes=2),
                    finished_at=last_observed_at + timedelta(minutes=2, seconds=10),
                )
            )

        if fruit_id in HARVESTED_FRUITS:
            success = HARVESTED_FRUITS[fruit_id]
            if success:
                basket_count += 1
            harvest_mission_id = _uuid5(f"mission:harvest:{fruit_id}")
            missions.append(
                Mission(
                    id=harvest_mission_id,
                    robot_id=ROBOT_ID,
                    mission_type="HARVEST",
                    target_zone_id=DEFAULT_ZONE_ID,
                    target_plant_id=plant_id,
                    target_fruit_id=fruit_id,
                    status="COMPLETED" if success else "FAILED",
                    progress_percent=100 if success else 72,
                    started_at=last_observed_at + timedelta(minutes=2),
                    completed_at=last_observed_at + timedelta(minutes=4),
                )
            )
            harvest_events.append(
                HarvestEvent(
                    id=_uuid5(f"harvest:{fruit_id}"),
                    plant_id=plant_id,
                    fruit_id=fruit_id,
                    robot_id=ROBOT_ID,
                    mission_id=harvest_mission_id,
                    success=success,
                    fail_reason=None if success else "target_lost",
                    basket_count=basket_count,
                    harvested_at=last_observed_at + timedelta(minutes=4),
                )
            )

    return {
        "zone": zone,
        "robot": robot,
        "missions": missions,
        "devices": devices,
        "plants": plants,
        "fruits": fruits,
        "environment_samples": environment_samples,
        "observations": observations,
        "alerts": alerts,
        "ai_judgments": ai_judgments,
        "actuation_commands": actuation_commands,
        "actuation_logs": actuation_logs,
        "harvest_events": harvest_events,
    }


def _print_summary(dataset: dict[str, Any], *, dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "APPLY"
    print(f"[{mode}] database_url={SQLALCHEMY_DATABASE_URL}")
    print(f"zone={dataset['zone'].id}")
    print(f"robot={dataset['robot'].name}")
    print(
        "counts="
        f"plants:{len(dataset['plants'])}, "
        f"fruits:{len(dataset['fruits'])}, "
        f"devices:{len(dataset['devices'])}, "
        f"environment:{len(dataset['environment_samples'])}, "
        f"observations:{len(dataset['observations'])}, "
        f"alerts:{len(dataset['alerts'])}, "
        f"ai_judgments:{len(dataset['ai_judgments'])}, "
        f"commands:{len(dataset['actuation_commands'])}, "
        f"logs:{len(dataset['actuation_logs'])}, "
        f"harvest_events:{len(dataset['harvest_events'])}"
    )
    for plant_id, scenario in DISEASE_SCENARIOS.items():
        print(
            "scenario="
            f"plant={plant_id} "
            f"zone={DEFAULT_ZONE_ID} "
            f"device={scenario.device_id} "
            f"finding={scenario.finding_label} "
            f"action={scenario.recommended_action}"
        )


def _apply_dataset(dataset: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        _reset_schema(db)
        Base.metadata.create_all(bind=engine)
        db.add(dataset["zone"])
        db.add(dataset["robot"])
        db.add_all(dataset["missions"])
        db.add_all(dataset["devices"])
        db.add_all(dataset["plants"])
        db.add_all(dataset["fruits"])
        db.add_all(dataset["environment_samples"])
        db.add_all(dataset["observations"])
        db.add_all(dataset["alerts"])
        db.add_all(dataset["ai_judgments"])
        db.add_all(dataset["actuation_commands"])
        db.add_all(dataset["actuation_logs"])
        db.add_all(dataset["harvest_events"])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    args = _parse_args()
    dataset = _build_dataset()
    _print_summary(dataset, dry_run=args.dry_run)
    if args.dry_run:
        return
    _apply_dataset(dataset)


if __name__ == "__main__":
    main()
