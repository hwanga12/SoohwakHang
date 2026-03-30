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
from .nutrient_controller_logic import (
    NutrientExecutionPlan,
    build_nutrient_result_payload,
    build_nutrient_state,
    plan_nutrient_command,
)


@dataclass(slots=True)
class ActiveNutrientCommand:
    plan: NutrientExecutionPlan
    started_at_monotonic: float
    timer: object


class NutrientControllerNode(Node):
    """Execute nutrient commands and publish state/result messages."""

    def __init__(self) -> None:
        super().__init__('nutrient_controller_node')
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

        self._nutrient_devices = {
            device.device_id: device
            for device in self._catalog.devices.values()
            if device.device_type == 'nutrient'
            and (not self._zone_id_filter or device.zone_id == self._zone_id_filter)
        }
        self._active_commands: dict[str, ActiveNutrientCommand] = {}

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

        for device in self._nutrient_devices.values():
            self._publish_state(
                device,
                state='IDLE',
                current_value=0.0,
                detail_message='Nutrient controller idle.',
            )

        self.get_logger().info(
            'Nutrient controller node ready. '
            f'iot_devices_file={catalog_path}, '
            f'command_topic={self._command_topic}, '
            f'device_state_topic={self._device_state_topic}, '
            f'command_result_topic={self._command_result_topic}, '
            f'device_count={len(self._nutrient_devices)}'
        )

    def _handle_command(self, message: IoTCommand) -> None:
        if message.device_type.strip().lower() != 'nutrient':
            return

        device = self._resolve_device(message)
        if device is None:
            self.get_logger().warning(
                f'Ignoring nutrient command for unknown zone/device: zone={message.zone_id}, device={message.device_id}'
            )
            return

        plan = plan_nutrient_command(message, device)
        if not plan.accepted:
            self._publish_result(
                plan,
                success=False,
                state='REJECTED',
                detail_message=plan.detail_message,
                executed_duration_sec=0.0,
            )
            return

        self._stop_active_command(device, reason='Superseded by a newer nutrient command.')
        self._publish_state(
            device,
            state='DISPENSING',
            current_value=plan.target_value,
            detail_message=plan.detail_message,
        )

        if plan.immediate_completion:
            self._publish_state(
                device,
                state='IDLE',
                current_value=0.0,
                detail_message='Nutrient dispensing completed immediately.',
            )
            self._publish_result(
                plan,
                success=True,
                state='COMPLETED',
                detail_message='Nutrient dispensing completed immediately.',
                executed_duration_sec=0.0,
            )
            return

        timer = self.create_timer(
            plan.duration_sec,
            lambda device_id=device.device_id: self._complete_nutrient(device_id),
        )
        self._active_commands[device.device_id] = ActiveNutrientCommand(
            plan=plan,
            started_at_monotonic=time.monotonic(),
            timer=timer,
        )
        self.get_logger().info(
            'Nutrient dispensing started: '
            f'device={device.device_id}, '
            f'nutrient_type={plan.nutrient_type}, '
            f'target={plan.target_value:.1f}{plan.unit}, '
            f'duration={plan.duration_sec:.2f}s, '
            f'requested_by={plan.requested_by}'
        )

    def _resolve_device(self, message: IoTCommand) -> IoTDeviceSpec | None:
        if message.device_id and message.device_id in self._nutrient_devices:
            return self._nutrient_devices[message.device_id]
        zone_id = message.zone_id.strip() or self._catalog.default_zone_id
        try:
            device = self._catalog.primary_device(zone_id, 'nutrient')
        except KeyError:
            return None
        return self._nutrient_devices.get(device.device_id)

    def _complete_nutrient(self, device_id: str) -> None:
        active_command = self._active_commands.pop(device_id, None)
        if active_command is None:
            return
        active_command.timer.cancel()
        self.destroy_timer(active_command.timer)

        device = self._nutrient_devices[device_id]
        executed_duration_sec = time.monotonic() - active_command.started_at_monotonic
        self._publish_state(
            device,
            state='IDLE',
            current_value=0.0,
            detail_message='Nutrient dispensing completed successfully.',
        )
        self._publish_result(
            active_command.plan,
            success=True,
            state='COMPLETED',
            detail_message='Nutrient dispensing completed successfully.',
            executed_duration_sec=executed_duration_sec,
        )

    def _stop_active_command(self, device: IoTDeviceSpec, *, reason: str) -> None:
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
        message = build_nutrient_state(
            device,
            state=state,
            current_value=current_value,
            detail_message=detail_message,
        )
        message.header.stamp = self.get_clock().now().to_msg()
        self._device_state_publisher.publish(message)
        self.get_logger().info(
            f'Nutrient state updated: device={device.device_id}, state={state}, detail={detail_message}'
        )

    def _publish_result(
        self,
        plan: NutrientExecutionPlan,
        *,
        success: bool,
        state: str,
        detail_message: str,
        executed_duration_sec: float,
    ) -> None:
        result = String()
        result.data = build_nutrient_result_payload(
            plan,
            success=success,
            state=state,
            detail_message=detail_message,
            executed_duration_sec=executed_duration_sec,
        )
        self._command_result_publisher.publish(result)
        self.get_logger().info(
            'Nutrient result published: '
            f'device={plan.device_id}, command={plan.command_type}, state={state}, success={success}'
        )

    def destroy_node(self) -> bool:
        for active_command in self._active_commands.values():
            active_command.timer.cancel()
            self.destroy_timer(active_command.timer)
        self._active_commands.clear()
        return super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = NutrientControllerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
