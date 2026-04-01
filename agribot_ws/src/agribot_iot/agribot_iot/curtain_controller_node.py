# 이 모듈은 IoT 장치 연동 패키지에서 curtain controller node 장치 흐름을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

from agribot_interfaces.msg import IoTCommand, IoTDeviceState
from rclpy.callback_groups import ReentrantCallbackGroup
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from .curtain_controller_logic import (
    CurtainExecutionPlan,
    build_curtain_result_payload,
    build_curtain_state,
    classify_curtain_state,
    plan_curtain_command,
)
from .device_mapping import IoTDeviceSpec, get_default_iot_devices_path, load_iot_device_catalog


@dataclass(slots=True)
class ActiveCurtainCommand:
    # active 커튼 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    plan: CurtainExecutionPlan
    started_at_monotonic: float
    last_update_monotonic: float


@dataclass(slots=True)
class CurtainRuntimeState:
    # 커튼 런타임 데이터 상태를 일관된 형태로 보관하기 위한 클래스를 정의한다.
    opening_ratio: float
    target_opening_ratio: float
    state: str
    detail_message: str
    active_command: ActiveCurtainCommand | None = None


class CurtainControllerNode(Node):
    # ROS 2 실행 환경에서 커튼 controller 흐름을 담당하는 노드 클래스를 정의한다.

    def __init__(self) -> None:
        # CurtainControllerNode 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__('curtain_controller_node')
        callback_group = ReentrantCallbackGroup()

        self.declare_parameter('iot_devices_file', str(get_default_iot_devices_path()))
        self.declare_parameter('command_topic', '/iot/commands/dispatch')
        self.declare_parameter('device_state_topic', '/iot/device_state')
        self.declare_parameter('command_result_topic', '/iot/command_result')
        self.declare_parameter('zone_id_filter', '')
        self.declare_parameter('initial_opening_ratio', 100.0)
        self.declare_parameter('state_publish_hz', 1.0)
        self.declare_parameter('transition_rate_percent_per_sec', 40.0)

        catalog_path = Path(str(self.get_parameter('iot_devices_file').value)).expanduser()
        if not catalog_path.is_absolute():
            catalog_path = get_default_iot_devices_path().parent / catalog_path
        self._catalog = load_iot_device_catalog(catalog_path)
        self._command_topic = str(self.get_parameter('command_topic').value)
        self._device_state_topic = str(self.get_parameter('device_state_topic').value)
        self._command_result_topic = str(self.get_parameter('command_result_topic').value)
        self._zone_id_filter = str(self.get_parameter('zone_id_filter').value).strip()
        self._initial_opening_ratio = _clamp_percent(float(self.get_parameter('initial_opening_ratio').value))
        self._state_publish_hz = max(0.2, float(self.get_parameter('state_publish_hz').value))
        self._transition_rate_percent_per_sec = max(
            0.1,
            float(self.get_parameter('transition_rate_percent_per_sec').value),
        )

        self._curtain_devices = {
            device.device_id: device
            for device in self._catalog.devices.values()
            if device.device_type == 'curtain'
            and (not self._zone_id_filter or device.zone_id == self._zone_id_filter)
        }
        self._runtime_states = {
            device.device_id: CurtainRuntimeState(
                opening_ratio=self._initial_opening_ratio,
                target_opening_ratio=self._initial_opening_ratio,
                state=classify_curtain_state(self._initial_opening_ratio),
                detail_message='Curtain controller idle.',
            )
            for device in self._curtain_devices.values()
        }
        self._last_logged_state_signatures: dict[str, tuple[str, float, str]] = {}

        self._device_state_publisher = self.create_publisher(
            IoTDeviceState,
            self._device_state_topic,
            20,
        )
        self._command_result_publisher = self.create_publisher(
            String,
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
        self._transition_timer = self.create_timer(0.1, self._advance_transitions)

        self._publish_all_states()
        self.get_logger().info(
            'Curtain controller node ready. '
            f'iot_devices_file={catalog_path}, '
            f'command_topic={self._command_topic}, '
            f'device_state_topic={self._device_state_topic}, '
            f'command_result_topic={self._command_result_topic}, '
            f'device_count={len(self._curtain_devices)}'
        )

    def _handle_command(self, message: IoTCommand) -> None:
        # handle 명령 정보를 계산해 반환한다.
        if message.device_type.strip().lower() != 'curtain':
            return

        device = self._resolve_device(message)
        if device is None:
            self.get_logger().warning(
                f'Ignoring curtain command for unknown zone/device: zone={message.zone_id}, device={message.device_id}'
            )
            return

        runtime = self._runtime_states[device.device_id]
        plan = plan_curtain_command(
            message,
            device,
            current_opening_ratio=runtime.opening_ratio,
            transition_rate_percent_per_sec=self._transition_rate_percent_per_sec,
        )
        if not plan.accepted:
            self._publish_result(
                plan,
                success=False,
                state='REJECTED',
                detail_message=plan.detail_message,
                executed_duration_sec=0.0,
                opening_ratio=runtime.opening_ratio,
            )
            self.get_logger().warning(f'Curtain command rejected: {plan.detail_message}')
            return

        if plan.immediate_completion:
            self._interrupt_active_command(
                device,
                runtime,
                reason='Superseded by an immediate curtain command.',
            )
            runtime.opening_ratio = plan.target_opening_ratio
            runtime.target_opening_ratio = plan.target_opening_ratio
            runtime.state = classify_curtain_state(plan.target_opening_ratio)
            runtime.detail_message = plan.detail_message
            runtime.active_command = None
            self._publish_state(device, runtime)
            self._publish_result(
                plan,
                success=True,
                state=runtime.state,
                detail_message=plan.detail_message,
                executed_duration_sec=0.0,
                opening_ratio=runtime.opening_ratio,
            )
            return

        self._interrupt_active_command(
            device,
            runtime,
            reason='Superseded by a newer curtain command.',
        )
        runtime.target_opening_ratio = plan.target_opening_ratio
        runtime.state = classify_curtain_state(
            runtime.opening_ratio,
            target_opening_ratio=plan.target_opening_ratio,
        )
        runtime.detail_message = plan.detail_message
        runtime.active_command = ActiveCurtainCommand(
            plan=plan,
            started_at_monotonic=time.monotonic(),
            last_update_monotonic=time.monotonic(),
        )
        self._publish_state(device, runtime)
        self.get_logger().info(
            'Curtain motion started: '
            f'device={device.device_id}, '
            f'current={plan.source_opening_ratio:.1f}%, '
            f'target={plan.target_opening_ratio:.1f}%, '
            f'duration={plan.duration_sec:.2f}s'
        )

    def _resolve_device(self, message: IoTCommand) -> IoTDeviceSpec | None:
        # 현재 입력 조건을 바탕으로 장치를 계산하거나 결정한다.
        if message.device_id:
            return self._curtain_devices.get(message.device_id)

        zone_id = message.zone_id.strip() or self._catalog.default_zone_id
        try:
            device = self._catalog.primary_device(zone_id, 'curtain')
        except KeyError:
            return None
        return self._curtain_devices.get(device.device_id)

    def _interrupt_active_command(
        self,
        device: IoTDeviceSpec,
        runtime: CurtainRuntimeState,
        *,
        reason: str,
    ) -> None:
        # interrupt active 명령 정보를 계산해 반환한다.
        active_command = runtime.active_command
        if active_command is None:
            return
        runtime.active_command = None
        runtime.target_opening_ratio = runtime.opening_ratio
        runtime.state = classify_curtain_state(runtime.opening_ratio)
        runtime.detail_message = reason
        self._publish_result(
            active_command.plan,
            success=False,
            state='INTERRUPTED',
            detail_message=reason,
            executed_duration_sec=time.monotonic() - active_command.started_at_monotonic,
            opening_ratio=runtime.opening_ratio,
        )
        self._publish_state(device, runtime)

    def _advance_transitions(self) -> None:
        # advance transitions 정보를 계산해 반환한다.
        now = time.monotonic()
        for device_id, runtime in self._runtime_states.items():
            active_command = runtime.active_command
            if active_command is None:
                continue

            elapsed = max(0.0, now - active_command.last_update_monotonic)
            if elapsed <= 0.0:
                continue
            step = self._transition_rate_percent_per_sec * elapsed
            target = active_command.plan.target_opening_ratio
            direction = 1.0 if target > runtime.opening_ratio else -1.0
            next_opening_ratio = runtime.opening_ratio + (direction * step)

            if direction > 0.0:
                runtime.opening_ratio = min(target, next_opening_ratio)
            else:
                runtime.opening_ratio = max(target, next_opening_ratio)
            active_command.last_update_monotonic = now

            if abs(runtime.opening_ratio - target) < 1e-3:
                runtime.opening_ratio = target
                runtime.target_opening_ratio = target
                runtime.state = classify_curtain_state(runtime.opening_ratio)
                runtime.detail_message = 'Curtain movement completed successfully.'
                runtime.active_command = None
                self._publish_state(self._curtain_devices[device_id], runtime)
                self._publish_result(
                    active_command.plan,
                    success=True,
                    state=runtime.state,
                    detail_message=runtime.detail_message,
                    executed_duration_sec=now - active_command.started_at_monotonic,
                    opening_ratio=runtime.opening_ratio,
                )
                continue

            runtime.state = classify_curtain_state(
                runtime.opening_ratio,
                target_opening_ratio=target,
            )
            runtime.detail_message = (
                f'Curtain {runtime.state.lower()} toward {target:.1f}% open '
                f'(current={runtime.opening_ratio:.1f}%).'
            )

    def _publish_all_states(self) -> None:
        # ALL 상태 묶음를 외부 시스템이나 다음 처리 단계로 전달한다.
        for device_id, device in self._curtain_devices.items():
            self._publish_state(device, self._runtime_states[device_id])

    def _publish_state(self, device: IoTDeviceSpec, runtime: CurtainRuntimeState) -> None:
        # 상태를 외부 시스템이나 다음 처리 단계로 전달한다.
        message = build_curtain_state(
            device,
            state=runtime.state,
            opening_ratio=runtime.opening_ratio,
            detail_message=runtime.detail_message,
        )
        message.header.stamp = self.get_clock().now().to_msg()
        self._device_state_publisher.publish(message)
        signature = (
            message.state,
            round(float(message.opening_ratio), 1),
            message.detail_message,
        )
        if self._last_logged_state_signatures.get(device.device_id) != signature:
            self._last_logged_state_signatures[device.device_id] = signature
            self.get_logger().info(
                'Curtain state updated: '
                f'device={device.device_id}, '
                f'state={message.state}, '
                f'opening_ratio={message.opening_ratio:.1f}, '
                f'detail={message.detail_message}'
            )

    def _publish_result(
        self,
        plan: CurtainExecutionPlan,
        *,
        success: bool,
        state: str,
        detail_message: str,
        executed_duration_sec: float,
        opening_ratio: float,
    ) -> None:
        # 결과를 외부 시스템이나 다음 처리 단계로 전달한다.
        result = String()
        result.data = build_curtain_result_payload(
            plan,
            success=success,
            state=state,
            detail_message=detail_message,
            executed_duration_sec=executed_duration_sec,
            opening_ratio=opening_ratio,
        )
        self._command_result_publisher.publish(result)
        self.get_logger().info(
            f'Curtain result published: command_id={plan.command_id}, state={state}, success={success}'
        )


def _clamp_percent(value: float) -> float:
    # percent 값을 허용 범위로 제한한다.
    return max(0.0, min(100.0, float(value)))


def main(args=None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = CurtainControllerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
