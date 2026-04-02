# Optional direct ROS transport for backend command and status traffic.
from __future__ import annotations

import logging
import os
from threading import Lock, Thread
from typing import Any

try:  # pragma: no cover - depends on local ROS workspace availability
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node

    from agribot_bringup.runtime_message_contract import (
        mission_bridge_status_payload_from_message,
        mission_request_message_from_payload,
        robot_command_message_from_payload,
        robot_command_status_payload_from_message,
        robot_control_state_payload_from_message,
    )
    from agribot_bringup.protocol_qos import protocol_qos_profile
    from agribot_interfaces.msg import (
        EnvironmentData,
        IoTCommand,
        IoTCommandResult,
        IoTDeviceState,
        MissionBridgeStatus,
        MissionRequest,
        MissionStatus,
        RobotCommand,
        RobotCommandStatus,
        RobotControlState,
        RobotStatus,
    )
    from agribot_iot.command_result_contract import command_result_payload_from_message
except Exception as exc:  # pragma: no cover - optional runtime dependency
    rclpy = None
    Context = None
    MultiThreadedExecutor = None
    Node = object
    mission_bridge_status_payload_from_message = None
    mission_request_message_from_payload = None
    robot_command_message_from_payload = None
    robot_command_status_payload_from_message = None
    robot_control_state_payload_from_message = None
    protocol_qos_profile = None
    EnvironmentData = None
    IoTCommand = None
    IoTCommandResult = None
    IoTDeviceState = None
    MissionBridgeStatus = None
    MissionRequest = None
    MissionStatus = None
    RobotCommand = None
    RobotCommandStatus = None
    RobotControlState = None
    RobotStatus = None
    command_result_payload_from_message = None
    _IMPORT_ERROR = exc
else:  # pragma: no cover - import path only
    _IMPORT_ERROR = None


logger = logging.getLogger(__name__)
DEFAULT_ENABLED = os.environ.get('AGRIBOT_BACKEND_USE_ROS_BRIDGE', '1').strip().lower() not in {
    '',
    '0',
    'false',
    'no',
    'off',
}


def _iso_from_builtin_time(stamp) -> str:
    # Convert builtin_interfaces/Time-like objects into an ISO-ish sortable string.
    seconds = int(getattr(stamp, 'sec', 0) or 0)
    nanoseconds = int(getattr(stamp, 'nanosec', 0) or 0)
    return f'{seconds}.{nanoseconds:09d}'


def _copy_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    # Return a shallow copy so callers cannot mutate internal cache state.
    return dict(payload) if isinstance(payload, dict) else None


def _topic_qos(topic_name: str, *, default_depth: int) -> Any:
    # Resolve QoS from the shared policy file when available.
    if protocol_qos_profile is None:
        return default_depth
    return protocol_qos_profile(topic_name, default_depth=default_depth)


