from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from database import Base


def _uuid_column(*, primary_key: bool = False, nullable: bool = False):
    return Column(UUID(as_uuid=True), primary_key=primary_key, default=uuid.uuid4, nullable=nullable)


class Zone(Base):
    __tablename__ = "zones"

    id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    bounds = Column(JSONB, nullable=False, default=dict)
    description = Column(String(255), nullable=True)

    robots = relationship("Robot", back_populates="current_zone")
    plants = relationship("Plant", back_populates="zone")
    environment_samples = relationship("EnvironmentSample", back_populates="zone")
    devices = relationship("IotDevice", back_populates="zone")
    missions = relationship("Mission", back_populates="target_zone")
    alerts = relationship("Alert", back_populates="zone")
    actuation_commands = relationship("ActuationCommand", back_populates="zone")


class Robot(Base):
    __tablename__ = "robots"

    id = _uuid_column(primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    status = Column(String(50), nullable=False, default="IDLE")
    battery_level = Column(Float, nullable=True)
    current_zone_id = Column(String(50), ForeignKey("zones.id"), nullable=True)
    current_pose = Column(JSONB, nullable=True)
    updated_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    current_zone = relationship("Zone", back_populates="robots")
    missions = relationship("Mission", back_populates="robot")
    observations = relationship("CropObservation", back_populates="robot")
    alerts = relationship("Alert", back_populates="robot")
    harvest_events = relationship("HarvestEvent", back_populates="robot")


class Plant(Base):
    __tablename__ = "plants"

    id = Column(String(50), primary_key=True, index=True)
    zone_id = Column(String(50), ForeignKey("zones.id"), nullable=False)
    crop_name = Column(String(50), nullable=False, default="tomato")
    position = Column(JSONB, nullable=False, default=dict)
    needs_water = Column(Boolean, nullable=False, default=False)
    ready_to_harvest = Column(Boolean, nullable=False, default=False)
    needs_nutrition = Column(Boolean, nullable=False, default=False)
    last_observed_at = Column(TIMESTAMP, nullable=True)

    zone = relationship("Zone", back_populates="plants")
    fruits = relationship("Fruit", back_populates="plant")
    observations = relationship("CropObservation", back_populates="plant")
    alerts = relationship("Alert", back_populates="plant")
    missions = relationship("Mission", back_populates="target_plant")
    harvest_events = relationship("HarvestEvent", back_populates="plant")


class Fruit(Base):
    __tablename__ = "fruits"

    id = Column(String(50), primary_key=True, index=True)
    plant_id = Column(String(50), ForeignKey("plants.id"), nullable=False)
    position = Column(JSONB, nullable=False, default=dict)
    ripeness_stage = Column(String(30), nullable=False, default="UNRIPE")
    ready_to_harvest = Column(Boolean, nullable=False, default=False)
    current_status = Column(String(30), nullable=False, default="VISIBLE")
    last_observed_at = Column(TIMESTAMP, nullable=True)

    plant = relationship("Plant", back_populates="fruits")
    observations = relationship("CropObservation", back_populates="fruit")
    missions = relationship("Mission", back_populates="target_fruit")
    harvest_events = relationship("HarvestEvent", back_populates="fruit")


class Mission(Base):
    __tablename__ = "missions"

    id = _uuid_column(primary_key=True)
    robot_id = Column(UUID(as_uuid=True), ForeignKey("robots.id"), nullable=False)
    mission_type = Column(String(50), nullable=False)
    target_zone_id = Column(String(50), ForeignKey("zones.id"), nullable=True)
    target_plant_id = Column(String(50), ForeignKey("plants.id"), nullable=True)
    target_fruit_id = Column(String(50), ForeignKey("fruits.id"), nullable=True)
    status = Column(String(50), nullable=False, default="PENDING")
    progress_percent = Column(Integer, nullable=True)
    started_at = Column(TIMESTAMP, nullable=True)
    completed_at = Column(TIMESTAMP, nullable=True)

    robot = relationship("Robot", back_populates="missions")
    target_zone = relationship("Zone", back_populates="missions")
    target_plant = relationship("Plant", back_populates="missions")
    target_fruit = relationship("Fruit", back_populates="missions")
    observations = relationship("CropObservation", back_populates="mission")
    actuation_commands = relationship("ActuationCommand", back_populates="mission")
    harvest_events = relationship("HarvestEvent", back_populates="mission")


class CropObservation(Base):
    __tablename__ = "crop_observations"

    id = _uuid_column(primary_key=True)
    robot_id = Column(UUID(as_uuid=True), ForeignKey("robots.id"), nullable=True)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True)
    plant_id = Column(String(50), ForeignKey("plants.id"), nullable=False)
    fruit_id = Column(String(50), ForeignKey("fruits.id"), nullable=True)
    finding_label = Column(String(100), nullable=False)
    confidence = Column(Float, nullable=False, default=0.0)
    recommended_action = Column(String(255), nullable=True)
    evidence = Column(Text, nullable=True)
    image_url = Column(String(255), nullable=True)
    observed_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    robot = relationship("Robot", back_populates="observations")
    mission = relationship("Mission", back_populates="observations")
    plant = relationship("Plant", back_populates="observations")
    fruit = relationship("Fruit", back_populates="observations")
    alerts = relationship("Alert", back_populates="observation")
    actuation_commands = relationship("ActuationCommand", back_populates="observation")


