# 이 모듈은 IoT 장치 연동 패키지에서 mqtt bridge node 장치 흐름을 담당한다.
from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any
import uuid

from agribot_interfaces.msg import EnvironmentData, IoTCommand, IoTCommandResult, IoTDeviceState
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

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
    # ROS 2 실행 환경에서 mqtt 브리지 흐름을 담당하는 노드 클래스를 정의한다.

    def __init__(self) -> None:
        # MqttBridgeNode 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__('mqtt_bridge_node')
        self.declare_parameter('topics_file', str(get_default_mqtt_topics_path()))
        self.declare_parameter('force_log_only', False)

        topics_path = Path(str(self.get_parameter('topics_file').value)).expanduser()
        if not topics_path.is_absolute():
            topics_path = get_default_mqtt_topics_path().parent / topics_path
        self._config = load_mqtt_bridge_config(topics_path)
        self._force_log_only = bool(self.get_parameter('force_log_only').value)
        self._offline_queue_dir = Path(self._config.broker.offline_queue_dir).expanduser()
        self._offline_queue_dir.mkdir(parents=True, exist_ok=True)
        self._connected = False
        self._client = self._create_mqtt_client()
        self._mqtt_publish_enabled = self._client is not None
        self._mqtt_to_ros_publishers: dict[str, Any] = {}

        for route in self._config.ros_to_mqtt:
            self._create_ros_subscription(route)

        for route in self._config.mqtt_to_ros:
            publisher = self.create_publisher(IoTCommand, route.ros_topic, 20)
            self._mqtt_to_ros_publishers[route.mqtt_topic] = publisher

        self.get_logger().info(
            'MQTT bridge node ready. '
            f'topics_file={topics_path}, '
            f'broker={self._config.broker.host}:{self._config.broker.port}, '
            f'mode={"mqtt" if self._mqtt_publish_enabled else "log-only"}, '
            f'offline_queue_dir={self._offline_queue_dir}'
        )

    def _create_mqtt_client(self):
        # mqtt 클라이언트를 새로 만들어 다음 처리 단계로 넘긴다.
        if self._force_log_only:
            self.get_logger().warning('MQTT bridge running in forced log-only mode.')
            return None
        if mqtt is None:
            self.get_logger().warning('paho-mqtt is unavailable; MQTT bridge will log serialized payloads only.')
            return None

        try:
            callback_api = getattr(getattr(mqtt, 'CallbackAPIVersion', None), 'VERSION2', None)
            if callback_api is None:
                client = mqtt.Client(
                    client_id=self._config.broker.client_id,
                    clean_session=self._config.broker.clean_session,
                )
            else:
                client = mqtt.Client(
                    callback_api,
                    client_id=self._config.broker.client_id,
                    clean_session=self._config.broker.clean_session,
                )
            client.on_connect = self._handle_mqtt_connect
            client.on_disconnect = self._handle_mqtt_disconnect
            client.on_message = self._handle_mqtt_message
            client.reconnect_delay_set(
                min_delay=self._config.broker.reconnect_min_delay_sec,
                max_delay=self._config.broker.reconnect_max_delay_sec,
            )
            client.max_queued_messages_set(self._config.broker.offline_queue_max_messages)
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
        # ROS subscription를 새로 만들어 다음 처리 단계로 넘긴다.
        message_type_map = {
            'agribot_interfaces/msg/EnvironmentData': EnvironmentData,
            'agribot_interfaces/msg/IoTCommand': IoTCommand,
            'agribot_interfaces/msg/IoTCommandResult': IoTCommandResult,
            'agribot_interfaces/msg/IoTDeviceState': IoTDeviceState,
        }
        message_type = message_type_map[route.ros_type]
        self.create_subscription(
            message_type,
            route.ros_topic,
            lambda msg, active_route=route: self._forward_ros_message(active_route, msg),
            20,
        )

    def _forward_ros_message(self, route, message: Any) -> None:
        # forward ROS 메시지 정보를 계산해 반환한다.
        payload = serialize_message(route.serializer, message)
        topic = resolve_mqtt_topic(route.mqtt_topic_template, message)
        payload_json = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        published = self._publish_mqtt_message(
            topic=topic,
            payload_json=payload_json,
            retain=route.retain or self._config.broker.retain_default,
        )
        self.get_logger().info(
            'MQTT bridge forwarded ROS message: '
            f'ros_topic={route.ros_topic}, mqtt_topic={topic}, '
            f'published={published}, payload={payload_json}'
        )

    def _handle_mqtt_connect(
        self,
        client,
        _userdata,
        _flags,
        reason_code,
        *_extra,
    ) -> None:  # pragma: no cover - broker runtime path
        # Handle MQTT connection lifecycle updates.
        success_code = getattr(mqtt, 'MQTT_ERR_SUCCESS', 0) if mqtt is not None else 0
        reason_value = int(reason_code) if hasattr(reason_code, '__int__') else reason_code
        if reason_value != success_code:
            self._connected = False
            self.get_logger().warning(f'MQTT bridge connect failed: reason_code={reason_value}')
            return

        self._connected = True
        for route in self._config.mqtt_to_ros:
            client.subscribe(route.mqtt_topic, qos=self._config.broker.qos)
        self.get_logger().info('MQTT bridge connected. Flushing offline queue.')
        self._flush_offline_queue()

    def _handle_mqtt_disconnect(self, _client, _userdata, reason_code, *_extra) -> None:  # pragma: no cover - broker runtime path
        # Handle MQTT disconnect lifecycle updates.
        self._connected = False
        self.get_logger().warning(f'MQTT bridge disconnected: reason_code={reason_code}')

    def _handle_mqtt_message(self, _client, _userdata, message) -> None:  # pragma: no cover - broker runtime path
        # handle MQTT 메시지 정보를 계산해 반환한다.
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

    def _publish_mqtt_message(
        self,
        *,
        topic: str,
        payload_json: str,
        retain: bool,
        queue_on_failure: bool = True,
    ) -> bool:
        # Publish a message to MQTT with retry and offline-queue fallback.
        if self._client is None or not self._connected:
            if queue_on_failure:
                self._enqueue_offline_message(topic=topic, payload_json=payload_json, retain=retain)
            return False

        publish_retry_count = self._config.broker.publish_retry_count
        publish_retry_backoff_sec = self._config.broker.publish_retry_backoff_sec
        mqtt_success_code = getattr(mqtt, 'MQTT_ERR_SUCCESS', 0) if mqtt is not None else 0

        for attempt in range(publish_retry_count + 1):
            try:
                publish_info = self._client.publish(
                    topic,
                    payload_json,
                    qos=self._config.broker.qos,
                    retain=retain,
                )
                if getattr(publish_info, 'rc', mqtt_success_code) == mqtt_success_code:
                    wait_for_publish = getattr(publish_info, 'wait_for_publish', None)
                    if callable(wait_for_publish):
                        wait_for_publish(timeout=1.5)
                    return True
            except Exception as exc:  # pragma: no cover - depends on local broker
                self.get_logger().warning(
                    f'MQTT publish attempt failed for {topic}: {exc} '
                    f'(attempt {attempt + 1}/{publish_retry_count + 1})'
                )
            if attempt < publish_retry_count and publish_retry_backoff_sec > 0.0:
                time.sleep(publish_retry_backoff_sec)

        if queue_on_failure:
            self._enqueue_offline_message(topic=topic, payload_json=payload_json, retain=retain)
        return False

    def _enqueue_offline_message(self, *, topic: str, payload_json: str, retain: bool) -> None:
        # Persist an outbound MQTT message for later replay.
        record = {
            'topic': topic,
            'payload_json': payload_json,
            'retain': bool(retain),
        }
        target_path = self._offline_queue_dir / (
            f'{int(time.time() * 1000):013d}_{uuid.uuid4().hex}.json'
        )
        target_path.write_text(
            json.dumps(record, ensure_ascii=True, sort_keys=True),
            encoding='utf-8',
        )
        self._prune_offline_queue()
        self.get_logger().warning(f'Queued MQTT message offline: {topic}')

    def _prune_offline_queue(self) -> None:
        # Keep the offline queue bounded to the configured maximum size.
        queue_files = sorted(self._offline_queue_dir.glob('*.json'))
        overflow = len(queue_files) - self._config.broker.offline_queue_max_messages
        for path in queue_files[:max(0, overflow)]:
            path.unlink(missing_ok=True)

    def _flush_offline_queue(self) -> None:
        # Replay queued MQTT messages after a successful reconnect.
        for path in sorted(self._offline_queue_dir.glob('*.json')):
            try:
                record = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError) as exc:
                self.get_logger().warning(f'Removing invalid offline MQTT record {path.name}: {exc}')
                path.unlink(missing_ok=True)
                continue

            if not self._publish_mqtt_message(
                topic=str(record.get('topic', '')),
                payload_json=str(record.get('payload_json', '')),
                retain=bool(record.get('retain', False)),
                queue_on_failure=False,
            ):
                self.get_logger().warning(
                    f'Stopped offline MQTT flush at {path.name}; broker still unavailable.'
                )
                return
            path.unlink(missing_ok=True)

    def destroy_node(self) -> bool:
        # destroy 노드 정보를 계산해 반환한다.
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
        return super().destroy_node()


def main(args=None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
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