class _BackendRosProtocolNode(Node):  # pragma: no cover - runtime integration path
    # Direct ROS bridge node that lives inside the backend process.

    def __init__(self, bridge: 'RosProtocolBridge', *, context: Context) -> None:
        super().__init__('backend_ros_protocol_bridge', context=context)
        self._bridge = bridge
        robot_command_topic = os.environ.get('AGRIBOT_ROBOT_COMMAND_TOPIC', '/robot/commands/manual')
        mission_request_topic = os.environ.get('AGRIBOT_MISSION_REQUEST_TOPIC', '/mission/requests')
        manual_iot_topic = os.environ.get('AGRIBOT_IOT_MANUAL_COMMAND_TOPIC', '/iot/commands/manual')
        automatic_iot_topic = os.environ.get('AGRIBOT_IOT_AUTOMATIC_COMMAND_TOPIC', '/iot/commands/auto')
        dispatch_iot_topic = os.environ.get('AGRIBOT_IOT_DISPATCH_COMMAND_TOPIC', '/iot/commands/dispatch')
        robot_command_status_topic = os.environ.get(
            'AGRIBOT_ROBOT_COMMAND_STATUS_TOPIC',
            '/robot/commands/status',
        )
        robot_control_state_topic = os.environ.get(
            'AGRIBOT_ROBOT_CONTROL_STATE_TYPED_TOPIC',
            '/robot/control_state/typed',
        )
        mission_bridge_status_topic = os.environ.get(
            'AGRIBOT_MISSION_BRIDGE_STATUS_TOPIC',
            '/mission/bridge_status',
        )
        environment_topic = os.environ.get('AGRIBOT_ENVIRONMENT_TOPIC', '/environment_data')
        iot_device_state_topic = os.environ.get('AGRIBOT_IOT_DEVICE_STATE_TOPIC', '/iot/device_state')
        iot_command_result_topic = os.environ.get(
            'AGRIBOT_IOT_COMMAND_RESULT_TOPIC',
            '/iot/command_result',
        )
        robot_status_topic = os.environ.get('AGRIBOT_ROBOT_STATUS_TOPIC', '/robot/status')
        mission_status_topic = os.environ.get('AGRIBOT_MISSION_STATUS_TOPIC', '/mission/status')

        self._robot_command_publisher = self.create_publisher(
            RobotCommand,
            robot_command_topic,
            _topic_qos(robot_command_topic, default_depth=20),
        )
        self._mission_request_publisher = self.create_publisher(
            MissionRequest,
            mission_request_topic,
            _topic_qos(mission_request_topic, default_depth=20),
        )
        self._iot_publishers = {
            topic: self.create_publisher(
                IoTCommand,
                topic,
                _topic_qos(topic, default_depth=20),
            )
            for topic in {
                manual_iot_topic,
                automatic_iot_topic,
                dispatch_iot_topic,
            }
        }

        self.create_subscription(
            RobotCommandStatus,
            robot_command_status_topic,
            self._handle_robot_command_status,
            _topic_qos(robot_command_status_topic, default_depth=20),
        )
        self.create_subscription(
            RobotControlState,
            robot_control_state_topic,
            self._handle_robot_control_state,
            _topic_qos(robot_control_state_topic, default_depth=20),
        )
        self.create_subscription(
            MissionBridgeStatus,
            mission_bridge_status_topic,
            self._handle_mission_bridge_status,
            _topic_qos(mission_bridge_status_topic, default_depth=20),
        )
        self.create_subscription(
            EnvironmentData,
            environment_topic,
            self._handle_environment_data,
            _topic_qos(environment_topic, default_depth=20),
        )
        self.create_subscription(
            IoTDeviceState,
            iot_device_state_topic,
            self._handle_iot_device_state,
            _topic_qos(iot_device_state_topic, default_depth=20),
        )
        self.create_subscription(
            IoTCommandResult,
            iot_command_result_topic,
            self._handle_iot_command_result,
            _topic_qos(iot_command_result_topic, default_depth=20),
        )
        self.create_subscription(
            RobotStatus,
            robot_status_topic,
            self._handle_robot_status,
            _topic_qos(robot_status_topic, default_depth=20),
        )
        self.create_subscription(
            MissionStatus,
            mission_status_topic,
            self._handle_mission_status,
            _topic_qos(mission_status_topic, default_depth=20),
        )

    def publish_robot_command(self, payload: dict[str, Any]) -> bool:
        # Publish a robot command onto the direct ROS transport.
        if self._robot_command_publisher.get_subscription_count() <= 0:
            return False
        message = robot_command_message_from_payload(
            payload,
            stamp=self.get_clock().now().to_msg(),
        )
        self._robot_command_publisher.publish(message)
        return True

    def publish_mission_request(self, payload: dict[str, Any]) -> bool:
        # Publish a mission request onto the direct ROS transport.
        if self._mission_request_publisher.get_subscription_count() <= 0:
            return False
        message = mission_request_message_from_payload(
            payload,
            stamp=self.get_clock().now().to_msg(),
        )
        self._mission_request_publisher.publish(message)
        return True

    def publish_iot_command(self, payload: dict[str, Any], *, topic: str) -> bool:
        # Publish an IoT command onto the direct ROS transport.
        publisher = self._iot_publishers.get(topic)
        if publisher is None:
            publisher = self.create_publisher(
                IoTCommand,
                topic,
                _topic_qos(topic, default_depth=20),
            )
            self._iot_publishers[topic] = publisher
        if publisher.get_subscription_count() <= 0:
            return False

        message = IoTCommand()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = str(payload.get('frame_id', 'map'))
        message.command_id = str(payload.get('command_id', ''))
        message.zone_id = str(payload.get('zone_id', ''))
        message.device_id = str(payload.get('device_id', ''))
        message.device_type = str(payload.get('device_type', ''))
        message.command_type = str(payload.get('command_type', ''))
        message.target_value = float(payload.get('target_value', 0.0) or 0.0)
        message.unit = str(payload.get('unit', ''))
        message.requires_approval = bool(payload.get('requires_approval', False))
        message.auto_execute = bool(payload.get('auto_execute', True))
        message.requested_by = str(payload.get('requested_by', ''))
        message.reason = str(payload.get('reason', ''))
        publisher.publish(message)
        return True

    def _handle_robot_command_status(self, message: RobotCommandStatus) -> None:
        self._bridge._update_robot_command_status(
            robot_command_status_payload_from_message(message)
        )

    def _handle_robot_control_state(self, message: RobotControlState) -> None:
        self._bridge._update_control_state(
            robot_control_state_payload_from_message(message)
        )

    def _handle_mission_bridge_status(self, message: MissionBridgeStatus) -> None:
        self._bridge._update_mission_bridge_status(
            mission_bridge_status_payload_from_message(message)
        )

    def _handle_environment_data(self, message: EnvironmentData) -> None:
        self._bridge._update_environment_data(
            {
                'source': 'ros_topic',
                'zone_id': str(message.zone_id),
                'temperature': float(message.temperature),
                'humidity': float(message.humidity),
                'soil_moisture': float(message.soil_moisture),
                'light_level': float(message.light_level),
                'co2_level': float(message.co2_level),
            }
        )

    def _handle_iot_device_state(self, message: IoTDeviceState) -> None:
        self._bridge._update_iot_device_state(
            {
                'source': 'ros_topic',
                'updated_at': _iso_from_builtin_time(message.header.stamp),
                'frame_id': str(message.header.frame_id),
                'device_id': str(message.device_id),
                'zone_id': str(message.zone_id),
                'device_type': str(message.device_type),
                'state': str(message.state),
                'opening_ratio': float(message.opening_ratio),
                'speed_level': float(message.speed_level),
                'current_value': float(message.current_value),
                'unit': str(message.unit),
                'is_available': bool(message.is_available),
                'detail_message': str(message.detail_message),
            }
        )

    def _handle_iot_command_result(self, message: IoTCommandResult) -> None:
        self._bridge._update_iot_command_result(
            {
                'source': 'ros_topic',
                'updated_at': _iso_from_builtin_time(message.header.stamp),
                **command_result_payload_from_message(message),
            }
        )

    def _handle_robot_status(self, message: RobotStatus) -> None:
        self._bridge._update_robot_status(
            {
                'source': 'ros_topic',
                'updated_at': _iso_from_builtin_time(message.header.stamp),
                'frame_id': str(message.header.frame_id),
                'robot_id': str(message.robot_id),
                'zone_id': str(message.zone_id),
                'mission_id': str(message.mission_id),
                'mode': str(message.mode),
                'state': str(message.state),
                'is_returning_home': bool(message.is_returning_home),
                'has_error': bool(message.has_error),
                'error_code': str(message.error_code),
                'error_message': str(message.error_message),
            }
        )

    def _handle_mission_status(self, message: MissionStatus) -> None:
        self._bridge._update_live_mission_status(
            {
                'source': 'ros_topic',
                'updated_at': _iso_from_builtin_time(message.header.stamp),
                'mission_id': str(message.mission_id),
                'mission_type': str(message.mission_type),
                'state': str(message.state),
                'current_phase': str(message.current_phase),
                'zone_id': str(message.zone_id),
                'target_id': str(message.target_id),
                'progress_pct': float(message.progress_pct),
                'retry_count': int(message.retry_count),
                'detail_message': str(message.detail_message),
            }
        )


