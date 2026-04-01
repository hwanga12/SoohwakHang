# 이 모듈은 IoT 장치 연동 패키지에서 watering controller node 장치 흐름을 담당한다.
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

from .device_mapping import IoTDeviceSpec, get_default_iot_devices_path, load_iot_device_catalog
from .watering_controller_logic import (
    WateringExecutionPlan,
    build_watering_result_payload,
    build_watering_state,
    plan_watering_command,
)


@dataclass(slots=True)
class ActiveWateringCommand:
    # active 급수 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    plan: WateringExecutionPlan
    started_at_monotonic: float
    timer: object


class WateringControllerNode(Node):
    # ROS 2 실행 환경에서 급수 controller 흐름을 담당하는 노드 클래스를 정의한다.

    def __init__(self) -> None:
        # WateringControllerNode 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__('watering_controller_node')
        callback_group = ReentrantCallbackGroup()

        self.declare_parameter('iot_devices_file', str(get_default_iot_devices_path()))
        self.declare_parameter('command_topic', '/iot/commands/dispatch')
        self.declare_parameter('device_state_topic', '/iot/device_state')
        self.declare_parameter('command_result_topic', '/iot/command_result')
        self.declare_parameter('zone_id_filter', '')

        catalog_path = Path(str(self.get_parameter('iot_devices_file').value)).expanduser()
        if not catalog_path.is_absolute():
            catalog_path = get_default_iot_devices_path().parent / catalog_path
        self._catalog = load_iot_device_catalog(catalog_path)
        self._command_topic = str(self.get_parameter('command_topic').value)
        self._device_state_topic = str(self.get_parameter('device_state_topic').value)
        self._command_result_topic = str(self.get_parameter('command_result_topic').value)
        self._zone_id_filter = str(self.get_parameter('zone_id_filter').value).strip()

        self._watering_devices = {
            device.device_id: device
            for device in self._catalog.devices.values()
            if device.device_type == 'watering'
            and (not self._zone_id_filter or device.zone_id == self._zone_id_filter)
        }
        self._active_commands: dict[str, ActiveWateringCommand] = {}

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

        for device in self._watering_devices.values():
            self._publish_state(
                device,
                state='OFF',
                current_value=0.0,
                detail_message='Watering controller idle.',
            )

        self.get_logger().info(
            'Watering controller node ready. '
            f'iot_devices_file={catalog_path}, '
            f'command_topic={self._command_topic}, '
            f'device_state_topic={self._device_state_topic}, '
            f'command_result_topic={self._command_result_topic}, '
            f'device_count={len(self._watering_devices)}'
        )

    def _handle_command(self, message: IoTCommand) -> None:
        # handle 명령 정보를 계산해 반환한다.
        if message.device_type.strip() != 'watering':
            return

        device = self._resolve_device(message)
        if device is None:
            self.get_logger().warning(
                f'Ignoring watering command for unknown zone/device: zone={message.zone_id}, device={message.device_id}'
            )
            return

        plan = plan_watering_command(message, device)
        if not plan.accepted:
            self._publish_result(
                plan,
                success=False,
                state='REJECTED',
                detail_message=plan.detail_message,
                executed_duration_sec=0.0,
            )
            return

        if plan.command_type == 'dispense_water':
            self._start_watering(device, plan)
            return

        self._stop_active_command(device, reason=plan.detail_message)
        self._publish_state(
            device,
            state='OFF',
            current_value=0.0,
            detail_message=plan.detail_message,
        )
        self._publish_result(
            plan,
            success=True,
            state='STOPPED' if plan.command_type == 'stop_watering' else 'HOLD',
            detail_message=plan.detail_message,
            executed_duration_sec=0.0,
        )

    def _resolve_device(self, message: IoTCommand) -> IoTDeviceSpec | None:
        # 현재 입력 조건을 바탕으로 장치를 계산하거나 결정한다.
        if message.device_id and message.device_id in self._watering_devices:
            return self._watering_devices[message.device_id]
        zone_id = message.zone_id.strip() or self._catalog.default_zone_id
        try:
            device = self._catalog.primary_device(zone_id, 'watering')
        except KeyError:
            return None
        return self._watering_devices.get(device.device_id)

    def _start_watering(self, device: IoTDeviceSpec, plan: WateringExecutionPlan) -> None:
        # 급수 실행 흐름을 시작하거나 마무리한다.
        self._stop_active_command(device, reason='Superseded by a newer watering command.')
        self._publish_state(
            device,
            state='ON',
            current_value=plan.target_value,
            detail_message=plan.detail_message,
        )
        if plan.immediate_completion:
            self._publish_state(
                device,
                state='OFF',
                current_value=0.0,
                detail_message='Watering completed immediately.',
            )
            self._publish_result(
                plan,
                success=True,
                state='COMPLETED',
                detail_message='Watering completed immediately.',
                executed_duration_sec=0.0,
            )
            return

        timer = self.create_timer(
            plan.duration_sec,
            lambda device_id=device.device_id: self._complete_watering(device_id),
        )
        self._active_commands[device.device_id] = ActiveWateringCommand(
            plan=plan,
            started_at_monotonic=time.monotonic(),
            timer=timer,
        )
        self.get_logger().info(
            'Watering started: '
            f'device={device.device_id}, '
            f'target={plan.target_value:.1f}{plan.unit}, '
            f'duration={plan.duration_sec:.2f}s'
        )

    def _complete_watering(self, device_id: str) -> None:
        # complete 급수 정보를 계산해 반환한다.
        active_command = self._active_commands.pop(device_id, None)
        if active_command is None:
            return
        active_command.timer.cancel()
        self.destroy_timer(active_command.timer)

        device = self._watering_devices[device_id]
        executed_duration_sec = time.monotonic() - active_command.started_at_monotonic
        self._publish_state(
            device,
            state='OFF',
            current_value=0.0,
            detail_message='Watering completed successfully.',
        )
        self._publish_result(
            active_command.plan,
            success=True,
            state='COMPLETED',
            detail_message='Watering completed successfully.',
            executed_duration_sec=executed_duration_sec,
        )

    def _stop_active_command(self, device: IoTDeviceSpec, *, reason: str) -> None:
        # active 명령 실행 흐름을 시작하거나 마무리한다.
        active_command = self._active_commands.pop(device.device_id, None)
        if active_command is None:
            return
        active_command.timer.cancel()
        self.destroy_timer(active_command.timer)
        executed_duration_sec = time.monotonic() - active_command.started_at_monotonic
        self._publish_result(
            active_command.plan,
            success=False,
            state='INTERRUPTED',
            detail_message=reason,
            executed_duration_sec=executed_duration_sec,
        )

    def _publish_state(
        self,
        device: IoTDeviceSpec,
        *,
        state: str,
        current_value: float,
        detail_message: str,
    ) -> None:
        # 상태를 외부 시스템이나 다음 처리 단계로 전달한다.
        message = build_watering_state(
            device,
            state=state,
            current_value=current_value,
            detail_message=detail_message,
        )
        message.header.stamp = self.get_clock().now().to_msg()
        self._device_state_publisher.publish(message)
        self.get_logger().info(
            f'Watering state updated: device={device.device_id}, state={state}, detail={detail_message}'
        )

    def _publish_result(
        self,
        plan: WateringExecutionPlan,
        *,
        success: bool,
        state: str,
        detail_message: str,
        executed_duration_sec: float,
    ) -> None:
        # 결과를 외부 시스템이나 다음 처리 단계로 전달한다.
        result = String()
        result.data = build_watering_result_payload(
            plan,
            success=success,
            state=state,
            detail_message=detail_message,
            executed_duration_sec=executed_duration_sec,
        )
        self._command_result_publisher.publish(result)
        self.get_logger().info(
            'Watering result published: '
            f'device={plan.device_id}, command={plan.command_type}, state={state}, success={success}'
        )

    def destroy_node(self) -> bool:
        # destroy 노드 정보를 계산해 반환한다.
        for active_command in self._active_commands.values():
            active_command.timer.cancel()
            self.destroy_timer(active_command.timer)
        self._active_commands.clear()
        return super().destroy_node()


def main(args=None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = WateringControllerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
