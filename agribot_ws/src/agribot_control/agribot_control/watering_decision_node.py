from __future__ import annotations

from dataclasses import dataclass

from agribot_interfaces.msg import EnvironmentData, PlantObservation
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from .environment_disease_rules import DiseaseSignal, EnvironmentSnapshot
from .watering_decision import (
    WateringDecision,
    WateringDecisionState,
    evaluate_watering_decision,
    format_watering_decision_log,
)


@dataclass(slots=True)
class ZoneObservationState:
    class_name: str
    repeat_count: int
    confidence: float
    health_score: float


class WateringDecisionNode(Node):
    """Evaluate watering execution mode with low-overhead environment callbacks."""

    def __init__(self) -> None:
        super().__init__('watering_decision_node')
        self.declare_parameter('environment_topic', '/environment_data')
        self.declare_parameter('plant_observation_topic', '/plant_observation')
        self.declare_parameter('zone_id_filter', '')
        self.declare_parameter('log_only_on_change', True)

        environment_topic = str(self.get_parameter('environment_topic').value)
        plant_observation_topic = str(self.get_parameter('plant_observation_topic').value)
        self._zone_id_filter = str(self.get_parameter('zone_id_filter').value).strip()
        self._log_only_on_change = bool(self.get_parameter('log_only_on_change').value)

        self._zone_observations: dict[str, ZoneObservationState] = {}
        self._last_decision_signature_by_zone: dict[str, tuple[str, str, float, str]] = {}

        self._environment_subscription = self.create_subscription(
            EnvironmentData,
            environment_topic,
            self._handle_environment,
            20,
        )
        self._plant_observation_subscription = self.create_subscription(
            PlantObservation,
            plant_observation_topic,
            self._handle_plant_observation,
            20,
        )

        self.get_logger().info(
            'Watering decision node ready. '
            f'environment_topic={environment_topic}, '
            f'plant_observation_topic={plant_observation_topic}, '
            f'zone_filter={self._zone_id_filter or "ALL"}'
        )

    def _handle_plant_observation(self, msg: PlantObservation) -> None:
        zone_id = msg.zone_id.strip()
        if not zone_id or not self._matches_zone(zone_id):
            return

        normalized_class_name = msg.class_name.strip().lower()
        if not normalized_class_name:
            return

        previous_state = self._zone_observations.get(zone_id)
        repeat_count = 1
        if previous_state is not None and previous_state.class_name == normalized_class_name:
            repeat_count = previous_state.repeat_count + 1

        self._zone_observations[zone_id] = ZoneObservationState(
            class_name=normalized_class_name,
            repeat_count=repeat_count,
            confidence=float(msg.confidence),
            health_score=float(msg.health_score),
        )

    def _handle_environment(self, msg: EnvironmentData) -> None:
        zone_id = msg.zone_id.strip()
        if not zone_id or not self._matches_zone(zone_id):
            return

        disease_signal = self._build_disease_signal(zone_id)
        decision = evaluate_watering_decision(
            EnvironmentSnapshot(
                zone_id=zone_id,
                temperature=float(msg.temperature),
                humidity=float(msg.humidity),
                soil_moisture=float(msg.soil_moisture),
                light_level=float(msg.light_level),
                co2_level=float(msg.co2_level),
            ),
            disease_signal,
        )

        signature = (
            decision.state,
            decision.source_rule,
            decision.target_value,
            decision.disease_context,
        )
        previous_signature = self._last_decision_signature_by_zone.get(zone_id)
        should_log = (
            not self._log_only_on_change
            or previous_signature != signature
        )
        self._last_decision_signature_by_zone[zone_id] = signature

        if not should_log:
            return

        log_message = format_watering_decision_log(decision)
        if decision.state == WateringDecisionState.HOLD.value:
            self.get_logger().warning(log_message)
        else:
            self.get_logger().info(log_message)

    def _build_disease_signal(self, zone_id: str) -> DiseaseSignal:
        observation_state = self._zone_observations.get(zone_id)
        if observation_state is None:
            return DiseaseSignal()
        return DiseaseSignal(
            class_name=observation_state.class_name,
            disease_name=observation_state.class_name,
            health_score=observation_state.health_score,
            repeat_count=observation_state.repeat_count,
            confidence=observation_state.confidence,
        )

    def _matches_zone(self, zone_id: str) -> bool:
        return not self._zone_id_filter or zone_id == self._zone_id_filter


def main(args=None) -> None:
    rclpy.init(args=args)
    node = WateringDecisionNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
