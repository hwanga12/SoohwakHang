from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import uuid

from agribot_interfaces.msg import MissionStatus, PlantObservation, RobotStatus
from geometry_msgs.msg import Pose, Vector3
from nav_msgs.msg import Odometry
import rclpy
from rclpy.client import Client
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .observation_priority import (
    ObservationInput,
    ObservationPriorityArbiter,
    ObservationTaskCandidate,
)


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


@dataclass(slots=True)
class PatrolStatusSnapshot:
    state: str
    message: str
    current_waypoint_id: str
    next_waypoint_id: str
    current_waypoint_index: int | None
    next_waypoint_index: int | None
    total_waypoints: int
    progress_pct: float


def parse_patrol_status(raw_data: str) -> PatrolStatusSnapshot | None:
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    try:
        total_waypoints = max(0, int(payload.get('total_waypoints', 0) or 0))
    except (TypeError, ValueError):
        return None
    next_waypoint_index = payload.get('next_waypoint_index')
    current_waypoint_index = payload.get('current_waypoint_index')
    try:
        if next_waypoint_index is not None:
            next_waypoint_index = int(next_waypoint_index)
        if current_waypoint_index is not None:
            current_waypoint_index = int(current_waypoint_index)
    except (TypeError, ValueError):
        return None

    progress_pct = 0.0
    if total_waypoints > 0 and next_waypoint_index is not None:
        completed_waypoints = min(max(next_waypoint_index, 0), total_waypoints)
        progress_pct = (completed_waypoints / total_waypoints) * 100.0
    if str(payload.get('state', '')).lower() == 'completed':
        progress_pct = 100.0

    return PatrolStatusSnapshot(
        state=str(payload.get('state', '')).lower(),
        message=str(payload.get('message', '')),
        current_waypoint_id=str(payload.get('current_waypoint_id') or ''),
        next_waypoint_id=str(payload.get('next_waypoint_id') or ''),
        current_waypoint_index=current_waypoint_index,
        next_waypoint_index=next_waypoint_index,
        total_waypoints=total_waypoints,
        progress_pct=max(0.0, min(100.0, progress_pct)),
    )


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

    def note(self, detail_message: str, *, target_id: str | None = None) -> None:
        self.detail_message = detail_message
        if target_id is not None:
            self.target_id = target_id

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