class RosProtocolBridge:
    # Process-local singleton bridge that enables backend direct ROS transport.

    def __init__(self) -> None:
        self._lock = Lock()
        self._enabled = DEFAULT_ENABLED
        self._started = False
        self._start_error: str | None = None
        self._context: Context | None = None
        self._executor: MultiThreadedExecutor | None = None
        self._node: _BackendRosProtocolNode | None = None
        self._thread: Thread | None = None
        self._latest_robot_command_status: dict[str, Any] | None = None
        self._latest_control_state: dict[str, Any] | None = None
        self._latest_mission_bridge_status: dict[str, Any] | None = None
        self._mission_bridge_status_by_id: dict[str, dict[str, Any]] = {}
        self._latest_environment_data: dict[str, Any] | None = None
        self._latest_iot_device_state_by_id: dict[str, dict[str, Any]] = {}
        self._latest_iot_command_result: dict[str, Any] | None = None
        self._latest_robot_status: dict[str, Any] | None = None
        self._latest_live_mission_status: dict[str, Any] | None = None

    @property
    def enabled(self) -> bool:
        # Return whether the bridge is configured to attempt startup.
        return self._enabled

    def start(self) -> bool:
        # Start the background ROS bridge thread when ROS is available.
        with self._lock:
            if not self._enabled:
                self._start_error = 'bridge_disabled'
                return False
            if self._started:
                return True
            if rclpy is None:
                self._start_error = f'ros_import_unavailable: {_IMPORT_ERROR}'
                logger.info('Backend ROS bridge unavailable: %s', self._start_error)
                return False

            try:
                self._context = Context()
                rclpy.init(args=None, context=self._context)
                self._node = _BackendRosProtocolNode(self, context=self._context)
                self._executor = MultiThreadedExecutor(context=self._context, num_threads=2)
                self._executor.add_node(self._node)
                self._thread = Thread(
                    target=self._executor.spin,
                    name='backend-ros-protocol-bridge',
                    daemon=True,
                )
                self._thread.start()
                self._started = True
                self._start_error = None
                logger.info('Backend ROS bridge started.')
                return True
            except Exception as exc:  # pragma: no cover - depends on local runtime
                self._start_error = str(exc)
                logger.warning('Failed to start backend ROS bridge: %s', exc)
                self._started = False
                self._executor = None
                self._node = None
                self._thread = None
                if self._context is not None:
                    try:
                        rclpy.shutdown(context=self._context)
                    except Exception:
                        pass
                self._context = None
                return False

    def stop(self) -> None:
        # Stop the background ROS bridge thread.
        with self._lock:
            executor = self._executor
            node = self._node
            context = self._context
            thread = self._thread
            self._executor = None
            self._node = None
            self._context = None
            self._thread = None
            self._started = False

        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        if context is not None and rclpy is not None:
            try:
                rclpy.shutdown(context=context)
            except Exception:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def is_ready(self) -> bool:
        # Return whether the direct ROS transport is active.
        with self._lock:
            return self._started and self._node is not None

    def publish_robot_command(self, payload: dict[str, Any]) -> bool:
        # Publish a direct robot command if the bridge is active.
        node = self._node
        if not self.is_ready() or node is None:
            return False
        return bool(node.publish_robot_command(payload))

    def publish_mission_request(self, payload: dict[str, Any]) -> bool:
        # Publish a direct mission request if the bridge is active.
        node = self._node
        if not self.is_ready() or node is None:
            return False
        return bool(node.publish_mission_request(payload))

    def publish_iot_command(self, payload: dict[str, Any], *, topic: str) -> bool:
        # Publish a direct IoT command if the bridge is active.
        node = self._node
        if not self.is_ready() or node is None:
            return False
        return bool(node.publish_iot_command(payload, topic=topic))

    def get_latest_robot_command_status(self) -> dict[str, Any] | None:
        # Return the latest typed robot command status payload, if any.
        with self._lock:
            return _copy_payload(self._latest_robot_command_status)

    def get_latest_control_state(self) -> dict[str, Any] | None:
        # Return the latest typed robot control state payload, if any.
        with self._lock:
            return _copy_payload(self._latest_control_state)

    def get_latest_mission_bridge_status(self) -> dict[str, Any] | None:
        # Return the latest typed mission bridge status payload, if any.
        with self._lock:
            return _copy_payload(self._latest_mission_bridge_status)

    def get_mission_bridge_status(self, mission_id: str) -> dict[str, Any] | None:
        # Return a cached mission bridge status for a specific mission id.
        with self._lock:
            return _copy_payload(
                self._mission_bridge_status_by_id.get(str(mission_id).strip())
            )

    def get_latest_environment_data(self) -> dict[str, Any] | None:
        # Return the latest environment payload published on the ROS graph.
        with self._lock:
            return _copy_payload(self._latest_environment_data)

    def get_live_snapshot(self) -> dict[str, Any]:
        # Return a compact snapshot for realtime websocket clients.
        with self._lock:
            return {
                'transport': {
                    'enabled': self._enabled,
                    'ready': self._started,
                    'error': self._start_error,
                },
                'robot_command_status': _copy_payload(self._latest_robot_command_status),
                'control_state': _copy_payload(self._latest_control_state),
                'mission_bridge_status': _copy_payload(self._latest_mission_bridge_status),
                'robot_status': _copy_payload(self._latest_robot_status),
                'mission_status': _copy_payload(self._latest_live_mission_status),
                'environment': _copy_payload(self._latest_environment_data),
                'iot_command_result': _copy_payload(self._latest_iot_command_result),
            }

    def _update_robot_command_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            payload['source'] = 'ros_topic'
            self._latest_robot_command_status = payload

    def _update_control_state(self, payload: dict[str, Any]) -> None:
        with self._lock:
            payload['source'] = 'ros_topic'
            self._latest_control_state = payload

    def _update_mission_bridge_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            payload['source'] = 'ros_topic'
            self._latest_mission_bridge_status = payload
            mission_id = str(payload.get('mission_id') or payload.get('command_id') or '').strip()
            if mission_id:
                self._mission_bridge_status_by_id[mission_id] = dict(payload)

    def _update_environment_data(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._latest_environment_data = dict(payload)

    def _update_iot_device_state(self, payload: dict[str, Any]) -> None:
        with self._lock:
            device_id = str(payload.get('device_id') or '').strip()
            if device_id:
                self._latest_iot_device_state_by_id[device_id] = dict(payload)

    def _update_iot_command_result(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._latest_iot_command_result = dict(payload)

    def _update_robot_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._latest_robot_status = dict(payload)

    def _update_live_mission_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._latest_live_mission_status = dict(payload)


_ROS_PROTOCOL_BRIDGE: RosProtocolBridge | None = None


def get_ros_protocol_bridge() -> RosProtocolBridge:
    # Return the process-local ROS bridge singleton.
    global _ROS_PROTOCOL_BRIDGE
    if _ROS_PROTOCOL_BRIDGE is None:
        _ROS_PROTOCOL_BRIDGE = RosProtocolBridge()
    return _ROS_PROTOCOL_BRIDGE
