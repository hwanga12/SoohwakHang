from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import uuid

from agribot_interfaces.msg import MissionStatus, RobotStatus
from geometry_msgs.msg import Pose, Vector3
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String


class RobotMode(str, Enum):
    IDLE = 'IDLE'
    PATROL = 'PATROL'
    OBSERVE = 'OBSERVE'
    HARVEST = 'HARVEST'
    RETURN_HOME = 'RETURN_HOME'
    IOT_ACTION = 'IOT_ACTION'
    ERROR = 'ERROR'
    STOPPED = 'STOPPED'


class MissionState(str, Enum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    PAUSED = 'PAUSED'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'
    CANCELED = 'CANCELED'


class MissionType(str, Enum):
    PATROL = 'PATROL'
    OBSERVE = 'OBSERVE'
    HARVEST = 'HARVEST'
    RETURN_HOME = 'RETURN_HOME'
    IOT_ACTION = 'IOT_ACTION'


@dataclass(slots=True)
class MissionSnapshot:
    mission_id: str
    mission_type: str
    state: str
    current_phase: str
    zone_id: str
    target_id: str
    progress_pct: float
    retry_count: int
    detail_message: str


class MissionStateMachine:
    """Pure-Python mission state machine so transitions stay testable."""

    def __init__(self, zone_id: str) -> None:
        self._zone_id = zone_id
        self._last_completed_mission_type = ''
        self._last_completed_target_id = ''
        self.reset()

    def reset(self) -> None:
        self.robot_mode = RobotMode.IDLE.value
        self.mission_state = MissionState.COMPLETED.value
        self.mission_id = ''
        self.mission_type = ''
        self.current_phase = 'IDLE'
        self.target_id = ''
        self.progress_pct = 0.0
        self.retry_count = 0
        self.detail_message = 'Mission manager initialized.'
        self._paused_mode = ''
        self._paused_phase = ''

    def start_mission(
        self,
        mission_type: str,
        *,
        target_id: str = '',
        detail_message: str = '',
    ) -> None:
        normalized_type = mission_type.upper()
        if normalized_type not in {item.value for item in MissionType}:
            raise ValueError(f'Unsupported mission type: {mission_type}')

        self.mission_id = f'mission-{uuid.uuid4()}'
        self.mission_type = normalized_type
        self.mission_state = MissionState.RUNNING.value
        self.robot_mode = normalized_type
        self.current_phase = normalized_type
        self.target_id = target_id
        self.progress_pct = 0.0
        self.retry_count = 0
        self.detail_message = detail_message or f'{normalized_type} mission started.'
        self._paused_mode = ''
        self._paused_phase = ''

    def transition_phase(self, robot_mode: str, *, detail_message: str = '') -> None:
        normalized_mode = robot_mode.upper()
        if normalized_mode not in {item.value for item in RobotMode}:
            raise ValueError(f'Unsupported robot mode: {robot_mode}')
        self.robot_mode = normalized_mode
        self.current_phase = normalized_mode
        if self.mission_state == MissionState.PAUSED.value and normalized_mode != RobotMode.STOPPED.value:
            self.mission_state = MissionState.RUNNING.value
        if detail_message:
            self.detail_message = detail_message

    def update_progress(self, progress_pct: float, *, detail_message: str = '') -> None:
        self.progress_pct = max(0.0, min(100.0, progress_pct))
        if detail_message:
            self.detail_message = detail_message

    def pause(self, *, detail_message: str = 'Mission paused by operator.') -> None:
        if self.mission_state != MissionState.RUNNING.value:
            return
        self._paused_mode = self.robot_mode
        self._paused_phase = self.current_phase
        self.robot_mode = RobotMode.STOPPED.value
        self.current_phase = 'PAUSED'
        self.mission_state = MissionState.PAUSED.value
        self.detail_message = detail_message

    def resume(self, *, detail_message: str = 'Mission resumed.') -> None:
        if self.mission_state != MissionState.PAUSED.value:
            return
        self.mission_state = MissionState.RUNNING.value
        self.robot_mode = self._paused_mode or self.mission_type or RobotMode.IDLE.value
        self.current_phase = self._paused_phase or self.robot_mode
        self.detail_message = detail_message

    def mark_complete(self, *, detail_message: str = 'Mission completed.') -> None:
        if self.mission_id:
            self._last_completed_mission_type = self.mission_type
            self._last_completed_target_id = self.target_id
        self.mission_state = MissionState.COMPLETED.value
        self.robot_mode = RobotMode.IDLE.value
        self.current_phase = 'IDLE'
        self.progress_pct = 100.0
        self.retry_count = 0
        self.detail_message = detail_message

    def cancel(self, *, detail_message: str = 'Mission canceled.') -> None:
        self.mission_state = MissionState.CANCELED.value
        self.robot_mode = RobotMode.IDLE.value
        self.current_phase = 'IDLE'
        self.detail_message = detail_message

    def fail(self, *, detail_message: str = 'Mission failed.') -> None:
        self.mission_state = MissionState.FAILED.value
        self.robot_mode = RobotMode.ERROR.value
        self.current_phase = 'ERROR'
        self.retry_count += 1
        self.detail_message = detail_message

    def snapshot(self) -> MissionSnapshot:
        return MissionSnapshot(
            mission_id=self.mission_id,
            mission_type=self.mission_type,
            state=self.mission_state,
            current_phase=self.current_phase,
            zone_id=self._zone_id,
            target_id=self.target_id,
            progress_pct=self.progress_pct,
            retry_count=self.retry_count,
            detail_message=self.detail_message,
        )


class MissionManagerNode(Node):
    """Mission manager skeleton for state, phase, and command handling."""

    def __init__(self) -> None:
        super().__init__('mission_manager')
        self.declare_parameter('robot_id', 'agribot_01')
        self.declare_parameter('zone_id', 'farm_01')
        self.declare_parameter('odometry_topic', '/odometry/filtered')
        self.declare_parameter('command_topic', '/mission/command')
        self.declare_parameter('mission_status_topic', '/mission/status')
        self.declare_parameter('robot_status_topic', '/robot/status')
        self.declare_parameter('status_publish_hz', 2.0)

        self._robot_id = str(self.get_parameter('robot_id').value)
        self._zone_id = str(self.get_parameter('zone_id').value)
        self._mission_machine = MissionStateMachine(self._zone_id)
        self._last_pose = Pose()
        self._last_linear_velocity = Vector3()
        self._last_angular_velocity = Vector3()

        mission_status_topic = str(self.get_parameter('mission_status_topic').value)
        robot_status_topic = str(self.get_parameter('robot_status_topic').value)
        odometry_topic = str(self.get_parameter('odometry_topic').value)
        command_topic = str(self.get_parameter('command_topic').value)
        status_publish_hz = max(0.5, float(self.get_parameter('status_publish_hz').value))

        self._mission_status_publisher = self.create_publisher(
            MissionStatus,
            mission_status_topic,
            10,
        )
        self._robot_status_publisher = self.create_publisher(
            RobotStatus,
            robot_status_topic,
            10,
        )
        self._odometry_subscription = self.create_subscription(
            Odometry,
            odometry_topic,
            self._handle_odometry,
            20,
        )
        self._command_subscription = self.create_subscription(
            String,
            command_topic,
            self._handle_command,
            20,
        )
        self._publish_timer = self.create_timer(
            1.0 / status_publish_hz,
            self._publish_status,
        )

        self.get_logger().info(
            'Mission manager skeleton ready. '
            f'command_topic={command_topic}, '
            f'mission_status_topic={mission_status_topic}, '
            f'robot_status_topic={robot_status_topic}'
        )
        self._publish_status()

    def _handle_odometry(self, msg: Odometry) -> None:
        self._last_pose = msg.pose.pose
        self._last_linear_velocity.x = float(msg.twist.twist.linear.x)
        self._last_linear_velocity.y = float(msg.twist.twist.linear.y)
        self._last_linear_velocity.z = float(msg.twist.twist.linear.z)
        self._last_angular_velocity.x = float(msg.twist.twist.angular.x)
        self._last_angular_velocity.y = float(msg.twist.twist.angular.y)
        self._last_angular_velocity.z = float(msg.twist.twist.angular.z)

    def _handle_command(self, msg: String) -> None:
        raw_command = msg.data.strip()
        if not raw_command:
            return

        command, _, argument = raw_command.partition(':')
        normalized_command = command.strip().lower()
        argument = argument.strip()

        try:
            if normalized_command == 'patrol_start':
                self._mission_machine.start_mission(
                    MissionType.PATROL.value,
                    target_id=argument,
                    detail_message='Patrol mission started.',
                )
            elif normalized_command == 'observe_start':
                self._mission_machine.start_mission(
                    MissionType.OBSERVE.value,
                    target_id=argument,
                    detail_message='Observe mission started.',
                )
            elif normalized_command == 'harvest_start':
                self._mission_machine.start_mission(
                    MissionType.HARVEST.value,
                    target_id=argument,
                    detail_message='Harvest mission started.',
                )
            elif normalized_command == 'return_home':
                self._mission_machine.start_mission(
                    MissionType.RETURN_HOME.value,
                    target_id=argument,
                    detail_message='Return-home mission started.',
                )
            elif normalized_command == 'iot_action':
                self._mission_machine.start_mission(
                    MissionType.IOT_ACTION.value,
                    target_id=argument,
                    detail_message='IoT action mission started.',
                )
            elif normalized_command == 'phase':
                next_mode = argument or RobotMode.IDLE.value
                self._mission_machine.transition_phase(
                    next_mode,
                    detail_message=f'Phase changed to {next_mode.upper()}.',
                )
            elif normalized_command == 'progress':
                progress_value = float(argument or '0.0')
                self._mission_machine.update_progress(
                    progress_value,
                    detail_message=f'Progress updated to {progress_value:.1f}%.',
                )
            elif normalized_command == 'pause':
                self._mission_machine.pause()
            elif normalized_command == 'resume':
                self._mission_machine.resume()
            elif normalized_command == 'complete':
                self._mission_machine.mark_complete()
            elif normalized_command == 'cancel':
                self._mission_machine.cancel()
            elif normalized_command == 'fail':
                self._mission_machine.fail(detail_message=argument or 'Mission failed.')
            elif normalized_command == 'reset':
                self._mission_machine.reset()
            else:
                self.get_logger().warning(f'Unsupported mission command: {raw_command}')
                return
        except ValueError as exc:
            self.get_logger().warning(f'Failed to apply command "{raw_command}": {exc}')
            return

        snapshot = self._mission_machine.snapshot()
        self.get_logger().info(
            'Mission command applied: '
            f'command={raw_command}, '
            f'mission_type={snapshot.mission_type or "NONE"}, '
            f'state={snapshot.state}, '
            f'phase={snapshot.current_phase}, '
            f'target={snapshot.target_id or "NONE"}'
        )
        self._publish_status()

    def _publish_status(self) -> None:
        mission_snapshot = self._mission_machine.snapshot()
        now = self.get_clock().now().to_msg()

        mission_status = MissionStatus()
        mission_status.header.stamp = now
        mission_status.header.frame_id = 'map'
        mission_status.mission_id = mission_snapshot.mission_id
        mission_status.mission_type = mission_snapshot.mission_type
        mission_status.state = mission_snapshot.state
        mission_status.current_phase = mission_snapshot.current_phase
        mission_status.zone_id = mission_snapshot.zone_id
        mission_status.target_id = mission_snapshot.target_id
        mission_status.progress_pct = mission_snapshot.progress_pct
        mission_status.retry_count = mission_snapshot.retry_count
        mission_status.detail_message = mission_snapshot.detail_message
        self._mission_status_publisher.publish(mission_status)

        robot_status = RobotStatus()
        robot_status.header.stamp = now
        robot_status.header.frame_id = 'map'
        robot_status.robot_id = self._robot_id
        robot_status.zone_id = self._zone_id
        robot_status.mission_id = mission_snapshot.mission_id
        robot_status.mode = self._mission_machine.robot_mode
        robot_status.state = mission_snapshot.state
        robot_status.pose = self._last_pose
        robot_status.linear_velocity = self._last_linear_velocity
        robot_status.angular_velocity = self._last_angular_velocity
        robot_status.is_returning_home = (
            self._mission_machine.robot_mode == RobotMode.RETURN_HOME.value
        )
        robot_status.has_error = (
            self._mission_machine.robot_mode == RobotMode.ERROR.value
        )
        robot_status.error_code = (
            'MISSION_ERROR' if robot_status.has_error else ''
        )
        robot_status.error_message = (
            mission_snapshot.detail_message if robot_status.has_error else ''
        )
        self._robot_status_publisher.publish(robot_status)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MissionManagerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