def apply_patrol_status_snapshot(
    machine: MissionStateMachine,
    patrol_status: PatrolStatusSnapshot,
) -> None:
    patrol_active = machine.mission_type == MissionType.PATROL.value
    mission_terminal = machine.mission_state in {
        MissionState.COMPLETED.value,
        MissionState.CANCELED.value,
        MissionState.FAILED.value,
    }

    if not patrol_active and mission_terminal and patrol_status.state not in {'starting', 'running'}:
        return

    target_id = patrol_status.next_waypoint_id or patrol_status.current_waypoint_id
    detail_message = patrol_status.message or 'Patrol status synchronized.'

    if patrol_status.state in {'starting', 'running', 'observing'}:
        if not patrol_active or machine.mission_state in {
            MissionState.COMPLETED.value,
            MissionState.CANCELED.value,
            MissionState.FAILED.value,
        }:
            machine.start_mission(
                MissionType.PATROL.value,
                target_id=target_id,
                detail_message=detail_message,
            )
        elif machine.mission_state == MissionState.PAUSED.value:
            machine.resume(detail_message=detail_message)
            machine.note(detail_message, target_id=target_id)
        else:
            machine.transition_phase(RobotMode.PATROL.value, detail_message=detail_message)
            machine.note(detail_message, target_id=target_id)
        machine.update_progress(patrol_status.progress_pct)
        return

    if not patrol_active:
        return

    if patrol_status.state == 'stopped':
        machine.pause(detail_message=detail_message)
        machine.note(detail_message, target_id=target_id)
        machine.update_progress(patrol_status.progress_pct)
        return

    if patrol_status.state == 'completed':
        machine.update_progress(100.0)
        machine.mark_complete(detail_message=detail_message)
        return

    if patrol_status.state == 'error':
        machine.fail(detail_message=detail_message)
        machine.note(detail_message, target_id=target_id)
        return

    if target_id or detail_message:
        machine.note(detail_message, target_id=target_id or None)
        machine.update_progress(patrol_status.progress_pct)


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
        self.declare_parameter('patrol_status_topic', '/patrol/status')
        self.declare_parameter('patrol_start_service', '/patrol/start')
        self.declare_parameter('patrol_stop_service', '/patrol/stop')
        self.declare_parameter('patrol_resume_service', '/patrol/resume')
        self.declare_parameter('patrol_service_wait_sec', 1.0)
        self.declare_parameter('plant_observation_topic', '/plant_observation')
        self.declare_parameter('observation_duplicate_window_sec', 120.0)
        self.declare_parameter('max_pending_observations', 16)
        self.declare_parameter('interrupt_patrol_on_observation', True)

        self._robot_id = str(self.get_parameter('robot_id').value)
        self._zone_id = str(self.get_parameter('zone_id').value)
        self._mission_machine = MissionStateMachine(self._zone_id)
        self._last_pose = Pose()
        self._last_linear_velocity = Vector3()
        self._last_angular_velocity = Vector3()
        self._patrol_service_wait_sec = max(
            0.1,
            float(self.get_parameter('patrol_service_wait_sec').value),
        )
        self._interrupt_patrol_on_observation = bool(
            self.get_parameter('interrupt_patrol_on_observation').value
        )
        self._observation_arbiter = ObservationPriorityArbiter(
            duplicate_window_sec=max(
                1.0,
                float(self.get_parameter('observation_duplicate_window_sec').value),
            ),
            max_pending_events=max(
                1,
                int(self.get_parameter('max_pending_observations').value),
            ),
        )
        self._pending_observation_activation_requested = False

        mission_status_topic = str(self.get_parameter('mission_status_topic').value)
        robot_status_topic = str(self.get_parameter('robot_status_topic').value)
        odometry_topic = str(self.get_parameter('odometry_topic').value)
        command_topic = str(self.get_parameter('command_topic').value)
        status_publish_hz = max(0.5, float(self.get_parameter('status_publish_hz').value))
        patrol_status_topic = str(self.get_parameter('patrol_status_topic').value)
        patrol_start_service = str(self.get_parameter('patrol_start_service').value)
        patrol_stop_service = str(self.get_parameter('patrol_stop_service').value)
        patrol_resume_service = str(self.get_parameter('patrol_resume_service').value)
        plant_observation_topic = str(self.get_parameter('plant_observation_topic').value)

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
        self._patrol_status_subscription = self.create_subscription(
            String,
            patrol_status_topic,
            self._handle_patrol_status,
            20,
        )
        self._plant_observation_subscription = self.create_subscription(
            PlantObservation,
            plant_observation_topic,
            self._handle_plant_observation,
            20,
        )
        self._patrol_start_client = self.create_client(Trigger, patrol_start_service)
        self._patrol_stop_client = self.create_client(Trigger, patrol_stop_service)
        self._patrol_resume_client = self.create_client(Trigger, patrol_resume_service)
        self._publish_timer = self.create_timer(
            1.0 / status_publish_hz,
            self._publish_status,
        )

        self.get_logger().info(
            'Mission manager skeleton ready. '
            f'command_topic={command_topic}, '
            f'mission_status_topic={mission_status_topic}, '
            f'robot_status_topic={robot_status_topic}, '
            f'patrol_status_topic={patrol_status_topic}, '
            f'plant_observation_topic={plant_observation_topic}'
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
            if normalized_command in {'patrol_start', 'start_patrol'}:
                if self._request_patrol_control('start', target_id=argument):
                    self.get_logger().info(
                        'Patrol start requested via mission command handler.'
                    )
                return
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
            elif normalized_command in {'patrol_stop', 'stop_patrol'}:
                if self._request_patrol_control('stop'):
                    self.get_logger().info(
                        'Patrol stop requested via mission command handler.'
                    )
                return
            elif normalized_command in {'patrol_resume', 'resume_patrol'}:
                if self._request_patrol_control('resume'):
                    self.get_logger().info(
                        'Patrol resume requested via mission command handler.'
                    )
                return
            elif normalized_command == 'pause':
                if self._mission_machine.mission_type == MissionType.PATROL.value:
                    if self._request_patrol_control('stop'):
                        self.get_logger().info(
                            'Patrol pause requested via mission command handler.'
                        )
                    return
                self._mission_machine.pause()
            elif normalized_command == 'resume':
                if self._mission_machine.mission_type == MissionType.PATROL.value:
                    if self._request_patrol_control('resume'):
                        self.get_logger().info(
                            'Patrol resume requested via mission command handler.'
                        )
                    return
                self._mission_machine.resume()
            elif normalized_command == 'complete':
                self._mission_machine.mark_complete()
                self._finish_active_observation_candidate()
                self._activate_best_pending_observation(
                    'Queued observation activated after the previous mission completed.'
                )
            elif normalized_command == 'cancel':
                self._mission_machine.cancel()
                self._finish_active_observation_candidate()
                self._activate_best_pending_observation(
                    'Queued observation activated after the previous mission was canceled.'
                )
            elif normalized_command == 'fail':
                self._mission_machine.fail(detail_message=argument or 'Mission failed.')
                self._finish_active_observation_candidate()
            elif normalized_command == 'reset':
                self._mission_machine.reset()
                self._observation_arbiter.clear()
                self._pending_observation_activation_requested = False
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

    def _handle_patrol_status(self, msg: String) -> None:
        snapshot = parse_patrol_status(msg.data)
        if snapshot is None:
            self.get_logger().warning('Ignored invalid patrol status payload.')
            return

        apply_patrol_status_snapshot(self._mission_machine, snapshot)
        if snapshot.state == 'completed':
            self._activate_best_pending_observation(
                'Priority observation activated after patrol completion.'
            )
        self._publish_status()

    def _handle_plant_observation(self, msg: PlantObservation) -> None:
        observation = ObservationInput(
            observation_id=msg.observation_id,
            zone_id=msg.zone_id,
            plant_id=msg.plant_id,
            fruit_id=msg.fruit_id,
            class_name=msg.class_name,
            confidence=float(msg.confidence),
            health_score=float(msg.health_score),
            ready_to_harvest=bool(msg.ready_to_harvest),
            image_path=msg.image_path,
        )
        selection = self._observation_arbiter.register_observation(
            observation,
            now_ns=self.get_clock().now().nanoseconds,
        )
        candidate = selection.selected_candidate

        if candidate is None:
            if selection.reason:
                self.get_logger().warning(selection.reason)
            return

        if selection.is_duplicate:
            self.get_logger().info(
                'Observation duplicate ignored: '
                f'class={candidate.event_kind}, target={candidate.target_id}, '
                f'reason={selection.reason}'
            )
            return

        if not selection.accepted:
            self.get_logger().warning(selection.reason)
            return

        self.get_logger().info(
            'Observation candidate updated: '
            f'class={candidate.event_kind}, target={candidate.target_id}, '
            f'priority={candidate.priority}, pending={selection.pending_count}, '
            f'reason={selection.reason}'
        )
        self._maybe_activate_observation_candidate(candidate)

    def _maybe_activate_observation_candidate(
        self,
        candidate: ObservationTaskCandidate,
    ) -> None:
        active_candidate = self._observation_arbiter.active_candidate
        if (
            active_candidate is not None
            and active_candidate.dedup_key == candidate.dedup_key
        ):
            self._mission_machine.note(
                active_candidate.detail_message,
                target_id=active_candidate.target_id,
            )
            self._publish_status()
            return

        if active_candidate is not None:
            self._mission_machine.note(
                f'Queued {candidate.event_kind} while {active_candidate.event_kind} is active.',
                target_id=active_candidate.target_id,
            )
            self._publish_status()
            return

        if (
            self._mission_machine.mission_type == MissionType.PATROL.value
            and self._mission_machine.mission_state == MissionState.RUNNING.value
        ):
            self._mission_machine.note(
                f'Queued {candidate.event_kind}; requesting patrol stop.',
                target_id=candidate.target_id,
            )
            self._publish_status()
            if self._interrupt_patrol_on_observation:
                if not self._pending_observation_activation_requested:
                    self._pending_observation_activation_requested = True
                    self._request_patrol_control('stop')
            return

        if (
            self._mission_machine.mission_type == MissionType.PATROL.value
            and self._mission_machine.mission_state == MissionState.PAUSED.value
        ):
            self._activate_best_pending_observation(
                'Priority observation activated while patrol is paused.'
            )
            return

        self._activate_best_pending_observation(
            'Priority observation activated from the pending queue.'
        )

    def _activate_best_pending_observation(self, detail_message: str) -> bool:
        candidate = self._observation_arbiter.peek_best_candidate()
        if candidate is None:
            self._pending_observation_activation_requested = False
            return False

        active_candidate = self._observation_arbiter.activate_candidate(
            candidate,
            now_ns=self.get_clock().now().nanoseconds,
        )
        self._pending_observation_activation_requested = False
        self._mission_machine.start_mission(
            active_candidate.mission_type,
            target_id=active_candidate.target_id,
            detail_message=(
                f'{detail_message} '
                f'event={active_candidate.event_kind}, target={active_candidate.target_id}.'
            ),
        )
        self.get_logger().info(
            'Activated observation candidate: '
            f'event={active_candidate.event_kind}, target={active_candidate.target_id}, '
            f'pending={self._observation_arbiter.pending_count()}'
        )
        self._publish_status()
        return True

    def _finish_active_observation_candidate(self) -> None:
        candidate = self._observation_arbiter.complete_active_candidate(
            now_ns=self.get_clock().now().nanoseconds,
        )
        if candidate is None:
            return
        self.get_logger().info(
            'Resolved active observation candidate: '
            f'event={candidate.event_kind}, target={candidate.target_id}'
        )

    def _request_patrol_control(self, operation: str, *, target_id: str = '') -> bool:
        operation = operation.lower()
        client: Client
        if operation == 'start':
            client = self._patrol_start_client
        elif operation == 'stop':
            client = self._patrol_stop_client
        elif operation == 'resume':
            client = self._patrol_resume_client
        else:
            self.get_logger().warning(f'Unsupported patrol control operation: {operation}')
            return False

        if not client.wait_for_service(timeout_sec=self._patrol_service_wait_sec):
            self._mission_machine.note(
                f'Patrol {operation} service is unavailable.',
                target_id=target_id or None,
            )
            if operation == 'stop':
                self._pending_observation_activation_requested = False
            self._publish_status()
            self.get_logger().warning(
                f'Patrol {operation} service is unavailable.'
            )
            return False

        future = client.call_async(Trigger.Request())
        future.add_done_callback(
            lambda result_future, op=operation, target=target_id: self._handle_patrol_control_response(
                result_future,
                op,
                target,
            )
        )
        return True

    def _handle_patrol_control_response(self, future, operation: str, target_id: str) -> None:
        try:
            response = future.result()
        except Exception as exc:
            self._mission_machine.note(
                f'Patrol {operation} request failed: {exc}',
                target_id=target_id or None,
            )
            if operation == 'stop':
                self._pending_observation_activation_requested = False
            self.get_logger().warning(
                f'Patrol {operation} request failed: {exc}'
            )
            self._publish_status()
            return

        if not response.success:
            self._mission_machine.note(
                response.message or f'Patrol {operation} request was rejected.',
                target_id=target_id or None,
            )
            if operation == 'stop':
                self._pending_observation_activation_requested = False
            self.get_logger().warning(
                response.message or f'Patrol {operation} request was rejected.'
            )
            self._publish_status()
            return

        detail_message = response.message or f'Patrol {operation} request accepted.'

        if operation == 'start':
            self._mission_machine.start_mission(
                MissionType.PATROL.value,
                target_id=target_id,
                detail_message=detail_message,
            )
        elif operation == 'stop':
            if self._mission_machine.mission_type == MissionType.PATROL.value:
                self._mission_machine.pause(detail_message=detail_message)
            else:
                self._mission_machine.note(detail_message, target_id=target_id or None)
            if self._pending_observation_activation_requested:
                self._activate_best_pending_observation(
                    'Priority observation activated after patrol stop.'
                )
        elif operation == 'resume':
            if self._mission_machine.mission_type == MissionType.PATROL.value:
                if self._mission_machine.mission_state == MissionState.PAUSED.value:
                    self._mission_machine.resume(detail_message=detail_message)
                else:
                    self._mission_machine.start_mission(
                        MissionType.PATROL.value,
                        target_id=target_id,
                        detail_message=detail_message,
                    )
            else:
                self._mission_machine.note(detail_message, target_id=target_id or None)

        self.get_logger().info(
            f'Patrol {operation} request accepted: {detail_message}'
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