class EnvironmentSample(Base):
    __tablename__ = "environment_samples"

    id = _uuid_column(primary_key=True)
    zone_id = Column(String(50), ForeignKey("zones.id"), nullable=False)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    soil_moisture = Column(Float, nullable=True)
    recorded_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    zone = relationship("Zone", back_populates="environment_samples")


class IotDevice(Base):
    __tablename__ = "iot_devices"

    id = Column(String(50), primary_key=True, index=True)
    zone_id = Column(String(50), ForeignKey("zones.id"), nullable=False)
    device_type = Column(String(30), nullable=False)
    display_name = Column(String(100), nullable=False)
    control_mode = Column(String(30), nullable=False, default="AUTO")
    current_state = Column(String(30), nullable=False, default="OFF")
    current_value = Column(Float, nullable=True)
    value_unit = Column(String(20), nullable=True)
    is_online = Column(Boolean, nullable=False, default=True)
    last_seen_at = Column(TIMESTAMP, nullable=True)

    zone = relationship("Zone", back_populates="devices")
    actuation_commands = relationship("ActuationCommand", back_populates="device")
    actuation_logs = relationship("ActuationLog", back_populates="device")


class ActuationCommand(Base):
    __tablename__ = "actuation_commands"

    id = _uuid_column(primary_key=True)
    device_id = Column(String(50), ForeignKey("iot_devices.id"), nullable=False)
    zone_id = Column(String(50), ForeignKey("zones.id"), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True)
    observation_id = Column(UUID(as_uuid=True), ForeignKey("crop_observations.id"), nullable=True)
    command_type = Column(String(30), nullable=False)
    command_status = Column(String(30), nullable=False, default="REQUESTED")
    target_value = Column(Float, nullable=True)
    value_unit = Column(String(20), nullable=True)
    requested_by = Column(String(100), nullable=True)
    request_source = Column(String(50), nullable=True)
    requested_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    device = relationship("IotDevice", back_populates="actuation_commands")
    zone = relationship("Zone", back_populates="actuation_commands")
    mission = relationship("Mission", back_populates="actuation_commands")
    observation = relationship("CropObservation", back_populates="actuation_commands")
    logs = relationship("ActuationLog", back_populates="command")


class ActuationLog(Base):
    __tablename__ = "actuation_logs"

    id = _uuid_column(primary_key=True)
    command_id = Column(UUID(as_uuid=True), ForeignKey("actuation_commands.id"), nullable=False)
    device_id = Column(String(50), ForeignKey("iot_devices.id"), nullable=False)
    result = Column(String(20), nullable=False)
    result_message = Column(Text, nullable=True)
    state_after = Column(String(30), nullable=True)
    actual_value = Column(Float, nullable=True)
    value_unit = Column(String(20), nullable=True)
    started_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    finished_at = Column(TIMESTAMP, nullable=True)

    command = relationship("ActuationCommand", back_populates="logs")
    device = relationship("IotDevice", back_populates="actuation_logs")


class Alert(Base):
    __tablename__ = "alerts"

    id = _uuid_column(primary_key=True)
    robot_id = Column(UUID(as_uuid=True), ForeignKey("robots.id"), nullable=True)
    zone_id = Column(String(50), ForeignKey("zones.id"), nullable=True)
    plant_id = Column(String(50), ForeignKey("plants.id"), nullable=True)
    observation_id = Column(UUID(as_uuid=True), ForeignKey("crop_observations.id"), nullable=True)
    alert_type = Column(String(30), nullable=False)
    severity = Column(String(20), nullable=False, default="INFO")
    message = Column(Text, nullable=False)
    image_url = Column(String(255), nullable=True)
    acknowledged_at = Column(TIMESTAMP, nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    detected_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    robot = relationship("Robot", back_populates="alerts")
    zone = relationship("Zone", back_populates="alerts")
    plant = relationship("Plant", back_populates="alerts")
    observation = relationship("CropObservation", back_populates="alerts")


class AiJudgment(Base):
    __tablename__ = "ai_judgments"

    id = _uuid_column(primary_key=True)
    plant_id = Column(String(50), ForeignKey("plants.id"), nullable=True, index=True)
    fruit_id = Column(String(50), ForeignKey("fruits.id"), nullable=True, index=True)
    zone_id = Column(String(50), ForeignKey("zones.id"), nullable=True, index=True)
    judgment_type = Column(String(30), nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=False)
    raw_label = Column(String(100), nullable=False)
    canonical_code = Column(String(100), nullable=False, index=True)
    confidence = Column(Float, nullable=False, default=0.0)
    risk_level = Column(String(20), nullable=True)
    recommended_action_code = Column(String(50), nullable=False, default="NONE")
    requires_approval = Column(Boolean, nullable=False, default=False)
    payload_json = Column(JSONB, nullable=False, default=dict)
    image_url = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow, index=True)

    plant = relationship("Plant")
    fruit = relationship("Fruit")
    zone = relationship("Zone")


class HarvestEvent(Base):
    __tablename__ = "harvest_events"

    id = _uuid_column(primary_key=True)
    plant_id = Column(String(50), ForeignKey("plants.id"), nullable=False)
    fruit_id = Column(String(50), ForeignKey("fruits.id"), nullable=True)
    robot_id = Column(UUID(as_uuid=True), ForeignKey("robots.id"), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    fail_reason = Column(Text, nullable=True)
    basket_count = Column(Integer, nullable=True)
    harvested_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    plant = relationship("Plant", back_populates="harvest_events")
    fruit = relationship("Fruit", back_populates="harvest_events")
    robot = relationship("Robot", back_populates="harvest_events")
    mission = relationship("Mission", back_populates="harvest_events")
