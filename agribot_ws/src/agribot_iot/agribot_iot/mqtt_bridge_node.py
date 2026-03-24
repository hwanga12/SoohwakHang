from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agribot_interfaces.msg import EnvironmentData, IoTCommand, IoTDeviceState
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from .mqtt_contract import (
    deserialize_iot_command_payload,
    get_default_mqtt_topics_path,
    load_mqtt_bridge_config,
    resolve_mqtt_topic,
    serialize_message,
)

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - optional runtime dependency
    mqtt = None


class MqttBridgeNode(Node):
    """Bridge selected ROS topics to MQTT with a log-only fallback."""

    def __init__(self) -> None:
        super().__init__('mqtt_bridge_node')
        self.declare_parameter('topics_file', str(get_default_mqtt_topics_path()))
        self.declare_parameter('force_log_only', False)

        topics_path = Path(str(self.get_parameter('topics_file').value)).expanduser()
        if not topics_path.is_absolute():
            topics_path = get_default_mqtt_topics_path().parent / topics_path
        self._config = load_mqtt_bridge_config(topics_path)
        self._force_log_only = bool(self.get_parameter('force_log_only').value)
        self._client = self._create_mqtt_client()
        self._mqtt_publish_enabled = self._client is not None
        self._mqtt_to_ros_publishers: dict[str, Any] = {}

        for route in self._config.ros_to_mqtt:
            self._create_ros_subscription(route)

        for route in self._config.mqtt_to_ros:
            publisher = self.create_publisher(IoTCommand, route.ros_topic, 20)
            self._mqtt_to_ros_publishers[route.mqtt_topic] = publisher
            if self._client is not None:
                self._client.subscribe(route.mqtt_topic, qos=self._config.broker.qos)

        self.get_logger().info(
            'MQTT bridge node ready. '
            f'topics_file={topics_path}, '
            f'broker={self._config.broker.host}:{self._config.broker.port}, '
            f'mode={"mqtt" if self._mqtt_publish_enabled else "log-only"}'
        )

    def _create_mqtt_client(self):
        if self._force_log_only:
            self.get_logger().warning('MQTT bridge running in forced log-only mode.')
            return None
        if mqtt is None:
            self.get_logger().warning('paho-mqtt is unavailable; MQTT bridge will log serialized payloads only.')
            return None

        try:
            callback_api = getattr(getattr(mqtt, 'CallbackAPIVersion', None), 'VERSION2', None)
            if callback_api is None:
                client = mqtt.Client(client_id=self._config.broker.client_id)
            else:
                client = mqtt.Client(callback_api, client_id=self._config.broker.client_id)
            client.on_message = self._handle_mqtt_message
            client.connect(
                self._config.broker.host,
                self._config.broker.port,
                keepalive=self._config.broker.keepalive_sec,
            )
            client.loop_start()
            return client
        except Exception as exc:  # pragma: no cover - depends on local broker
            self.get_logger().warning(f'Failed to connect to MQTT broker; falling back to log-only mode: {exc}')
            return None

    def _create_ros_subscription(self, route) -> None:
        message_type_map = {
            'agribot_interfaces/msg/EnvironmentData': EnvironmentData,
            'agribot_interfaces/msg/IoTCommand': IoTCommand,
            'agribot_interfaces/msg/IoTDeviceState': IoTDeviceState,
            'std_msgs/msg/String': String,
        }
        message_type = message_type_map[route.ros_type]
        self.create_subscription(
            message_type,
            route.ros_topic,
            lambda msg, active_route=route: self._forward_ros_message(active_route, msg),
            20,
        )

    def _forward_ros_message(self, route, message: Any) -> None:
        payload = serialize_message(route.serializer, message)
        topic = resolve_mqtt_topic(route.mqtt_topic_template, message)
        payload_json = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        if self._client is not None:
            self._client.publish(
                topic,
                payload_json,
                qos=self._config.broker.qos,
                retain=route.retain or self._config.broker.retain_default,
            )
        self.get_logger().info(
            'MQTT bridge forwarded ROS message: '
            f'ros_topic={route.ros_topic}, mqtt_topic={topic}, payload={payload_json}'
        )

    def _handle_mqtt_message(self, _client, _userdata, message) -> None:  # pragma: no cover - broker runtime path
        publisher = self._mqtt_to_ros_publishers.get(message.topic)
        if publisher is None:
            return
        try:
            ros_message = deserialize_iot_command_payload(message.payload)
        except Exception as exc:
            self.get_logger().warning(f'Ignoring invalid MQTT command payload on {message.topic}: {exc}')
            return
        publisher.publish(ros_message)
        self.get_logger().info(f'MQTT bridge published inbound command to ROS topic from {message.topic}.')

    def destroy_node(self) -> bool:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MqttBridgeNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
