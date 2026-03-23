from sqlalchemy import Column, Integer, String, Float, TIMESTAMP, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from database import Base
from datetime import datetime

class Robot(Base):
    __tablename__ = "robots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    status = Column(String(50), nullable=False, default="IDLE", comment="IDLE")
    battery = Column(Float, nullable=True)
    current_pose = Column(JSONB, nullable=True)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    crop_observations = relationship("CropObservation", back_populates="robot")
    harvest_events = relationship("HarvestEvent", back_populates="robot")
    alerts = relationship("Alert", back_populates="robot")
    missions = relationship("Mission", back_populates="robot")
    actuation_logs = relationship("ActuationLog", back_populates="robot")


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True, comment="e.g.")
    name = Column(String(100), nullable=False)
    bounds = Column(JSONB, nullable=True, comment="구역")

    # Relationships
    environment_samples = relationship("EnvironmentSample", back_populates="zone")
    plants = relationship("Plant", back_populates="zone")
    actuation_logs = relationship("ActuationLog", back_populates="zone")


class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True, index=True, comment="e.g.")
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    position = Column(JSONB, nullable=True, comment="x")
    health_score = Column(Float, nullable=True, comment="0.0")
    growth_stage = Column(String(50), nullable=True)
    name = Column(String(50), nullable=True)
    read_water = Column(Boolean, nullable=True)
    ready_harvest = Column(Boolean, nullable=True)
    last_observed = Column(TIMESTAMP, nullable=True)

    # Relationships
    zone = relationship("Zone", back_populates="plants")
    crop_observations = relationship("CropObservation", back_populates="plant")
    harvest_events = relationship("HarvestEvent", back_populates="plant")


class Mission(Base):
    __tablename__ = "missons"

    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(Integer, ForeignKey("robots.id"), nullable=False)
    mission_type = Column(String(50), nullable=False, comment="PATROL")
    status = Column(String(50), nullable=False, comment="RUNNING")
    progress_percent = Column(Integer, nullable=True)
    started_at = Column(TIMESTAMP, nullable=True)
    completed_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    robot = relationship("Robot", back_populates="missions")
    crop_observations = relationship("CropObservation", back_populates="mission")


class CropObservation(Base):
    __tablename__ = "crop_observations"

    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(Integer, ForeignKey("robots.id"), nullable=False, comment="어떤")
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    misson_id = Column(Integer, ForeignKey("missons.id"), nullable=True)
    class_name = Column(String(50), nullable=False, comment="healthy_leaf")
    confidence = Column(Float, nullable=True)
    health_score = Column(Float, nullable=True)
    image_url = Column(String(255), nullable=True)
    observed_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    robot = relationship("Robot", back_populates="crop_observations")
    plant = relationship("Plant", back_populates="crop_observations")
    mission = relationship("Mission", back_populates="crop_observations")


class HarvestEvent(Base):
    __tablename__ = "harvest_events"

    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(Integer, ForeignKey("robots.id"), nullable=False, comment="어떤")
    plant_id = Column(Integer, ForeignKey("plants.id"), nullable=False)
    fruit_id = Column(Integer, nullable=True, comment="토마토")
    success = Column(Boolean, nullable=True)
    fail_reason = Column(Text, nullable=True)
    basket_count = Column(Integer, nullable=True, comment="적재된")
    harvested_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    robot = relationship("Robot", back_populates="harvest_events")
    plant = relationship("Plant", back_populates="harvest_events")


class EnvironmentSample(Base):
    __tablename__ = "environment_samples"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    soil_moisture = Column(Float, nullable=True)
    recorded_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Relationships
    zone = relationship("Zone", back_populates="environment_samples")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(Integer, ForeignKey("robots.id"), nullable=False)
    alert_type = Column(String(50), nullable=False, comment="DISEASE")
    message = Column(Text, nullable=True)
    image_url = Column(String(255), nullable=True)
    detected_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    is_acked = Column(Boolean, nullable=True, comment="프론트엔드")

    # Relationships
    robot = relationship("Robot", back_populates="alerts")


class ActuationLog(Base):
    __tablename__ = "actuation_logs"

    id = Column(Integer, primary_key=True, index=True)
    robot_id = Column(Integer, ForeignKey("robots.id"), nullable=False, comment="어떤")
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    action_type = Column(String(50), nullable=False, comment="WATERING")
    amount_ml = Column(Float, nullable=True)
    executed_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    success = Column(Boolean, nullable=True)

    # Relationships
    robot = relationship("Robot", back_populates="actuation_logs")
    zone = relationship("Zone", back_populates="actuation_logs")
