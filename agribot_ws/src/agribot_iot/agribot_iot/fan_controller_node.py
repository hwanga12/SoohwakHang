# 이 모듈은 IoT 장치 연동 패키지에서 fan controller node 장치 흐름을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from agribot_interfaces.msg import IoTCommand, IoTCommandResult, IoTDeviceState
from rclpy.callback_groups import ReentrantCallbackGroup
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from .command_result_contract import command_result_message_from_payload
from .device_mapping import IoTDeviceSpec, get_default_iot_devices_path, load_iot_device_catalog
from .fan_controller_logic import (
    FanExecutionPlan,
    build_fan_result_payload,
    build_fan_state,
    classify_fan_state,
    plan_fan_command,
)


@dataclass(slots=True)
class ActiveFanCommand:
    # active 환기팬 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    plan: FanExecutionPlan
    started_at_monotonic: float


@dataclass(slots=True)
class FanRuntimeState:
    # 환기팬 런타임 데이터 상태를 일관된 형태로 보관하기 위한 클래스를 정의한다.
    speed_level: int
    state: str
    detail_message: str
    last_run_duration_sec: float
    active_command: ActiveFanCommand | None = None


class FanControllerNode(Node):
    # ROS 2 실행 환경에서 환기팬 controller 흐름을 담당하는 노드 클래스를 정의한다.

    def __init__(self) -> None:
        # FanControllerNode 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__('fan_controller_node')
        callback_group = ReentrantCallbackGroup()

        self.declare_parameter('iot_devices_file', str(get_default_iot_devices_path()))
        self.declare_parameter('command_topic', '/iot/commands/dispatch')
        self.declare_parameter('device_state_topic', '/iot/device_state')
        self.declare_parameter('command_result_topic', '/iot/command_result')
        self.declare_parameter('zone_id_filter', '')
        self.declare_parameter('state_publish_hz', 1.0)

        catalog_path = Path(str(self.get_parameter('iot_devices_file').value)).expanduser()
        if not catalog_path.is_absolute():
            catalog_path = get_default_iot_devices_path().parent / catalog_path
        self._catalog = load_iot_device_catalog(catalog_path)
        self._command_topic = str(self.get_parameter('command_topic').value)
        self._device_state_topic = str(self.get_parameter('device_state_topic').value)
        self._command_result_topic = str(self.get_parameter('command_result_topic').value)
        self._zone_id_filter = str(self.get_parameter('zone_id_filter').value).strip()
        self._state_publish_hz = max(0.2, float(self.get_parameter('state_publish_hz').value))

        self._fan_devices = {
            device.device_id: device
            for device in self._catalog.devices.values()
            if device.device_type == 'fan'
            and (not self._zone_id_filter or device.zone_id == self._zone_id_filter)
        }
        self._runtime_states = {
            device.device_id: FanRuntimeState(
                speed_level=0,
                state='OFF',
                detail_message='Fan controller idle.',
                last_run_duration_sec=0.0,
            )
            for device in self._fan_devices.values()
        }
        self._last_logged_state_signatures: dict[str, tuple[str, int, str]] = {}

        self._device_state_publisher = self.create_publisher(IoTDeviceState, self._device_state_topic, 20)
        self._command_result_publisher = self.create_publisher(
            IoTCommandResult,
            self._command_result_topic,
            20,
        )
        self._command_subscription = self.create_subscription(
            IoTCommand,
            self._command_topic,
            self._handle_command,
            20,
            callback_group=callback_group,
        )
        self._publish_timer = self.create_timer(1.0 / self._state_publish_hz, self._publish_all_states)

        self._publish_all_states()
        self.get_logger().info(
            'Fan controller node ready. '
            f'iot_devices_file={catalog_path}, '
            f'command_topic={self._command_topic}, '
            f'device_state_topic={self._device_state_topic}, '
            f'command_result_topic={self._command_result_topic}, '
            f'device_count={len(self._fan_devices)}'
        )

    def _handle_command(self, message: IoTCommand) -> None:
        # handle 명령 정보를 계산해 반환한다.
        if message.device_type.strip().lower() != 'fan':
            return

        device = self._resolve_device(message)
        if device is None:
            self.get_logger().warning(
                f'Ignoring fan command for unknown zone/device: zone={message.zone_id}, device={message.device_id}'
            )
            return

        runtime = self._runtime_states[device.device_id]
        plan = plan_fan_command(message, device, current_speed_level=runtime.speed_level)
        if not plan.accepted:
            self._publish_result(
                plan,
                success=False,
                state='REJECTED',
                detail_message=plan.detail_message,
                executed_duration_sec=self._current_run_duration(runtime),
                speed_level=runtime.speed_level,
            )
            self.get_logger().warning(f'Fan command rejected: {plan.detail_message}')
            return

        if plan.target_speed_level == runtime.speed_level:
            runtime.detail_message = plan.detail_message
            self._publish_state(device, runtime)
            self._publish_result(
                plan,
                success=True,
                state='RUNNING' if runtime.speed_level > 0 else 'STOPPED',
                detail_message=runtime.detail_message,
                executed_duration_sec=self._current_run_duration(runtime),
                speed_level=runtime.speed_level,
            )
            return

        previous_duration_sec = self._interrupt_active_command(
            device,
            runtime,
            reason=(
                'Stopped by explicit fan off command.'
                if plan.target_speed_level == 0
                else 'Superseded by a newer fan command.'
            ),
        )

        runtime.speed_level = plan.target_speed_level
        runtime.state = classify_fan_state(plan.target_speed_level)
        runtime.detail_message = plan.detail_message

        executed_duration_sec = previous_duration_sec if plan.target_speed_level == 0 else 0.0
        if plan.target_speed_level > 0:
            runtime.active_command = ActiveFanCommand(
                plan=plan,
                started_at_monotonic=time.monotonic(),
            )
            runtime.last_run_duration_sec = 0.0
        else:
            runtime.active_command = None
            runtime.last_run_duration_sec = previous_duration_sec
            if previous_duration_sec > 0.0:
                runtime.detail_message = (
                    f'Fan stopped after {previous_duration_sec:.1f}s of runtime.'
                )

        self._publish_state(device, runtime)
        self._publish_result(
            plan,
            success=True,
            state='RUNNING' if plan.target_speed_level > 0 else 'STOPPED',
            detail_message=runtime.detail_message,
            executed_duration_sec=executed_duration_sec,
            speed_level=runtime.speed_level,
        )

    def _resolve_device(self, message: IoTCommand) -> IoTDeviceSpec | None:
        # 현재 입력 조건을 바탕으로 장치를 계산하거나 결정한다.
        if message.device_id:
            return self._fan_devices.get(message.device_id)

        zone_id = message.zone_id.strip() or self._catalog.default_zone_id
        try:
            device = self._catalog.primary_device(zone_id, 'fan')
        except KeyError:
            return None
        return self._fan_devices.get(device.device_id)

    def _interrupt_active_command(
        self,
        device: IoTDeviceSpec,
        runtime: FanRuntimeState,
        *,
        reason: str,
    ) -> float:
        # interrupt active 명령 정보를 계산해 반환한다.
        active_command = runtime.active_command
        if active_command is None:
            return runtime.last_run_duration_sec

        executed_duration_sec = max(0.0, time.monotonic() - active_command.started_at_monotonic)
        runtime.active_command = None
        runtime.last_run_duration_sec = executed_duration_sec
        self._publish_result(
            active_command.plan,
            success=False,
            state='INTERRUPTED',
            detail_message=reason,
            executed_duration_sec=executed_duration_sec,
            speed_level=runtime.speed_level,
        )
        runtime.detail_message = reason
        self._publish_state(device, runtime)
        return executed_duration_sec

    def _publish_all_states(self) -> None:
        # ALL 상태 묶음를 외부 시스템이나 다음 처리 단계로 전달한다.
        for device_id, device in self._fan_devices.items():
            self._publish_state(device, self._runtime_states[device_id])

    def _publish_state(self, device: IoTDeviceSpec, runtime: FanRuntimeState) -> None:
        # 상태를 외부 시스템이나 다음 처리 단계로 전달한다.
        run_duration_sec = self._current_run_duration(runtime)
        message = build_fan_state(
            device,
            state=runtime.state,
            speed_level=runtime.speed_level,
            run_duration_sec=run_duration_sec,
            detail_message=runtime.detail_message,
        )
        message.header.stamp = self.get_clock().now().to_msg()
        self._device_state_publisher.publish(message)
        signature = (
            message.state,
            int(message.speed_level),
            message.detail_message,
        )
        if self._last_logged_state_signatures.get(device.device_id) != signature:
            self._last_logged_state_signatures[device.device_id] = signature
            self.get_logger().info(
                'Fan state updated: '
                f'device={device.device_id}, '
                f'state={message.state}, '
                f'speed_level={int(message.speed_level)}, '
                f'run_duration={message.current_value:.1f}s, '
                f'detail={message.detail_message}'
            )

    def _publish_result(
        self,
        plan: FanExecutionPlan,
        *,
        success: bool,
        state: str,
        detail_message: str,
        executed_duration_sec: float,
        speed_level: int,
    ) -> None:
        # 결과를 외부 시스템이나 다음 처리 단계로 전달한다.
        result = command_result_message_from_payload(
            build_fan_result_payload(
                plan,
                success=success,
                state=state,
                detail_message=detail_message,
                executed_duration_sec=executed_duration_sec,
                speed_level=speed_level,
            ),
            stamp=self.get_clock().now().to_msg(),
        )
        self._command_result_publisher.publish(result)
        self.get_logger().info(
            f'Fan result published: command_id={plan.command_id}, state={state}, success={success}'
        )

    def _current_run_duration(self, runtime: FanRuntimeState) -> float:
        # 현재 run duration 정보를 계산해 반환한다.
        active_command = runtime.active_command
        if active_command is None:
            return runtime.last_run_duration_sec
        return max(0.0, time.monotonic() - active_command.started_at_monotonic)


def main(args=None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = FanControllerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
