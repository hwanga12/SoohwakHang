from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text

from database import Base, SQLALCHEMY_DATABASE_URL, SessionLocal, engine
from models import (
    ActuationLog,
    Alert,
    CropObservation,
    EnvironmentSample,
    HarvestEvent,
    Mission,
    Plant,
    Robot,
    Zone,
)
from robot_map_service import _load_crop_instances, read_map_payload, read_pose_payload
from zone_service import guess_zone_id_for_x, read_zones_payload

DEMO_TAG = "[demo-seed]"
DEFAULT_ZONE_NAME = "farm_01"
ROBOT_NAME = "agribot"
ROBOT_STATUS = "PATROL"
MISSION_TYPE = "PATROL"
MISSION_STATUS = "RUNNING"

HEALTHY_IMAGE_URL = "/mock-images/greenhouse-overview.png"
DISEASE_IMAGE_URL = "/mock-images/disease-closeup.png"
@dataclass(frozen=True)
class DiseasePlan:
    label: str
    confidence: float
    health_score: float
    chemical_name: str
    amount_ml: float
    follow_up_alert: str


DISEASE_CASES: dict[str, DiseasePlan] = {
    "farm01_plant_06": DiseasePlan(
        label="tomato_powdery_mildew",
        confidence=0.98,
        health_score=0.22,
        chemical_name="sulfur_fungicide",
        amount_ml=180.0,
        follow_up_alert="흰가루병 의심 개체를 국소 살포 대상으로 지정",
    ),
    "farm01_plant_15": DiseasePlan(
        label="tomato_gray_mold",
        confidence=0.95,
        health_score=0.18,
        chemical_name="botrytis_fungicide",
        amount_ml=220.0,
        follow_up_alert="잿빛곰팡이 의심 개체를 격리 관찰 대상으로 지정",
    ),
    "farm01_plant_22": DiseasePlan(
        label="tomato_blossom_end_rot",
        confidence=0.92,
        health_score=0.43,
        chemical_name="calcium_solution",
        amount_ml=160.0,
        follow_up_alert="칼슘 결핍 의심 개체를 보정 처치 대상으로 지정",
    ),
}

HARVEST_READY_PLANT_IDS = {
    "farm01_plant_01",
    "farm01_plant_02",
    "farm01_plant_03",
    "farm01_plant_04",
    "farm01_plant_11",
    "farm01_plant_12",
    "farm01_plant_19",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="현재 farm 맵 메타데이터에 맞춘 로컬 데모 더미데이터를 PostgreSQL에 적재합니다."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="DB에 쓰지 않고 어떤 데이터가 들어가는지만 출력합니다.",
    )
    return parser.parse_args()


def _reset_tables(db: Any) -> None:
    db.execute(
        text(
            """
            TRUNCATE TABLE
                crop_observations,
                harvest_events,
                alerts,
                environment_samples,
                actuation_logs,
                missons,
                plants,
                robots,
                zones
            RESTART IDENTITY CASCADE
            """
        )
    )


def _build_zone_bounds() -> dict[str, Any]:
    map_payload = read_map_payload("farm_map")
    operational_zones = read_zones_payload("farm_map")
    return {
        "type": "rectangle",
        "frame_id": "map",
        **map_payload["bounds"],
        "operational_slices": [
            {
                "zone_id": zone["id"],
                "name": zone["name"],
                "bounds": zone["bounds"],
                "representative_pose": zone["representative_pose"],
            }
            for zone in operational_zones
        ],
    }


def _build_robot_pose() -> dict[str, Any]:
    pose_payload = read_pose_payload("farm_map")
    pose = pose_payload.get("pose", {})
    return {
        "x": float(pose.get("x", 0.0)),
        "y": float(pose.get("y", 0.0)),
        "z": float(pose.get("z", 0.0)),
        "yaw": float(pose.get("yaw", 0.0)),
        "frame_id": str(pose.get("frame_id", "map")),
        "current_zone_id": str(pose_payload.get("current_zone_id", "farm_01_center")),
    }


def _sprinkler_id_for_x(x_value: float) -> str:
    if x_value <= -4.0:
        return "sprinkler_0"
    if x_value <= 0.0:
        return "sprinkler_1"
    if x_value <= 4.0:
        return "sprinkler_2"
    return "sprinkler_3"


def _plant_index_from_id(plant_id: str) -> int:
    return int(plant_id.rsplit("_", 1)[-1])


