from __future__ import annotations

import uuid

from agribot_interfaces.msg import EnvironmentData, IoTCommand, PlantObservation
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from .actuation_request_planner import (
    ActuationRequestPlan,
    RequestRoute,
    plan_actuation_requests,
    request_signature,
)
from .environment_disease_rules import DiseaseSignal, EnvironmentSnapshot


class ActuationRequestNode(Node):
    """Publish actionable IoT requests from environment and observation inputs."""

    def __init__(self) -> None:
        super().__init__('actuation_request_node')
        self.declare_parameter('environment_topic', '/environment_data')
        self.declare_parameter('plant_observation_topic', '/plant_observation')
        self.declare_parameter('zone_id_filter', '')
        self.declare_parameter('log_only_on_change', True)
        self.declare_parameter('auto_command_topic', '/iot/commands/auto')
        self.declare_parameter('review_command_topic', '/iot/commands/review')
        self.declare_parameter('requested_by', 'mission_manager:auto')

        environment_topic = str(self.get_parameter('environment_topic').value)
        plant_observation_topic = str(self.get_parameter('plant_observation_topic').value)
        self._zone_id_filter = str(self.get_parameter('zone_id_filter').value).strip()
        self._log_only_on_change = bool(self.get_parameter('log_only_on_change').value)
        auto_command_topic = str(self.get_parameter('auto_command_topic').value)
        review_command_topic = str(self.get_parameter('review_command_topic').value)
        self._requested_by = str(self.get_parameter('requested_by').value).strip()

        self._zone_observations: dict[str, tuple[str, int, float, float, str]] = {}
        self._last_signature_by_zone_device: dict[str, tuple[str, ...]] = {}

        self._auto_command_publisher = self.create_publisher(
            IoTCommand,
            auto_command_topic,
            20,
        )
        self._review_command_publisher = self.create_publisher(
            IoTCommand,
            review_command_topic,
            20,
        )

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
            'Actuation request node ready. '
            f'environment_topic={environment_topic}, '
            f'plant_observation_topic={plant_observation_topic}, '
            f'auto_topic={auto_command_topic}, '
            f'review_topic={review_command_topic}, '
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
        if previous_state is not None and previous_state[0] == normalized_class_name:
            repeat_count = previous_state[1] + 1

        self._zone_observations[zone_id] = (
            normalized_class_name,
            repeat_count,
            float(msg.confidence),
            float(msg.health_score),
            msg.growth_stage.strip(),
        )

    def _handle_environment(self, msg: EnvironmentData) -> None:
        zone_id = msg.zone_id.strip()
        if not zone_id or not self._matches_zone(zone_id):
            return

        requests = plan_actuation_requests(
            EnvironmentSnapshot(
                zone_id=zone_id,
                temperature=float(msg.temperature),
                humidity=float(msg.humidity),
                soil_moisture=float(msg.soil_moisture),
                light_level=float(msg.light_level),
                co2_level=float(msg.co2_level),
            ),
            self._build_disease_signal(zone_id),
            requested_by=self._requested_by or 'mission_manager:auto',
        )
        active_keys = set()
        for request_plan in requests:
            device_key = f'{request_plan.zone_id}:{request_plan.device_type}'
            active_keys.add(device_key)
            signature = request_signature(request_plan)
            previous_signature = self._last_signature_by_zone_device.get(device_key)
            should_publish = (
                not self._log_only_on_change
                or previous_signature != signature
            )
            self._last_signature_by_zone_device[device_key] = signature
            if not should_publish:
                continue
            self._publish_request(request_plan)

        stale_keys = [
            key for key in self._last_signature_by_zone_device
            if key.startswith(f'{zone_id}:') and key not in active_keys
        ]
        for key in stale_keys:
            self._last_signature_by_zone_device.pop(key, None)

    def _publish_request(self, plan: ActuationRequestPlan) -> None:
        message = IoTCommand()
        message.header.stamp = self.get_clock().now().to_msg()
        message.command_id = str(uuid.uuid4())
        message.zone_id = plan.zone_id
        message.device_id = plan.device_id
        message.device_type = plan.device_type
        message.command_type = plan.command_type
        message.target_value = float(plan.target_value)
        message.unit = plan.unit
        message.requires_approval = bool(plan.requires_approval)
        message.auto_execute = bool(plan.auto_execute)
        message.requested_by = plan.requested_by
        message.reason = plan.reason

        if plan.route == RequestRoute.AUTO.value:
            self._auto_command_publisher.publish(message)
            route_label = 'auto'
        else:
            self._review_command_publisher.publish(message)
            route_label = 'review'

        self.get_logger().info(
            'Actuation request published: '
            f'route={route_label}, '
            f'zone={plan.zone_id}, '
            f'device={plan.device_type}, '
            f'command={plan.command_type}, '
            f'target={plan.target_value:.1f}{plan.unit}, '
            f'rule={plan.source_rule}, '
            f'requires_approval={plan.requires_approval}'
        )

    def _build_disease_signal(self, zone_id: str) -> DiseaseSignal:
        observation_state = self._zone_observations.get(zone_id)
        if observation_state is None:
            return DiseaseSignal()
        return DiseaseSignal(
            class_name=observation_state[0],
            disease_name=observation_state[0],
            repeat_count=observation_state[1],
            confidence=observation_state[2],
            health_score=observation_state[3],
            growth_stage=observation_state[4],
        )

    def _matches_zone(self, zone_id: str) -> bool:
        return not self._zone_id_filter or zone_id == self._zone_id_filter


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ActuationRequestNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
