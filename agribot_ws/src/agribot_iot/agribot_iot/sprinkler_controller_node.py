from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

from agribot_interfaces.msg import IoTCommand, IoTDeviceState
from ament_index_python.packages import get_package_share_directory
from rclpy.callback_groups import ReentrantCallbackGroup
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from .device_mapping import IoTDeviceSpec, get_default_iot_devices_path, load_iot_device_catalog
from .sprinkler_controller_logic import (
    SprinklerExecutionPlan,
    build_sprinkler_result_payload,
    build_sprinkler_state,
    plan_sprinkler_command,
)


@dataclass(slots=True)
class ActiveSprinklerCommand:
    plan: SprinklerExecutionPlan
    started_at_monotonic: float
    timer: object
    effect_entity_name: str


class SprinklerControllerNode(Node):
    """Execute sprinkler spray commands and mirror them as Gazebo spray effects."""

    def __init__(self) -> None:
        super().__init__('sprinkler_controller_node')
        callback_group = ReentrantCallbackGroup()
        default_world_file = Path(get_package_share_directory('agribot_description')) / 'worlds' / 'farm_world.sdf'

        self.declare_parameter('iot_devices_file', str(get_default_iot_devices_path()))
        self.declare_parameter('command_topic', '/iot/commands/dispatch')
        self.declare_parameter('device_state_topic', '/iot/device_state')
        self.declare_parameter('command_result_topic', '/iot/command_result')
        self.declare_parameter('zone_id_filter', '')
        self.declare_parameter('world_name', 'farm_world')
        self.declare_parameter(
            'world_file',
            str(default_world_file),
        )

        catalog_path = Path(str(self.get_parameter('iot_devices_file').value)).expanduser()
        if not catalog_path.is_absolute():
            catalog_path = get_default_iot_devices_path().parent / catalog_path
        self._catalog = load_iot_device_catalog(catalog_path)
        self._command_topic = str(self.get_parameter('command_topic').value)
        self._device_state_topic = str(self.get_parameter('device_state_topic').value)
        self._command_result_topic = str(self.get_parameter('command_result_topic').value)
        self._zone_id_filter = str(self.get_parameter('zone_id_filter').value).strip()
        self._world_name = str(self.get_parameter('world_name').value).strip() or 'farm_world'
        raw_world_file = str(self.get_parameter('world_file').value).strip()
        self._world_file = Path(raw_world_file).expanduser() if raw_world_file else default_world_file

        self._sprinkler_devices = {
            device.device_id: device
            for device in self._catalog.devices.values()
            if device.device_type == 'sprinkler'
            and (not self._zone_id_filter or device.zone_id == self._zone_id_filter)
        }
        self._active_commands: dict[str, ActiveSprinklerCommand] = {}
        self._sprinkler_positions = _load_sprinkler_positions(self._world_file)

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

        for device in self._sprinkler_devices.values():
            self._publish_state(
                device,
                state='IDLE',
                current_value=0.0,
                detail_message='Sprinkler controller idle.',
            )

        self.get_logger().info(
            'Sprinkler controller node ready. '
            f'iot_devices_file={catalog_path}, '
            f'command_topic={self._command_topic}, '
            f'device_state_topic={self._device_state_topic}, '
            f'command_result_topic={self._command_result_topic}, '
            f'device_count={len(self._sprinkler_devices)}, '
            f'world_name={self._world_name}, world_file={self._world_file}'
        )

    def _handle_command(self, message: IoTCommand) -> None:
        if message.device_type.strip().lower() != 'sprinkler':
            return

        device = self._resolve_device(message)
        if device is None:
            self.get_logger().warning(
                f'Ignoring sprinkler command for unknown zone/device: zone={message.zone_id}, device={message.device_id}'
            )
            return

        plan = plan_sprinkler_command(message, device)
        if not plan.accepted:
            self._publish_result(
                plan,
                success=False,
                state='REJECTED',
                detail_message=plan.detail_message,
                executed_duration_sec=0.0,
            )
            return

        if plan.immediate_completion:
            self._stop_active_command(device, reason=plan.detail_message)
            self._publish_state(
                device,
                state='IDLE',
                current_value=0.0,
                detail_message=plan.detail_message,
            )
            self._publish_result(
                plan,
                success=True,
                state='STOPPED',
                detail_message=plan.detail_message,
                executed_duration_sec=0.0,
            )
            return

        self._start_spray(device, plan)

    def _resolve_device(self, message: IoTCommand) -> IoTDeviceSpec | None:
        if message.device_id and message.device_id in self._sprinkler_devices:
            return self._sprinkler_devices[message.device_id]
        zone_id = message.zone_id.strip() or self._catalog.default_zone_id
        try:
            device = self._catalog.primary_device(zone_id, 'sprinkler')
        except KeyError:
            return None
        return self._sprinkler_devices.get(device.device_id)

    def _start_spray(self, device: IoTDeviceSpec, plan: SprinklerExecutionPlan) -> None:
        self._stop_active_command(device, reason='Superseded by a newer sprinkler command.')
        effect_entity_name = (
            f'{device.device_id}_spray_effect_'
            f'{int(self.get_clock().now().nanoseconds / 1_000_000)}'
        )
        effect_spawned = self._spawn_effect(
            device_id=device.device_id,
            effect_entity_name=effect_entity_name,
            effect_color=plan.effect_color,
        )

        self._publish_state(
            device,
            state='SPRAYING',
            current_value=plan.duration_sec,
            detail_message=(
                plan.detail_message
                if effect_spawned
                else f'{plan.detail_message} Gazebo effect spawn failed.'
            ),
        )

        timer = self.create_timer(
            plan.duration_sec,
            lambda device_id=device.device_id: self._complete_spray(device_id),
        )
        self._active_commands[device.device_id] = ActiveSprinklerCommand(
            plan=plan,
            started_at_monotonic=time.monotonic(),
            timer=timer,
            effect_entity_name=effect_entity_name,
        )
        self.get_logger().info(
            'Sprinkler spray started: '
            f'device={device.device_id}, '
            f'command={plan.command_type}, '
            f'effect_color={plan.effect_color}, '
            f'duration={plan.duration_sec:.2f}s'
        )

    def _complete_spray(self, device_id: str) -> None:
        active_command = self._active_commands.pop(device_id, None)
        if active_command is None:
            return
        active_command.timer.cancel()
        self.destroy_timer(active_command.timer)

        self._remove_effect(active_command.effect_entity_name)
        device = self._sprinkler_devices[device_id]
        executed_duration_sec = time.monotonic() - active_command.started_at_monotonic
        self._publish_state(
            device,
            state='IDLE',
            current_value=0.0,
            detail_message='Sprinkler spray completed successfully.',
        )
        self._publish_result(
            active_command.plan,
            success=True,
            state='COMPLETED',
            detail_message='Sprinkler spray completed successfully.',
            executed_duration_sec=executed_duration_sec,
        )

    def _stop_active_command(self, device: IoTDeviceSpec, *, reason: str) -> None:
        active_command = self._active_commands.pop(device.device_id, None)
        if active_command is None:
            return
        active_command.timer.cancel()
        self.destroy_timer(active_command.timer)
        self._remove_effect(active_command.effect_entity_name)
        executed_duration_sec = time.monotonic() - active_command.started_at_monotonic
        self._publish_result(
            active_command.plan,
            success=False,
            state='INTERRUPTED',
            detail_message=reason,
            executed_duration_sec=executed_duration_sec,
        )

    def _spawn_effect(
        self,
        *,
        device_id: str,
        effect_entity_name: str,
        effect_color: str,
    ) -> bool:
        position = self._sprinkler_positions.get(device_id)
        if position is None:
            self.get_logger().warning(f'Cannot spawn Gazebo spray effect; no pose mapped for {device_id}.')
            return False

        effect_sdf = _build_effect_sdf(effect_entity_name, effect_color)
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            suffix='.sdf',
            prefix=f'{effect_entity_name}_',
            delete=False,
        ) as stream:
            stream.write(effect_sdf)
            temp_path = Path(stream.name)
        try:
            completed = subprocess.run(
                [
                    'ros2',
                    'run',
                    'ros_gz_sim',
                    'create',
                    '-world',
                    self._world_name,
                    '-file',
                    str(temp_path),
                    '-name',
                    effect_entity_name,
                    '-x',
                    f'{position[0]:.3f}',
                    '-y',
                    f'{position[1]:.3f}',
                    '-z',
                    f'{position[2]:.3f}',
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=5.0,
            )
        except subprocess.TimeoutExpired:
            self.get_logger().warning(
                f'Gazebo spray effect creation timed out: entity={effect_entity_name}'
            )
            return False
        finally:
            temp_path.unlink(missing_ok=True)

        if completed.returncode != 0:
            self.get_logger().warning(
                'Failed to spawn Gazebo spray effect: '
                f'entity={effect_entity_name}, stderr={completed.stderr.strip()}'
            )
            return False
        self.get_logger().info(
            f'Gazebo spray effect spawned: entity={effect_entity_name}, color={effect_color}'
        )
        return True

    def _remove_effect(self, effect_entity_name: str) -> None:
        try:
            completed = subprocess.run(
                [
                    'gz',
                    'service',
                    '-s',
                    f'/world/{self._world_name}/remove',
                    '--reqtype',
                    'gz.msgs.Entity',
                    '--reptype',
                    'gz.msgs.Boolean',
                    '--timeout',
                    '3000',
                    '--req',
                    f'name: "{effect_entity_name}" type: 6',
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=4.0,
            )
        except subprocess.TimeoutExpired:
            self.get_logger().warning(
                f'Gazebo spray effect removal timed out: entity={effect_entity_name}'
            )
            return
        if completed.returncode == 0:
            self.get_logger().info(f'Gazebo spray effect removed: entity={effect_entity_name}')
        else:
            self.get_logger().warning(
                'Gazebo spray effect removal failed: '
                f'entity={effect_entity_name}, stderr={completed.stderr.strip()}'
            )

    def _publish_state(
        self,
        device: IoTDeviceSpec,
        *,
        state: str,
        current_value: float,
        detail_message: str,
    ) -> None:
        message = build_sprinkler_state(
            device,
            state=state,
            current_value=current_value,
            detail_message=detail_message,
        )
        message.header.stamp = self.get_clock().now().to_msg()
        self._device_state_publisher.publish(message)
        self.get_logger().info(
            f'Sprinkler state updated: device={device.device_id}, state={state}, detail={detail_message}'
        )

    def _publish_result(
        self,
        plan: SprinklerExecutionPlan,
        *,
        success: bool,
        state: str,
        detail_message: str,
        executed_duration_sec: float,
    ) -> None:
        result = String()
        result.data = build_sprinkler_result_payload(
            plan,
            success=success,
            state=state,
            detail_message=detail_message,
            executed_duration_sec=executed_duration_sec,
        )
        self._command_result_publisher.publish(result)
        self.get_logger().info(
            'Sprinkler result published: '
            f'device={plan.device_id}, command={plan.command_type}, state={state}, success={success}'
        )

    def destroy_node(self) -> bool:
        for active_command in self._active_commands.values():
            active_command.timer.cancel()
            self.destroy_timer(active_command.timer)
            self._remove_effect(active_command.effect_entity_name)
        self._active_commands.clear()
        return super().destroy_node()


def _load_sprinkler_positions(world_file: Path) -> dict[str, tuple[float, float, float]]:
    if not world_file.exists() or world_file.is_dir():
        return {}

    root = ET.fromstring(world_file.read_text(encoding='utf-8'))
    positions: dict[str, tuple[float, float, float]] = {}
    for include in root.findall('.//include'):
        name = (include.findtext('name') or '').strip()
        if not name.startswith('sprinkler_'):
            continue
        pose_text = (include.findtext('pose') or '').strip()
        parts = pose_text.split()
        if len(parts) < 3:
            continue
        try:
            positions[name] = (float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError:
            continue
    return positions


def _build_effect_sdf(effect_entity_name: str, effect_color: str) -> str:
    rgba = _resolve_rgba(effect_color)
    nozzle_alpha = max(0.22, min(0.95, rgba[3] + 0.18))
    spray_visuals = '\n'.join(
        _build_spray_visual_block(
            visual_name=name,
            pose=pose,
            rgba=rgba,
            radius=radius,
            length=length,
        )
        for name, pose, radius, length in (
            ('spray_stream_center', '0 0 0.56 0 -1.52 0', 0.042, 0.78),
            ('spray_stream_left', '0 0 0.52 0 -1.35 0.36', 0.032, 0.72),
            ('spray_stream_right', '0 0 0.52 0 -1.35 -0.36', 0.032, 0.72),
            ('spray_stream_front', '0 0 0.50 0 -1.28 1.57', 0.028, 0.68),
            ('spray_stream_back', '0 0 0.50 0 -1.28 -1.57', 0.028, 0.68),
        )
    )
    side_emitters = '\n'.join(
        _build_particle_emitter_block(
            emitter_name=name,
            pose=pose,
            rgba=rgba,
            rate=rate,
            min_velocity=min_velocity,
            max_velocity=max_velocity,
        )
        for name, pose, rate, min_velocity, max_velocity in (
            ('spray_center', '0 0 0.24 0 -1.52 0', 260, 2.0, 2.8),
            ('spray_left', '0 0 0.24 0 -1.35 0.36', 180, 1.8, 2.5),
            ('spray_right', '0 0 0.24 0 -1.35 -0.36', 180, 1.8, 2.5),
            ('spray_front', '0 0 0.24 0 -1.28 1.57', 160, 1.7, 2.4),
            ('spray_back', '0 0 0.24 0 -1.28 -1.57', 160, 1.7, 2.4),
        )
    )
    return f"""<?xml version="1.0" ?>
<sdf version="1.9">
  <model name="{effect_entity_name}">
    <static>true</static>
    <link name="spray_link">
      <visual name="spray_nozzle">
        <pose>0 0 0.14 0 0 0</pose>
        <geometry>
          <cylinder>
            <radius>0.05</radius>
            <length>0.08</length>
          </cylinder>
        </geometry>
        <material>
          <ambient>{rgba[0]} {rgba[1]} {rgba[2]} {nozzle_alpha}</ambient>
          <diffuse>{rgba[0]} {rgba[1]} {rgba[2]} {nozzle_alpha}</diffuse>
          <specular>0.2 0.2 0.2 0.1</specular>
        </material>
        <transparency>{max(0.0, 1.0 - nozzle_alpha):.3f}</transparency>
        <cast_shadows>false</cast_shadows>
      </visual>
{spray_visuals}
{side_emitters}
    </link>
  </model>
</sdf>
"""


def _build_particle_emitter_block(
    *,
    emitter_name: str,
    pose: str,
    rgba: tuple[float, float, float, float],
    rate: int,
    min_velocity: float,
    max_velocity: float,
) -> str:
    start_alpha = min(0.95, max(0.60, rgba[3] + 0.28))
    end_alpha = max(0.08, rgba[3] - 0.18)
    return f"""      <particle_emitter name="{emitter_name}" type="point">
        <pose>{pose}</pose>
        <emitting>true</emitting>
        <duration>0</duration>
        <particle_size>0.055 0.022 0.022</particle_size>
        <lifetime>1.15</lifetime>
        <rate>{rate}</rate>
        <min_velocity>{min_velocity:.2f}</min_velocity>
        <max_velocity>{max_velocity:.2f}</max_velocity>
        <scale_rate>0.10</scale_rate>
        <color_start>{rgba[0]} {rgba[1]} {rgba[2]} {start_alpha:.2f}</color_start>
        <color_end>{rgba[0]} {rgba[1]} {rgba[2]} {end_alpha:.2f}</color_end>
        <particle_scatter_ratio>0.03</particle_scatter_ratio>
      </particle_emitter>"""


def _build_spray_visual_block(
    *,
    visual_name: str,
    pose: str,
    rgba: tuple[float, float, float, float],
    radius: float,
    length: float,
) -> str:
    beam_alpha = min(0.92, max(0.42, rgba[3] + 0.28))
    emissive_alpha = min(0.7, beam_alpha * 0.45)
    return f"""      <visual name="{visual_name}">
        <pose>{pose}</pose>
        <geometry>
          <cylinder>
            <radius>{radius:.3f}</radius>
            <length>{length:.3f}</length>
          </cylinder>
        </geometry>
        <material>
          <ambient>{rgba[0]} {rgba[1]} {rgba[2]} {beam_alpha:.2f}</ambient>
          <diffuse>{rgba[0]} {rgba[1]} {rgba[2]} {beam_alpha:.2f}</diffuse>
          <specular>0.08 0.08 0.08 0.05</specular>
          <emissive>{rgba[0]} {rgba[1]} {rgba[2]} {emissive_alpha:.2f}</emissive>
        </material>
        <transparency>{max(0.0, 1.0 - beam_alpha):.3f}</transparency>
        <cast_shadows>false</cast_shadows>
      </visual>"""


def _resolve_rgba(effect_color: str) -> tuple[float, float, float, float]:
    normalized = effect_color.strip().lower()
    if normalized == 'blue':
        return (0.15, 0.55, 1.0, 0.42)
    if normalized == 'green':
        return (0.2, 0.9, 0.35, 0.42)
    if normalized == 'red':
        return (1.0, 0.1, 0.1, 0.45)
    if normalized == 'yellow':
        return (1.0, 0.85, 0.1, 0.45)
    return (0.8, 0.8, 0.8, 0.35)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = SprinklerControllerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