def _tomatoes_by_plant(crop_catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for tomato in crop_catalog.get("tomatoes", []):
        if not isinstance(tomato, dict):
            continue
        parent_plant_id = str(tomato.get("parent_plant_id", "")).strip()
        if parent_plant_id:
            lookup[parent_plant_id] = tomato
    return lookup


def _observation_payload(
    *,
    robot_row_id: int,
    plant_row_id: int,
    mission_row_id: int,
    observed_at: datetime,
    disease_plan: DiseasePlan | None,
) -> dict[str, Any]:
    if disease_plan is None:
        return {
            "robot_id": robot_row_id,
            "plant_id": plant_row_id,
            "misson_id": mission_row_id,
            "class_name": "healthy_leaf",
            "confidence": 0.96,
            "health_score": 0.94,
            "image_url": HEALTHY_IMAGE_URL,
            "observed_at": observed_at,
        }

    return {
        "robot_id": robot_row_id,
        "plant_id": plant_row_id,
        "misson_id": mission_row_id,
        "class_name": disease_plan.label,
        "confidence": disease_plan.confidence,
        "health_score": disease_plan.health_score,
        "image_url": DISEASE_IMAGE_URL,
        "observed_at": observed_at,
    }


def _build_alert_message(
    *,
    plant_id: str,
    operational_zone_id: str,
    sprinkler_id: str,
    disease_plan: DiseasePlan,
) -> str:
    return (
        f"{DEMO_TAG} plant={plant_id} zone={operational_zone_id} "
        f"sprinkler={sprinkler_id} chemical={disease_plan.chemical_name} "
        f"reason={disease_plan.follow_up_alert}"
    )


def _build_demo_dataset() -> dict[str, Any]:
    crop_catalog = _load_crop_instances()
    tomatoes_by_plant = _tomatoes_by_plant(crop_catalog)
    now = datetime.utcnow().replace(microsecond=0)

    zone_row = Zone(
        id=1,
        name=DEFAULT_ZONE_NAME,
        bounds=_build_zone_bounds(),
    )
    robot_row = Robot(
        id=1,
        name=ROBOT_NAME,
        status=ROBOT_STATUS,
        battery=82.0,
        current_pose=_build_robot_pose(),
        updated_at=now,
    )
    mission_row = Mission(
        id=1,
        robot_id=robot_row.id,
        mission_type=MISSION_TYPE,
        status=MISSION_STATUS,
        progress_percent=68,
        started_at=now - timedelta(minutes=18),
        completed_at=None,
    )

    plant_rows: list[Plant] = []
    observation_rows: list[CropObservation] = []
    alert_rows: list[Alert] = []
    actuation_rows: list[ActuationLog] = []
    harvest_rows: list[HarvestEvent] = []
    environment_rows: list[EnvironmentSample] = []
    scenario_rows: list[dict[str, Any]] = []

    observation_id = 1
    alert_id = 1
    actuation_id = 1
    harvest_id = 1
    environment_id = 1

    for index, sample in enumerate(range(6), start=1):
        recorded_at = now - timedelta(minutes=(6 - index) * 5)
        environment_rows.append(
            EnvironmentSample(
                id=environment_id,
                zone_id=zone_row.id,
                temperature=24.0 + (index * 0.4),
                humidity=58.0 + (index * 1.1),
                soil_moisture=31.0 + (index * 0.8),
                recorded_at=recorded_at,
            )
        )
        environment_id += 1

    for plant_row_id, plant in enumerate(crop_catalog.get("plants", []), start=1):
        if not isinstance(plant, dict):
            continue

        plant_id = str(plant.get("plant_id", "")).strip()
        pose = plant.get("pose", {})
        x_value = float(pose.get("x", 0.0))
        operational_zone_id = guess_zone_id_for_x(x_value)
        tomato = tomatoes_by_plant.get(plant_id, {})
        tomato_id = str(tomato.get("tomato_id", "")).strip()
        sprinkler_id = _sprinkler_id_for_x(x_value)
        disease_plan = DISEASE_CASES.get(plant_id)
        ready_harvest = plant_id in HARVEST_READY_PLANT_IDS
        observed_at = now - timedelta(minutes=max(1, 26 - plant_row_id))

        plant_rows.append(
            Plant(
                id=plant_row_id,
                zone_id=zone_row.id,
                position={
                    "x": x_value,
                    "y": y_value,
                    "z": float(pose.get("z", 0.75)),
                    "yaw": float(pose.get("yaw", 0.0)),
                    "operational_zone_id": operational_zone_id,
                    "nearest_sprinkler_id": sprinkler_id,
                    "linked_tomato_id": tomato_id,
                    "world_model_name": plant.get("world_model_name"),
                },
                health_score=0.94 if disease_plan is None else disease_plan.health_score,
                growth_stage="harvest_ready" if ready_harvest else "fruiting",
                name=plant_id,
                read_water=not ready_harvest,
                ready_harvest=ready_harvest,
                last_observed=observed_at,
            )
        )

        observation_rows.append(
            CropObservation(
                id=observation_id,
                **_observation_payload(
                    robot_row_id=robot_row.id,
                    plant_row_id=plant_row_id,
                    mission_row_id=mission_row.id,
                    observed_at=observed_at,
                    disease_plan=disease_plan,
                ),
            )
        )
        observation_id += 1

        if disease_plan is not None:
            alert_rows.append(
                Alert(
                    id=alert_id,
                    robot_id=robot_row.id,
                    alert_type="DISEASE",
                    message=_build_alert_message(
                        plant_id=plant_id,
                        operational_zone_id=operational_zone_id,
                        sprinkler_id=sprinkler_id,
                        disease_plan=disease_plan,
                    ),
                    image_url=DISEASE_IMAGE_URL,
                    detected_at=observed_at + timedelta(seconds=30),
                    is_acked=False,
                )
            )
            alert_id += 1

            actuation_rows.append(
                ActuationLog(
                    id=actuation_id,
                    robot_id=robot_row.id,
                    zone_id=zone_row.id,
                    action_type=f"{DEMO_TAG}:SPRAY:{sprinkler_id}:{disease_plan.chemical_name}",
                    amount_ml=disease_plan.amount_ml,
                    executed_at=observed_at + timedelta(minutes=3),
                    success=True,
                )
            )
            actuation_id += 1

        if ready_harvest and plant_id in {"farm01_plant_03", "farm01_plant_12", "farm01_plant_19"}:
            success = plant_id != "farm01_plant_19"
            harvest_rows.append(
                HarvestEvent(
                    id=harvest_id,
                    robot_id=robot_row.id,
                    plant_id=plant_row_id,
                    fruit_id=_plant_index_from_id(plant_id),
                    success=success,
                    fail_reason=None if success else f"{DEMO_TAG} fruit lost during gripper alignment",
                    basket_count=1 if success else 0,
                    harvested_at=observed_at + timedelta(minutes=5),
                )
            )
            harvest_id += 1

        if disease_plan is not None:
            scenario_rows.append(
                {
                    "plant_id": plant_id,
                    "linked_tomato_id": tomato_id,
                    "physical_zone_id": DEFAULT_ZONE_NAME,
                    "operational_zone_id": operational_zone_id,
                    "sprinkler_id": sprinkler_id,
                    "disease_label": disease_plan.label,
                    "chemical_name": disease_plan.chemical_name,
                }
            )

    return {
        "zone": zone_row,
        "robot": robot_row,
        "mission": mission_row,
        "plants": plant_rows,
        "environment_samples": environment_rows,
        "crop_observations": observation_rows,
        "alerts": alert_rows,
        "actuation_logs": actuation_rows,
        "harvest_events": harvest_rows,
        "scenario_rows": scenario_rows,
    }


def _print_summary(dataset: dict[str, Any], *, dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"[{mode}] agribot local demo seed")
    print(f"database_url={SQLALCHEMY_DATABASE_URL}")
    print(f"zone={dataset['zone'].name}")
    print(
        "counts="
        f"plants:{len(dataset['plants'])}, "
        f"environment:{len(dataset['environment_samples'])}, "
        f"observations:{len(dataset['crop_observations'])}, "
        f"alerts:{len(dataset['alerts'])}, "
        f"actuations:{len(dataset['actuation_logs'])}, "
        f"harvests:{len(dataset['harvest_events'])}"
    )
    for row in dataset["scenario_rows"]:
        print(
            "scenario="
            f"plant={row['plant_id']} "
            f"tomato={row['linked_tomato_id'] or 'n/a'} "
            f"physical_zone={row['physical_zone_id']} "
            f"operational_zone={row['operational_zone_id']} "
            f"sprinkler={row['sprinkler_id']} "
            f"disease={row['disease_label']} "
            f"chemical={row['chemical_name']}"
        )


def _apply_dataset(dataset: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        _reset_tables(db)
        db.add(dataset["zone"])
        db.add(dataset["robot"])
        db.add(dataset["mission"])
        db.add_all(dataset["plants"])
        db.add_all(dataset["environment_samples"])
        db.add_all(dataset["crop_observations"])
        db.add_all(dataset["alerts"])
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
    Base.metadata.create_all(bind=engine)
    dataset = _build_demo_dataset()
    _print_summary(dataset, dry_run=args.dry_run)
    if args.dry_run:
        return

    engine.connect().close()
    _apply_dataset(dataset)


if __name__ == "__main__":
    main()
