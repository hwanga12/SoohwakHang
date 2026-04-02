# 이 모듈은 상위 제어와 의사결정 패키지에서 manual actuation guard node 판단과 실행 보조 로직을 담당한다.
from __future__ import annotations

from agribot_interfaces.msg import IoTCommand
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from .manual_actuation_safety import (
    ActuationCommand,
    CommandSource,
    ManualPrioritySafetyLock,
)


def _parse_conflict_groups(raw_values: list[str]) -> dict[str, str]:
    # conflict groups를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    parsed: dict[str, str] = {}
    for raw_value in raw_values:
        items = [item.strip().lower() for item in raw_value.split(',') if item.strip()]
        if len(items) < 2:
            continue
        group_name = '+'.join(items)
        for item in items:
            parsed[item] = group_name
    return parsed


class ManualActuationGuardNode(Node):
    # ROS 2 실행 환경에서 manual actuation guard 흐름을 담당하는 노드 클래스를 정의한다.

    def __init__(self) -> None:
        # ManualActuationGuardNode 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__('manual_actuation_guard_node')
        self.declare_parameter('manual_command_topic', '/iot/commands/manual')
        self.declare_parameter('auto_command_topic', '/iot/commands/auto')
        self.declare_parameter('dispatch_topic', '/iot/commands/dispatch')
        self.declare_parameter('manual_override_seconds', 15.0)
        self.declare_parameter('duplicate_window_seconds', 2.0)
        self.declare_parameter('execution_lock_seconds', 4.0)
        self.declare_parameter('conflict_groups', ['watering,nutrient'])

        manual_command_topic = str(self.get_parameter('manual_command_topic').value)
        auto_command_topic = str(self.get_parameter('auto_command_topic').value)
        dispatch_topic = str(self.get_parameter('dispatch_topic').value)
        conflict_groups = _parse_conflict_groups(
            list(self.get_parameter('conflict_groups').value)
        )

        self._guard = ManualPrioritySafetyLock(
            manual_override_seconds=float(
                self.get_parameter('manual_override_seconds').value
            ),
            duplicate_window_seconds=float(
                self.get_parameter('duplicate_window_seconds').value
            ),
            execution_lock_seconds=float(
                self.get_parameter('execution_lock_seconds').value
            ),
            conflict_groups=conflict_groups,
        )

        self._dispatch_publisher = self.create_publisher(IoTCommand, dispatch_topic, 20)
        self._manual_subscription = self.create_subscription(
            IoTCommand,
            manual_command_topic,
            lambda msg: self._handle_command(msg, source=CommandSource.MANUAL.value),
            20,
        )
        self._auto_subscription = self.create_subscription(
            IoTCommand,
            auto_command_topic,
            lambda msg: self._handle_command(msg, source=CommandSource.AUTO.value),
            20,
        )

        self.get_logger().info(
            'Manual actuation guard ready. '
            f'manual_topic={manual_command_topic}, '
            f'auto_topic={auto_command_topic}, '
            f'dispatch_topic={dispatch_topic}'
        )

    def _handle_command(self, msg: IoTCommand, *, source: str) -> None:
        # handle 명령 정보를 계산해 반환한다.
        command = ActuationCommand(
            command_id=msg.command_id,
            zone_id=msg.zone_id,
            device_id=msg.device_id,
            device_type=msg.device_type,
            command_type=msg.command_type,
            target_value=float(msg.target_value),
            unit=msg.unit,
            requires_approval=bool(msg.requires_approval),
            auto_execute=bool(msg.auto_execute),
            requested_by=msg.requested_by,
            reason=msg.reason,
            source=source,
        )
        now_seconds = self.get_clock().now().nanoseconds / 1_000_000_000
        result = self._guard.evaluate(command, now_seconds=now_seconds)
        log_prefix = (
            f'Actuation guard {source} command '
            f'zone={command.zone_id}, device={command.device_type}, '
            f'command={command.command_type}, rule={result.rule}: '
        )
        if not result.accepted:
            self.get_logger().warning(f'{log_prefix}{result.reason}')
            return

        self._dispatch_publisher.publish(msg)
        self.get_logger().info(f'{log_prefix}{result.reason}')


def main(args=None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = ManualActuationGuardNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
