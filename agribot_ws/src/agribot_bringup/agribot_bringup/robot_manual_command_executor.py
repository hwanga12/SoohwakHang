from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from action_msgs.msg import GoalStatus
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from agribot_navigation.nav_goal_utils import build_latest_pose_stamped
from std_msgs.msg import String
from std_srvs.srv import Trigger

from agribot_navigation.patrol_config import (
    PatrolPlan,
    Pose2D,
    get_default_patrol_waypoints_path,
    load_patrol_plan,
)

from .control_state import (
    ControlMode,
    ControlStateSnapshot,
    MotionActivity,
    ResumeContext,
    ResumeContextType,
    build_control_state_payload,
    iso_now,
)
from .runtime_snapshot_service import (
    DEFAULT_FRAME_ID,
    DEFAULT_MAP_ID,
    build_manual_command_status_payload,
    control_state_path,
    manual_command_path,
    manual_command_status_path,
    read_json_object,
    runtime_dir_from_env,
    write_json_atomic,
)

TERMINAL_STATUSES = {'succeeded', 'failed', 'canceled'}
SUPPORTED_COMMAND_TYPES = {
    'emergency_stop',
    'navigate_to_pose',
    'pause_motion',
    'pause_patrol',
    'resume_motion',
    'resume_patrol',
    'return_home',
}
NAVIGATION_COMMAND_TYPES = {
    'navigate_to_pose',
    'return_home',
}
PAUSE_COMMAND_TYPES = {
    'pause_motion',
    'pause_patrol',
}
RESUME_COMMAND_TYPES = {
    'resume_motion',
    'resume_patrol',
}
PATROL_ACTIVE_STATES = {'starting', 'running', 'observing', 'stopping'}
PATROL_RESUMABLE_STATES = PATROL_ACTIVE_STATES | {'stopped'}
_UNSET = object()


@dataclass(frozen=True)
class PatrolStatusSnapshot:
    state: str
    message: str
    current_waypoint_id: str
    next_waypoint_id: str
    current_waypoint_index: int | None
    next_waypoint_index: int | None
    total_waypoints: int
    active_navigation_kind: str
    active_batch_end_waypoint_id: str
    segment_target_waypoint_id: str

    def as_resume_payload(self) -> dict[str, Any]:
        return {
            'state': self.state,
            'message': self.message,
            'current_waypoint_id': self.current_waypoint_id or None,
            'next_waypoint_id': self.next_waypoint_id or None,
            'current_waypoint_index': self.current_waypoint_index,
            'next_waypoint_index': self.next_waypoint_index,
            'total_waypoints': self.total_waypoints,
            'active_navigation_kind': self.active_navigation_kind or None,
            'active_batch_end_waypoint_id': self.active_batch_end_waypoint_id or None,
            'segment_target_waypoint_id': self.segment_target_waypoint_id or None,
        }


@dataclass(frozen=True)
class CommandPose:
    x: float
    y: float
    z: float
    yaw: float
    frame_id: str

    def as_status_payload(self) -> dict[str, Any]:
        return {
            'x': self.x,
            'y': self.y,
            'z': self.z,
            'yaw': self.yaw,
            'frame_id': self.frame_id,
        }

    def as_pose2d(self) -> Pose2D:
        return Pose2D(x=self.x, y=self.y, z=self.z, yaw=self.yaw)


@dataclass(frozen=True)
class ManualCommand:
    command_id: str
    command_type: str
    robot_id: str
    requested_by: str
    target_pose: CommandPose | None
    home_waypoint_id: str | None
    preempt_current_navigation: bool


@dataclass
class ActiveCommandContext:
    command: ManualCommand
    received_at: str
    started_at: str | None = None
    target_pose: CommandPose | None = None
    home_waypoint_id: str | None = None


class CommandValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        command_id: str | None = None,
        command_type: str | None = None,
        robot_id: str = 'AGR-02',
        requested_by: str = '',
    ) -> None:
        super().__init__(message)
        self.command_id = command_id
        self.command_type = command_type
        self.robot_id = robot_id
        self.requested_by = requested_by


def _iso_now() -> str:
    return iso_now()


def _extract_string(payload: dict[str, Any], key: str, *, default: str = '') -> str:
    raw_value = payload.get(key, default)
    return str(raw_value).strip() if raw_value is not None else default


def _extract_optional_bool(payload: dict[str, Any], key: str) -> bool | None:
    if key not in payload:
        return None

    raw_value = payload.get(key)
    if raw_value is None:
        return None
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, (int, float)):
        if raw_value in {0, 1}:
            return bool(raw_value)
        raise ValueError(f'{key} 는 bool 이어야 합니다.')
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {'true', '1', 'yes', 'y', 'on'}:
            return True
        if normalized in {'false', '0', 'no', 'n', 'off'}:
            return False
    raise ValueError(f'{key} 는 bool 이어야 합니다.')


def _coerce_pose(payload: dict[str, Any], default_frame: str) -> CommandPose:
    required_fields = {'x', 'y', 'yaw'}
    missing = sorted(field for field in required_fields if field not in payload)
    if missing:
        raise ValueError(f'pose payload is missing fields: {missing}')

    frame_id = str(payload.get('frame_id', default_frame)).strip() or default_frame
    return CommandPose(
        x=float(payload['x']),
        y=float(payload['y']),
        z=float(payload.get('z', 0.0)),
        yaw=float(payload['yaw']),
        frame_id=frame_id,
    )


def _extract_target_pose(raw_payload: dict[str, Any], default_frame: str) -> CommandPose:
    payload_candidates: list[dict[str, Any]] = []
    nested_payload = raw_payload.get('payload')
    if isinstance(nested_payload, dict):
        payload_candidates.append(nested_payload)
    payload_candidates.append(raw_payload)

    for candidate in payload_candidates:
        for key in ('target_pose', 'pose'):
            nested_pose = candidate.get(key)
            if isinstance(nested_pose, dict):
                return _coerce_pose(nested_pose, default_frame)
        if any(field in candidate for field in ('x', 'y', 'yaw')):
            return _coerce_pose(candidate, default_frame)

    raise ValueError('navigate_to_pose 명령에는 map frame x, y, yaw가 필요합니다.')


def describe_manual_navigation_label(command_type: str, home_waypoint_id: str | None = None) -> str:
    if command_type == 'return_home':
        if home_waypoint_id:
            return f'홈 복귀({home_waypoint_id})'
        return '홈 복귀'
    return '수동 목표점'


def should_retry_goal_rejection(retry_count: int, retry_limit: int) -> bool:
    return retry_limit > 0 and retry_count < retry_limit


def is_navigation_command_type(command_type: str) -> bool:
    return command_type in NAVIGATION_COMMAND_TYPES


def is_pause_command_type(command_type: str) -> bool:
    return command_type in PAUSE_COMMAND_TYPES


def is_resume_command_type(command_type: str) -> bool:
    return command_type in RESUME_COMMAND_TYPES


def parse_patrol_status_payload(raw_data: str) -> PatrolStatusSnapshot | None:
    try:
        payload = json.loads(raw_data)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    total_waypoints = payload.get('total_waypoints', 0)
    current_waypoint_index = payload.get('current_waypoint_index')
    next_waypoint_index = payload.get('next_waypoint_index')
    try:
        total_waypoints = int(total_waypoints or 0)
        if current_waypoint_index is not None:
            current_waypoint_index = int(current_waypoint_index)
        if next_waypoint_index is not None:
            next_waypoint_index = int(next_waypoint_index)
    except (TypeError, ValueError):
        return None

    return PatrolStatusSnapshot(
        state=str(payload.get('state', '')).strip().lower(),
        message=str(payload.get('message', '')),
        current_waypoint_id=str(payload.get('current_waypoint_id') or ''),
        next_waypoint_id=str(payload.get('next_waypoint_id') or ''),
        current_waypoint_index=current_waypoint_index,
        next_waypoint_index=next_waypoint_index,
        total_waypoints=max(0, total_waypoints),
        active_navigation_kind=str(payload.get('active_navigation_kind') or ''),
        active_batch_end_waypoint_id=str(payload.get('active_batch_end_waypoint_id') or ''),
        segment_target_waypoint_id=str(payload.get('segment_target_waypoint_id') or ''),
    )


def build_patrol_resume_context(
    patrol_status: PatrolStatusSnapshot | None,
    *,
    captured_at: str | None = None,
) -> ResumeContext | None:
    if patrol_status is None or patrol_status.state not in PATROL_RESUMABLE_STATES:
        return None

    total_waypoints = max(0, patrol_status.total_waypoints)
    if total_waypoints == 0:
        return None

    next_waypoint_index = patrol_status.next_waypoint_index
    if next_waypoint_index is None or next_waypoint_index >= total_waypoints:
        return None

    return ResumeContext(
        context_type=ResumeContextType.PATROL,
        captured_at=captured_at or _iso_now(),
        patrol_snapshot=patrol_status.as_resume_payload(),
    )


def describe_resume_context(resume_context: ResumeContext | None) -> str:
    if resume_context is None:
        return '저장된 재개 문맥 없음'
    if resume_context.context_type is ResumeContextType.PATROL:
        next_waypoint_id = ''
        if resume_context.patrol_snapshot is not None:
            next_waypoint_id = str(resume_context.patrol_snapshot.get('next_waypoint_id') or '')
        return f'순찰({next_waypoint_id or "다음 waypoint 미상"})'
    if resume_context.home_waypoint_id:
        return f'수동 이동({resume_context.command_type}:{resume_context.home_waypoint_id})'
    return f'수동 이동({resume_context.command_type or "navigate_to_pose"})'


def should_block_command_for_control_mode(
    mode: ControlMode,
    command_type: str,
) -> bool:
    if not mode.is_latched:
        return False
    return command_type not in {'emergency_stop', 'resume_motion', 'resume_patrol'}

def resolve_preempt_current_navigation(
    command_type: str,
    *,
    raw_payload: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    explicit_value = _extract_optional_bool(raw_payload, 'preempt_current_navigation')
    if explicit_value is not None:
        return explicit_value

    payload_value = _extract_optional_bool(payload, 'preempt_current_navigation')
    if payload_value is not None:
        return payload_value

    return is_navigation_command_type(command_type)


def parse_manual_command_payload(
    raw_payload: dict[str, Any],
    *,
    default_robot_id: str = 'AGR-02',
    default_frame: str = DEFAULT_FRAME_ID,
) -> ManualCommand:
    robot_id = _extract_string(raw_payload, 'robot_id', default=default_robot_id) or default_robot_id
    requested_by = _extract_string(raw_payload, 'requested_by')
    command_id = _extract_string(raw_payload, 'command_id')
    command_type = _extract_string(raw_payload, 'command_type')

    if not command_id:
        raise CommandValidationError(
            'robot_manual_command.json에 command_id가 없습니다.',
            command_type=command_type or None,
            robot_id=robot_id,
            requested_by=requested_by,
        )

    if command_type not in SUPPORTED_COMMAND_TYPES:
        raise CommandValidationError(
            f'지원하지 않는 command_type 입니다: {command_type!r}',
            command_id=command_id,
            command_type=command_type or None,
            robot_id=robot_id,
            requested_by=requested_by,
        )

    payload = raw_payload.get('payload', {})
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise CommandValidationError(
            'payload는 JSON object여야 합니다.',
            command_id=command_id,
            command_type=command_type,
            robot_id=robot_id,
            requested_by=requested_by,
        )

    try:
        target_pose = (
            _extract_target_pose(raw_payload, default_frame)
            if command_type == 'navigate_to_pose'
            else None
        )
        preempt_current_navigation = resolve_preempt_current_navigation(
            command_type,
            raw_payload=raw_payload,
            payload=payload,
        )
    except ValueError as exc:
        raise CommandValidationError(
            str(exc),
            command_id=command_id,
            command_type=command_type,
            robot_id=robot_id,
            requested_by=requested_by,
        ) from exc

    home_waypoint_id = _extract_string(payload, 'home_waypoint_id') or _extract_string(
        raw_payload,
        'home_waypoint_id',
    )

    return ManualCommand(
        command_id=command_id,
        command_type=command_type,
        robot_id=robot_id,
        requested_by=requested_by,
        target_pose=target_pose,
        home_waypoint_id=home_waypoint_id or None,
        preempt_current_navigation=preempt_current_navigation,
    )


def resolve_return_home_target(
    command: ManualCommand,
    plan: PatrolPlan,
) -> tuple[str, CommandPose]:
    waypoint_id = command.home_waypoint_id or plan.home_pose_id
    if waypoint_id not in plan.waypoints:
        raise ValueError(f'홈 복귀 waypoint를 찾지 못했습니다: {waypoint_id}')

    waypoint = plan.waypoints[waypoint_id]
    return (
        waypoint_id,
        CommandPose(
            x=waypoint.pose.x,
            y=waypoint.pose.y,
            z=waypoint.pose.z,
            yaw=waypoint.pose.yaw,
            frame_id=plan.frame_id,
        ),
    )


def build_manual_resume_context(
    context: ActiveCommandContext,
    *,
    captured_at: str | None = None,
) -> ResumeContext | None:
    if context.target_pose is None:
        return None

    command_type = context.command.command_type
    if command_type not in NAVIGATION_COMMAND_TYPES and command_type not in RESUME_COMMAND_TYPES:
        return None

    return ResumeContext(
        context_type=ResumeContextType.MANUAL_NAVIGATION,
        captured_at=captured_at or _iso_now(),
        command_id=context.command.command_id,
        command_type=command_type,
        target_pose=context.target_pose.as_status_payload(),
        home_waypoint_id=context.home_waypoint_id,
    )


def context_has_navigation_target(context: ActiveCommandContext | None) -> bool:
    return context is not None and context.target_pose is not None


class RobotManualCommandExecutor(Node):
    def __init__(self) -> None:
        super().__init__('robot_manual_command_executor')

        if not self.has_parameter('use_sim_time'):
            self.declare_parameter('use_sim_time', True)
        self.declare_parameter('map_id', DEFAULT_MAP_ID)
        self.declare_parameter('robot_id', 'AGR-02')
        self.declare_parameter('map_frame', DEFAULT_FRAME_ID)
        self.declare_parameter('navigate_to_pose_action', 'navigate_to_pose')
        self.declare_parameter('patrol_status_topic', '/patrol/status')
        self.declare_parameter('patrol_stop_service', '/patrol/stop')
        self.declare_parameter('patrol_resume_service', '/patrol/resume')
        self.declare_parameter('control_state_topic', '/robot/control_state')
        self.declare_parameter('nav_server_wait_sec', 5.0)
        self.declare_parameter('patrol_service_wait_sec', 1.0)
        self.declare_parameter('goal_reject_retry_sec', 0.75)
        self.declare_parameter('goal_reject_retry_limit', 4)
        self.declare_parameter(
            'patrol_waypoints_file',
            str(get_default_patrol_waypoints_path()),
        )
        self.declare_parameter('command_poll_period_sec', 0.25)
        self.declare_parameter('processed_command_history_size', 64)

        self._runtime_dir = runtime_dir_from_env()
        self._command_path = manual_command_path(self._runtime_dir)
        self._status_path = manual_command_status_path(self._runtime_dir)
        self._control_state_path = control_state_path(self._runtime_dir)
        self._map_id = str(self.get_parameter('map_id').value)
        self._default_robot_id = str(self.get_parameter('robot_id').value)
        self._map_frame = str(self.get_parameter('map_frame').value)
        self._action_name = str(self.get_parameter('navigate_to_pose_action').value)
        self._patrol_status_topic = str(self.get_parameter('patrol_status_topic').value)
        self._control_state_topic = str(self.get_parameter('control_state_topic').value)
        self._nav_server_wait_sec = float(self.get_parameter('nav_server_wait_sec').value)
        self._patrol_service_wait_sec = float(self.get_parameter('patrol_service_wait_sec').value)
        self._goal_reject_retry_sec = max(0.0, float(self.get_parameter('goal_reject_retry_sec').value))
        self._goal_reject_retry_limit = max(0, int(self.get_parameter('goal_reject_retry_limit').value))
        history_size = max(8, int(self.get_parameter('processed_command_history_size').value))

        self._plan = self._load_patrol_plan()
        self._navigate_client = ActionClient(self, NavigateToPose, self._action_name)
        self._patrol_stop_client = self.create_client(
            Trigger,
            str(self.get_parameter('patrol_stop_service').value),
        )
        self._patrol_resume_client = self.create_client(
            Trigger,
            str(self.get_parameter('patrol_resume_service').value),
        )
        self._patrol_status_subscription = self.create_subscription(
            String,
            self._patrol_status_topic,
            self._handle_patrol_status,
            20,
        )
        self._control_state_publisher = self.create_publisher(
            String,
            self._control_state_topic,
            10,
        )

        self._processed_command_ids: set[str] = set()
        self._processed_command_order: deque[str] = deque(maxlen=history_size)
        self._active_context: ActiveCommandContext | None = None
        self._active_goal_handle = None
        self._goal_send_future = None
        self._goal_result_future = None
        self._goal_cancel_future = None
        self._goal_retry_timer = None
        self._goal_reject_retry_count = 0
        self._service_future = None
        self._pending_context: ActiveCommandContext | None = None
        self._last_status_payload: dict[str, Any] | None = None
        self._last_seen_command_signature: tuple[int, int] | None = None
        self._latest_patrol_status: PatrolStatusSnapshot | None = None
        self._patrol_state_wait: dict[str, Any] | None = None
        self._navigation_cancel_reason = ''
        self._resume_release_pending = False
        self._control_state = ControlStateSnapshot(
            mode=ControlMode.NORMAL,
            active_activity=MotionActivity.IDLE,
            updated_at=_iso_now(),
        )

        self._recover_previous_control_state()
        self._recover_previous_command_status()
        self._write_control_state()
        poll_period = float(self.get_parameter('command_poll_period_sec').value)
        self.create_timer(poll_period, self._poll_command_file)

        self.get_logger().info(
            'robot manual command executor started. '
            f'command_path={self._command_path}, '
            f'control_state_topic={self._control_state_topic}'
        )

    def _load_patrol_plan(self) -> PatrolPlan:
        plan_path = Path(str(self.get_parameter('patrol_waypoints_file').value)).expanduser()
        if not plan_path.is_absolute():
            plan_path = get_default_patrol_waypoints_path().parent.parent / plan_path
        return load_patrol_plan(plan_path)

    def _recover_previous_control_state(self) -> None:
        if not self._control_state_path.exists():
            return

        try:
            payload = read_json_object(self._control_state_path)
        except (OSError, ValueError) as exc:
            self.get_logger().warning(f'기존 control state 파일을 읽지 못했습니다: {exc}')
            return

        self._control_state = ControlStateSnapshot.from_payload(payload)

    def _derive_active_activity(self) -> MotionActivity:
        if context_has_navigation_target(self._active_context):
            return MotionActivity.MANUAL_NAVIGATION
        if (
            self._goal_retry_timer is not None
            and context_has_navigation_target(self._active_context)
        ):
            return MotionActivity.MANUAL_NAVIGATION
        if self._latest_patrol_status is not None and self._latest_patrol_status.state in PATROL_ACTIVE_STATES:
            return MotionActivity.PATROL
        return MotionActivity.IDLE

    def _update_control_state(
        self,
        *,
        mode: ControlMode | None = None,
        blocking_reason: str | None = None,
        message: str | None = None,
        resume_context: ResumeContext | None | object = _UNSET,
    ) -> None:
        if resume_context is _UNSET:
            next_resume_context = self._control_state.resume_context
        else:
            next_resume_context = resume_context

        self._control_state = ControlStateSnapshot(
            mode=mode or self._control_state.mode,
            active_activity=self._derive_active_activity(),
            blocking_reason=(
                self._control_state.blocking_reason
                if blocking_reason is None
                else blocking_reason
            ),
            message=self._control_state.message if message is None else message,
            resume_context=next_resume_context,
            updated_at=_iso_now(),
        )
        self._write_control_state()

    def _set_control_latch(
        self,
        *,
        mode: ControlMode,
        blocking_reason: str,
        message: str,
        resume_context: ResumeContext | None,
    ) -> None:
        self._control_state = ControlStateSnapshot(
            mode=mode,
            active_activity=self._derive_active_activity(),
            blocking_reason=blocking_reason,
            message=message,
            resume_context=resume_context,
            updated_at=_iso_now(),
        )
        self._write_control_state()

    def _clear_control_latch(self, *, message: str) -> None:
        self._control_state = ControlStateSnapshot(
            mode=ControlMode.NORMAL,
            active_activity=self._derive_active_activity(),
            blocking_reason='',
            message=message,
            resume_context=None,
            updated_at=_iso_now(),
        )
        self._write_control_state()

    def _write_control_state(self) -> None:
        payload = build_control_state_payload(
            mode=self._control_state.mode,
            active_activity=self._derive_active_activity(),
            blocking_reason=self._control_state.blocking_reason,
            message=self._control_state.message,
            resume_context=self._control_state.resume_context,
            updated_at=_iso_now(),
        )
        self._control_state = ControlStateSnapshot.from_payload(payload)
        write_json_atomic(self._control_state_path, payload)
        self._control_state_publisher.publish(String(data=json.dumps(payload, sort_keys=True)))

    def _resume_context(self) -> ResumeContext | None:
        return self._control_state.resume_context

    def _is_patrol_resumable(self) -> bool:
        return build_patrol_resume_context(self._latest_patrol_status) is not None

    def _recover_previous_command_status(self) -> None:
        if not self._status_path.exists():
            return

        try:
            payload = read_json_object(self._status_path)
        except (OSError, ValueError) as exc:
            self.get_logger().warning(f'기존 command status 파일을 읽지 못했습니다: {exc}')
            return

        self._last_status_payload = payload
        command_id = _extract_string(payload, 'command_id')
        status = _extract_string(payload, 'status')
        if not command_id:
            return

        if status in TERMINAL_STATUSES:
            self._remember_processed_command_id(command_id)
            return

        repaired_payload = build_manual_command_status_payload(
            command_id=command_id,
            command_type=_extract_string(payload, 'command_type') or None,
            robot_id=_extract_string(payload, 'robot_id', default=self._default_robot_id),
            requested_by=_extract_string(payload, 'requested_by'),
            map_id=_extract_string(payload, 'map_id', default=self._map_id) or self._map_id,
            frame_id=_extract_string(payload, 'frame_id', default=self._map_frame) or self._map_frame,
            status='failed',
            message='이전 executor 세션이 명령 완료 전에 종료되었습니다. 새 command_id로 다시 요청하세요.',
            error='executor_restart',
            target_pose=payload.get('target_pose') if isinstance(payload.get('target_pose'), dict) else None,
            home_waypoint_id=_extract_string(payload, 'home_waypoint_id') or None,
            received_at=_extract_string(payload, 'received_at') or None,
            started_at=_extract_string(payload, 'started_at') or None,
            completed_at=_iso_now(),
        )
        write_json_atomic(self._status_path, repaired_payload)
        self._last_status_payload = repaired_payload
        self._remember_processed_command_id(command_id)

    def _remember_processed_command_id(self, command_id: str) -> None:
        if command_id in self._processed_command_ids:
            return

        if len(self._processed_command_order) == self._processed_command_order.maxlen:
            oldest = self._processed_command_order.popleft()
            self._processed_command_ids.discard(oldest)

        self._processed_command_order.append(command_id)
        self._processed_command_ids.add(command_id)

    def _handle_patrol_status(self, msg: String) -> None:
        snapshot = parse_patrol_status_payload(msg.data)
        if snapshot is None:
            self.get_logger().warning('유효하지 않은 patrol status payload를 무시합니다.')
            return

        self._latest_patrol_status = snapshot
        if (
            self._control_state.mode is ControlMode.NORMAL
            and self._control_state.resume_context is not None
            and self._control_state.resume_context.context_type is ResumeContextType.PATROL
            and snapshot.state not in PATROL_RESUMABLE_STATES
        ):
            self._update_control_state(resume_context=None)
        else:
            self._update_control_state()
        self._maybe_finish_patrol_state_wait(snapshot)

    def _maybe_finish_patrol_state_wait(self, snapshot: PatrolStatusSnapshot) -> None:
        if self._patrol_state_wait is None or self._active_context is None:
            return

        command_id = str(self._patrol_state_wait.get('command_id') or '')
        if self._active_context.command.command_id != command_id:
            return

        success_states = set(self._patrol_state_wait.get('success_states') or ())
        failure_states = set(self._patrol_state_wait.get('failure_states') or ())
        if snapshot.state in failure_states:
            self._patrol_state_wait = None
            self._finish_active_command(
                'failed',
                self._patrol_state_wait_failure_message(),
                error='patrol_state_transition_failed',
            )
            return

        if snapshot.state not in success_states:
            return

        success_message = str(self._patrol_state_wait.get('success_message') or '순찰 상태 전환이 확인되었습니다.')
        clear_latch = bool(self._patrol_state_wait.get('clear_latch'))
        no_op = bool(self._patrol_state_wait.get('no_op'))
        self._patrol_state_wait = None
        if clear_latch:
            self._clear_control_latch(message=success_message)
        else:
            self._update_control_state(message=success_message)
        self._finish_active_command(
            'succeeded',
            success_message,
            result='no_op' if no_op else 'executed',
        )

    def _patrol_state_wait_failure_message(self) -> str:
        if self._latest_patrol_status is None or not self._latest_patrol_status.message:
            return '순찰 상태 전환이 실패했습니다.'
        return self._latest_patrol_status.message

    def _poll_command_file(self) -> None:
        if not self._command_path.exists():
            return

        signature = self._command_file_signature(self._command_path)
        if signature == self._last_seen_command_signature:
            return
        self._last_seen_command_signature = signature

        try:
            raw_payload = read_json_object(self._command_path)
            command = parse_manual_command_payload(
                raw_payload,
                default_robot_id=self._default_robot_id,
                default_frame=self._map_frame,
            )
        except CommandValidationError as exc:
            self._handle_invalid_command(exc)
            return
        except (OSError, ValueError) as exc:
            self._write_status(
                build_manual_command_status_payload(
                    command_id=None,
                    command_type=None,
                    robot_id=self._default_robot_id,
                    status='failed',
                    message=f'명령 파일을 해석하지 못했습니다: {exc}',
                    error='invalid_command_payload',
                    map_id=self._map_id,
                    frame_id=self._map_frame,
                    completed_at=_iso_now(),
                )
            )
            return

        if command.command_id in self._processed_command_ids:
            if not (
                self._last_status_payload
                and self._last_status_payload.get('command_id') == command.command_id
                and self._last_status_payload.get('status') in TERMINAL_STATUSES
            ):
                self._write_status(
                    build_manual_command_status_payload(
                        command_id=command.command_id,
                        command_type=command.command_type,
                        robot_id=command.robot_id,
                        requested_by=command.requested_by,
                        map_id=self._map_id,
                        frame_id=self._map_frame,
                        status='failed',
                        message='이미 처리된 command_id 입니다. 새 command_id로 다시 요청하세요.',
                        error='duplicate_command_id',
                        target_pose=(
                            command.target_pose.as_status_payload()
                            if command.target_pose is not None
                            else None
                        ),
                        home_waypoint_id=command.home_waypoint_id,
                        completed_at=_iso_now(),
                    )
                )
            return

        if should_block_command_for_control_mode(self._control_state.mode, command.command_type):
            self._remember_processed_command_id(command.command_id)
            self._write_status(
                self._build_non_active_command_status_payload(
                    command,
                    'failed',
                    (
                        '현재 제어 상태가 '
                        f'{self._control_state.mode.value} 이라 새 이동 명령을 거부했습니다. '
                        'resume_motion 으로 먼저 해제하세요.'
                    ),
                    error='control_state_blocked',
                    completed_at=_iso_now(),
                )
            )
            return

        if self._active_context is not None:
            self._handle_command_while_active(command)
            return

        self._start_command(command)

    def _command_file_signature(self, path: Path) -> tuple[int, int]:
        stat_result = path.stat()
        return stat_result.st_mtime_ns, stat_result.st_size

    def _handle_invalid_command(self, exc: CommandValidationError) -> None:
        if exc.command_id:
            self._remember_processed_command_id(exc.command_id)
        self._write_status(
            build_manual_command_status_payload(
                command_id=exc.command_id,
                command_type=exc.command_type,
                robot_id=exc.robot_id,
                requested_by=exc.requested_by,
                map_id=self._map_id,
                frame_id=self._map_frame,
                status='failed',
                message=str(exc),
                error='invalid_command_payload',
                completed_at=_iso_now(),
            )
        )

    def _build_non_active_command_status_payload(
        self,
        command: ManualCommand,
        status: str,
        message: str,
        *,
        error: str | None = None,
        result: str | None = None,
        received_at: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        frame_id = command.target_pose.frame_id if command.target_pose is not None else self._map_frame
        return build_manual_command_status_payload(
            command_id=command.command_id,
            command_type=command.command_type,
            robot_id=command.robot_id,
            requested_by=command.requested_by,
            map_id=self._map_id,
            frame_id=frame_id,
            status=status,
            message=message,
            error=error,
            result=result,
            target_pose=(
                command.target_pose.as_status_payload()
                if command.target_pose is not None
                else None
            ),
            home_waypoint_id=command.home_waypoint_id,
            control_state=self._control_state.as_payload(),
            received_at=received_at,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _build_pending_context(self, command: ManualCommand) -> ActiveCommandContext:
        return ActiveCommandContext(
            command=command,
            received_at=_iso_now(),
            target_pose=command.target_pose,
            home_waypoint_id=command.home_waypoint_id,
        )

    def _handle_command_while_active(self, command: ManualCommand) -> None:
        active_context = self._active_context
        if active_context is None:
            self._start_command(command)
            return

        if command.command_id == active_context.command.command_id:
            return

        if command.command_type == 'emergency_stop':
            self._request_control_interruption(command, mode=ControlMode.EMERGENCY_STOP)
            return

        if is_pause_command_type(command.command_type):
            if command.command_type == 'pause_patrol' and not self._is_patrol_resumable():
                self._remember_processed_command_id(command.command_id)
                self._write_status(
                    self._build_non_active_command_status_payload(
                        command,
                        'failed',
                        '현재 재개 가능한 순찰 문맥이 없어 pause_patrol 을 적용할 수 없습니다.',
                        error='patrol_not_active',
                        completed_at=_iso_now(),
                    )
                )
                return
            self._request_control_interruption(command, mode=ControlMode.PAUSED)
            return

        if is_navigation_command_type(command.command_type) and command.preempt_current_navigation:
            self._request_navigation_preemption(command)
            return

        message = '현재 다른 명령이 실행 중이라 새 명령을 즉시 처리할 수 없습니다.'
        if is_navigation_command_type(command.command_type):
            message += ' 이동 명령은 preempt_current_navigation=true 로 다시 요청하세요.'
        self._remember_processed_command_id(command.command_id)
        self._write_status(
            self._build_non_active_command_status_payload(
                command,
                'failed',
                message,
                error='active_command_in_progress',
                completed_at=_iso_now(),
            )
        )

    def _request_navigation_preemption(self, command: ManualCommand) -> None:
        pending_context = self._build_pending_context(command)
        self._pending_context = pending_context
        self._write_status(
            self._build_status_payload(
                pending_context,
                'pending',
                '새 이동 명령을 수락했습니다. 현재 주행을 중단하고 목표를 선점 전환하는 중입니다.',
            )
        )

        if self._active_context is None:
            self._start_pending_command()
            return

        if self._goal_retry_timer is not None and self._active_goal_handle is None and self._goal_send_future is None:
            self._cancel_goal_retry_timer()
            self._finish_active_command(
                'canceled',
                '새 이동 명령이 들어와 기존 재시도를 중단했습니다.',
                error='preempted_by_new_command',
            )
            return

        if self._active_goal_handle is not None:
            self._request_active_goal_cancel_for_preemption()
            return

        if self._goal_send_future is not None or self._service_future is not None:
            self.get_logger().info(
                '새 이동 명령을 대기열에 올렸습니다. 현재 비동기 작업이 끝나는 즉시 선점 전환합니다.'
            )
            return

        self._finish_active_command(
            'canceled',
            '새 이동 명령이 들어와 기존 명령을 중단했습니다.',
            error='preempted_by_new_command',
        )

    def _build_resume_context_for_interruption(
        self,
        command_type: str,
        *,
        captured_at: str | None = None,
    ) -> ResumeContext | None:
        if context_has_navigation_target(self._active_context):
            return build_manual_resume_context(
                self._active_context,
                captured_at=captured_at,
            )
        if command_type == 'pause_patrol':
            return build_patrol_resume_context(
                self._latest_patrol_status,
                captured_at=captured_at,
            )
        return build_patrol_resume_context(
            self._latest_patrol_status,
            captured_at=captured_at,
        )

    def _request_control_interruption(
        self,
        command: ManualCommand,
        *,
        mode: ControlMode,
    ) -> None:
        pending_context = self._build_pending_context(command)
        self._pending_context = pending_context
        captured_at = _iso_now()
        resume_context = self._build_resume_context_for_interruption(
            command.command_type,
            captured_at=captured_at,
        )

        if mode is ControlMode.EMERGENCY_STOP:
            self._set_control_latch(
                mode=ControlMode.EMERGENCY_STOP,
                blocking_reason='emergency_stop',
                message='비상 정지가 활성화되었습니다. resume_motion 전까지 새 이동을 거부합니다.',
                resume_context=resume_context,
            )
            pending_message = '비상 정지를 적용하기 위해 현재 이동을 즉시 중단하는 중입니다.'
            cancel_error = 'emergency_stopped'
            cancel_message = '비상 정지 명령으로 현재 이동을 즉시 중단했습니다.'
        else:
            self._set_control_latch(
                mode=ControlMode.PAUSED,
                blocking_reason=command.command_type,
                message='일시정지가 활성화되었습니다. 저장된 문맥이 있으면 resume_motion 으로 재개할 수 있습니다.',
                resume_context=resume_context,
            )
            pending_message = '일시정지를 적용하기 위해 현재 이동을 중단하는 중입니다.'
            cancel_error = 'paused_by_control_command'
            cancel_message = '일시정지 명령으로 현재 이동을 중단했습니다.'

        self._write_status(
            self._build_status_payload(
                pending_context,
                'pending',
                pending_message,
            )
        )

        if (
            self._goal_retry_timer is not None
            and self._active_goal_handle is None
            and self._goal_send_future is None
        ):
            self._cancel_goal_retry_timer()
            self._finish_active_command(
                'canceled',
                cancel_message,
                error=cancel_error,
            )
            return

        self._navigation_cancel_reason = cancel_error
        if self._active_goal_handle is not None:
            self._request_active_goal_cancel_for_preemption()
            return

        if self._goal_send_future is not None or self._service_future is not None:
            self.get_logger().info(
                '제어 상태 전환 명령을 대기열에 올렸습니다. 현재 비동기 작업이 끝나는 즉시 적용합니다.'
            )
            return

        self._finish_active_command(
            'canceled',
            cancel_message,
            error=cancel_error,
        )

    def _start_pending_command(self) -> None:
        pending_context = self._pending_context
        if pending_context is None:
            return
        self._pending_context = None
        self._start_command(pending_context.command, context=pending_context)

    def _start_command(
        self,
        command: ManualCommand,
        *,
        context: ActiveCommandContext | None = None,
    ) -> None:
        context = context or self._build_pending_context(command)
        self._active_context = context
        self._write_status(self._build_status_payload(context, 'pending', '명령을 수락했습니다.'))

        if command.command_type == 'emergency_stop':
            self._start_emergency_stop_command(context)
            return

        if command.command_type in {'pause_motion', 'pause_patrol'}:
            self._start_pause_command(context)
            return

        if command.command_type in {'resume_motion', 'resume_patrol'}:
            self._start_resume_command(context)
            return

        if command.command_type == 'navigate_to_pose':
            self._start_navigation_command(
                context,
                target_pose=command.target_pose,
                label=describe_manual_navigation_label(command.command_type),
            )
            return

        if command.command_type == 'return_home':
            try:
                home_waypoint_id, target_pose = resolve_return_home_target(command, self._plan)
            except ValueError as exc:
                self._finish_active_command('failed', str(exc), error='home_waypoint_not_found')
                return
            context.home_waypoint_id = home_waypoint_id
            self._start_navigation_command(
                context,
                target_pose=target_pose,
                label=describe_manual_navigation_label(command.command_type, home_waypoint_id),
            )
            return

        self._finish_active_command(
            'failed',
            f'지원하지 않는 command_type 입니다: {command.command_type}',
            error='unsupported_command_type',
        )

    def _start_emergency_stop_command(self, context: ActiveCommandContext) -> None:
        context.started_at = context.started_at or _iso_now()
        resume_context = self._resume_context() or self._build_resume_context_for_interruption(
            context.command.command_type,
            captured_at=context.started_at,
        )
        self._set_control_latch(
            mode=ControlMode.EMERGENCY_STOP,
            blocking_reason='emergency_stop',
            message='비상 정지가 활성화되었습니다. resume_motion 전까지 새 이동을 거부합니다.',
            resume_context=resume_context,
        )
        if self._latest_patrol_status is not None and self._latest_patrol_status.state in PATROL_ACTIVE_STATES:
            self._call_patrol_service_and_wait(
                context,
                self._patrol_stop_client,
                action_label='비상 정지 순찰 정지',
                request_message='비상 정지로 순찰을 정지하는 중입니다.',
                success_states={'stopped'},
                failure_states={'error'},
                success_message='비상 정지가 활성화되었고 순찰이 실제로 정지했습니다.',
            )
            return

        self._finish_active_command(
            'succeeded',
            '비상 정지가 활성화되었습니다.',
            result='executed',
        )

    def _start_pause_command(self, context: ActiveCommandContext) -> None:
        context.started_at = context.started_at or _iso_now()
        if context.command.command_type == 'pause_patrol' and not self._is_patrol_resumable():
            self._finish_active_command(
                'failed',
                '현재 재개 가능한 순찰 문맥이 없어 pause_patrol 을 적용할 수 없습니다.',
                error='patrol_not_active',
            )
            return

        resume_context = self._resume_context() or self._build_resume_context_for_interruption(
            context.command.command_type,
            captured_at=context.started_at,
        )
        self._set_control_latch(
            mode=ControlMode.PAUSED,
            blocking_reason=context.command.command_type,
            message='일시정지가 활성화되었습니다. 저장된 문맥이 있으면 resume_motion 으로 재개할 수 있습니다.',
            resume_context=resume_context,
        )
        if self._latest_patrol_status is not None and self._latest_patrol_status.state in PATROL_ACTIVE_STATES:
            self._call_patrol_service_and_wait(
                context,
                self._patrol_stop_client,
                action_label='순찰 일시정지',
                request_message='일시정지를 적용하기 위해 순찰 정지를 기다리는 중입니다.',
                success_states={'stopped'},
                failure_states={'error'},
                success_message='일시정지가 활성화되었고 순찰이 실제로 정지했습니다.',
            )
            return

        self._finish_active_command(
            'succeeded',
            '일시정지가 활성화되었습니다.',
            result='executed',
        )

    def _start_resume_command(self, context: ActiveCommandContext) -> None:
        context.started_at = context.started_at or _iso_now()
        resume_context = self._resume_context()
        if self._control_state.mode is ControlMode.NORMAL and context.command.command_type == 'resume_patrol':
            self._call_patrol_service_and_wait(
                context,
                self._patrol_resume_client,
                action_label='순찰 재개',
                request_message='순찰 재개를 기다리는 중입니다.',
                success_states=PATROL_ACTIVE_STATES,
                failure_states={'error'},
                success_message='순찰 재개가 실제로 시작되었습니다.',
            )
            return

        if self._control_state.mode is ControlMode.NORMAL:
            self._finish_active_command(
                'succeeded',
                '현재 제어 latch가 없어 추가로 재개할 동작이 없습니다.',
                result='no_op',
            )
            return

        if resume_context is None:
            self._clear_control_latch(message='저장된 재개 문맥 없이 제어 latch만 해제했습니다.')
            self._finish_active_command(
                'succeeded',
                '저장된 재개 문맥이 없어 제어 latch만 해제했습니다.',
                result='no_op',
            )
            return

        if (
            context.command.command_type == 'resume_patrol'
            and resume_context.context_type is ResumeContextType.MANUAL_NAVIGATION
        ):
            self._finish_active_command(
                'failed',
                '저장된 재개 문맥이 수동 이동이라 resume_patrol 로는 재개할 수 없습니다.',
                error='resume_context_mismatch',
            )
            return

        if resume_context.context_type is ResumeContextType.PATROL:
            self._call_patrol_service_and_wait(
                context,
                self._patrol_resume_client,
                action_label='저장된 순찰 재개',
                request_message='저장된 순찰 문맥을 재개하는 중입니다.',
                success_states=PATROL_ACTIVE_STATES,
                failure_states={'error'},
                success_message='저장된 순찰 문맥을 재개했습니다.',
                clear_latch=True,
            )
            return

        if resume_context.target_pose is None:
            self._finish_active_command(
                'failed',
                '저장된 수동 이동 재개 문맥에 target_pose 가 없습니다.',
                error='missing_resume_target_pose',
            )
            return

        context.home_waypoint_id = resume_context.home_waypoint_id
        context.target_pose = _coerce_pose(resume_context.target_pose, self._map_frame)
        self._resume_release_pending = True
        self._start_navigation_command(
            context,
            target_pose=context.target_pose,
            label='저장된 수동 이동 재개',
        )

    def _call_patrol_service_and_wait(
        self,
        context: ActiveCommandContext,
        client,
        *,
        action_label: str,
        request_message: str,
        success_states: set[str],
        failure_states: set[str],
        success_message: str,
        clear_latch: bool = False,
    ) -> None:
        if not client.wait_for_service(timeout_sec=self._patrol_service_wait_sec):
            self._finish_active_command(
                'failed',
                f'{action_label} 서비스가 준비되지 않았습니다.',
                error='patrol_service_unavailable',
            )
            return

        self._write_status(
            self._build_status_payload(
                context,
                'running',
                request_message,
            )
        )
        self._patrol_state_wait = {
            'command_id': context.command.command_id,
            'success_states': tuple(success_states),
            'failure_states': tuple(failure_states),
            'success_message': success_message,
            'clear_latch': clear_latch,
        }
        self._service_future = client.call_async(Trigger.Request())
        self._service_future.add_done_callback(
            lambda future, label=action_label: self._handle_patrol_service_response(
                future,
                action_label=label,
            )
        )

    def _start_navigation_command(
        self,
        context: ActiveCommandContext,
        *,
        target_pose: CommandPose | None,
        label: str,
    ) -> None:
        if target_pose is None:
            self._finish_active_command(
                'failed',
                '이동 명령에 목표 pose가 없습니다.',
                error='missing_target_pose',
            )
            return

        if target_pose.frame_id != self._plan.frame_id:
            self._finish_active_command(
                'failed',
                f'지원하지 않는 pose frame 입니다: {target_pose.frame_id}',
                error='unsupported_frame_id',
            )
            return

        self._goal_reject_retry_count = 0
        self._cancel_goal_retry_timer()
        context.target_pose = target_pose
        self._update_control_state()
        if context.command.preempt_current_navigation:
            self._prepare_navigation_preemption(context, label=label)
            return
        self._dispatch_navigation_goal(
            context,
            target_pose=target_pose,
            label=label,
            is_retry=False,
        )

    def _prepare_navigation_preemption(
        self,
        context: ActiveCommandContext,
        *,
        label: str,
    ) -> None:
        if not self._patrol_stop_client.wait_for_service(timeout_sec=self._patrol_service_wait_sec):
            self.get_logger().warning(
                '순찰 중지 서비스를 찾지 못해 stop 확인 없이 새 이동 명령을 실행합니다.'
            )
            self._dispatch_navigation_goal(
                context,
                target_pose=context.target_pose,
                label=label,
                is_retry=False,
            )
            return

        if context.started_at is None:
            context.started_at = _iso_now()
        self._write_status(
            self._build_status_payload(
                context,
                'running',
                '기존 순찰을 중지하고 새 이동 명령을 준비 중입니다.',
            )
        )
        self._service_future = self._patrol_stop_client.call_async(Trigger.Request())
        self._service_future.add_done_callback(
            lambda future, command_id=context.command.command_id, dispatch_label=label: self._handle_pre_navigation_patrol_stop_response(
                future,
                command_id=command_id,
                label=dispatch_label,
            )
        )

    def _handle_pre_navigation_patrol_stop_response(
        self,
        future: Any,
        *,
        command_id: str,
        label: str,
    ) -> None:
        self._service_future = None

        context = self._active_context
        if context is None or context.command.command_id != command_id:
            return

        if self._pending_context is not None:
            cancel_message, cancel_error = self._cancel_outcome_for_pending_transition()
            self._finish_active_command(
                'canceled',
                cancel_message,
                error=cancel_error,
            )
            return

        try:
            response = future.result()
        except Exception as exc:
            self.get_logger().warning(f'순찰 중지 선행 호출에 실패해 바로 이동을 시도합니다: {exc}')
            self._dispatch_navigation_goal(
                context,
                target_pose=context.target_pose,
                label=label,
                is_retry=False,
            )
            return

        if not response.success:
            self.get_logger().info(
                f'순찰 중지 선행 호출 응답: {response.message or "추가 메시지 없음"}. '
                '새 이동 명령은 계속 실행합니다.'
            )

        self._dispatch_navigation_goal(
            context,
            target_pose=context.target_pose,
            label=label,
            is_retry=False,
        )

    def _dispatch_navigation_goal(
        self,
        context: ActiveCommandContext,
        *,
        target_pose: CommandPose,
        label: str,
        is_retry: bool,
    ) -> None:
        if not self._navigate_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self._finish_active_command(
                'failed',
                f'NavigateToPose action server를 찾지 못했습니다: {self._action_name}',
                error='navigate_action_unavailable',
            )
            return

        context.target_pose = target_pose
        if context.started_at is None:
            context.started_at = _iso_now()

        goal = NavigateToPose.Goal()
        goal.pose = self._build_pose_stamped(target_pose.as_pose2d())
        goal.behavior_tree = ''

        message = f'{label} 명령을 실행 중입니다.'
        if is_retry:
            message = (
                f'{label} 명령 재시도 중입니다. '
                f'({self._goal_reject_retry_count}/{self._goal_reject_retry_limit})'
            )
        self._write_status(self._build_status_payload(context, 'running', message))
        self._goal_send_future = self._navigate_client.send_goal_async(goal)
        self._goal_send_future.add_done_callback(self._handle_navigation_goal_response)

    def _cancel_outcome_for_pending_transition(self) -> tuple[str, str]:
        if self._navigation_cancel_reason == 'emergency_stopped':
            return (
                '비상 정지 명령으로 현재 이동을 즉시 중단했습니다.',
                'emergency_stopped',
            )
        if self._navigation_cancel_reason == 'paused_by_control_command':
            return (
                '일시정지 명령으로 현재 이동을 중단했습니다.',
                'paused_by_control_command',
            )
        return (
            '새 이동 명령이 들어와 기존 이동을 중단했습니다.',
            'preempted_by_new_command',
        )

    def _handle_navigation_goal_response(self, future: Any) -> None:
        self._goal_send_future = None
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._finish_active_command(
                'failed',
                f'NavigateToPose goal 전송에 실패했습니다: {exc}',
                error='goal_send_failed',
            )
            return

        if not goal_handle.accepted:
            if self._pending_context is not None:
                cancel_message, cancel_error = self._cancel_outcome_for_pending_transition()
                self._finish_active_command(
                    'canceled',
                    cancel_message,
                    error=cancel_error,
                )
                return
            if self._schedule_goal_reject_retry():
                return
            self._finish_active_command(
                'failed',
                'NavigateToPose goal이 반복해서 거부되었습니다. 현재 로봇 위치 추정과 TF 상태를 확인하세요.',
                error='goal_rejected',
            )
            return

        self._active_goal_handle = goal_handle
        self._goal_reject_retry_count = 0
        self._cancel_goal_retry_timer()
        self._goal_result_future = goal_handle.get_result_async()
        self._goal_result_future.add_done_callback(self._handle_navigation_result)
        if self._resume_release_pending:
            self._resume_release_pending = False
            self._clear_control_latch(message='저장된 수동 이동 문맥을 재개했습니다.')
        else:
            self._update_control_state()
        if self._pending_context is not None:
            self._request_active_goal_cancel_for_preemption()

    def _handle_navigation_result(self, future: Any) -> None:
        self._active_goal_handle = None
        self._goal_result_future = None
        try:
            result = future.result()
        except Exception as exc:
            self._finish_active_command(
                'failed',
                f'NavigateToPose 결과 수신에 실패했습니다: {exc}',
                error='goal_result_failed',
            )
            return

        status = result.status
        nav_result = result.result

        if status == GoalStatus.STATUS_SUCCEEDED:
            self._finish_active_command('succeeded', '이동 명령이 완료되었습니다.')
            return

        if status == GoalStatus.STATUS_CANCELED:
            if self._pending_context is not None:
                cancel_message, cancel_error = self._cancel_outcome_for_pending_transition()
                self._finish_active_command(
                    'canceled',
                    cancel_message,
                    error=cancel_error,
                )
                return
            self._finish_active_command('canceled', '이동 명령이 취소되었습니다.', error='goal_canceled')
            return

        message = nav_result.error_msg or '이동 명령이 실패했습니다.'
        if nav_result.error_code != NavigateToPose.Result.NONE:
            message = f'{message} (error_code={nav_result.error_code})'
        self._finish_active_command('failed', message, error='navigate_failed')

    def _handle_patrol_service_response(
        self,
        future: Any,
        *,
        action_label: str,
    ) -> None:
        self._service_future = None
        try:
            response = future.result()
        except Exception as exc:
            self._patrol_state_wait = None
            self._finish_active_command(
                'failed',
                f'{action_label} 서비스 호출에 실패했습니다: {exc}',
                error='patrol_service_call_failed',
            )
            return

        if not response.success:
            self._patrol_state_wait = None
            self._finish_active_command(
                'failed',
                f'{action_label} 요청이 실패했습니다: {response.message}',
                error='patrol_service_failed',
            )
            return

        if self._pending_context is not None:
            cancel_message, cancel_error = self._cancel_outcome_for_pending_transition()
            self._patrol_state_wait = None
            self._finish_active_command(
                'canceled',
                cancel_message,
                error=cancel_error,
            )
            return

        if self._patrol_state_wait is None:
            self._finish_active_command(
                'succeeded',
                response.message or f'{action_label} 요청이 완료되었습니다.',
                result='executed',
            )
            return

        if self._latest_patrol_status is not None:
            self._maybe_finish_patrol_state_wait(self._latest_patrol_status)

    def _request_active_goal_cancel_for_preemption(self) -> None:
        if self._active_goal_handle is None or self._goal_cancel_future is not None:
            return
        self._goal_cancel_future = self._active_goal_handle.cancel_goal_async()
        self._goal_cancel_future.add_done_callback(self._handle_active_goal_cancel_response)

    def _handle_active_goal_cancel_response(self, future: Any) -> None:
        self._goal_cancel_future = None
        try:
            cancel_response = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f'기존 이동 goal 취소 응답을 받지 못했습니다. 새 목표로 전환을 계속 시도합니다: {exc}'
            )
            if self._pending_context is not None:
                cancel_message, cancel_error = self._cancel_outcome_for_pending_transition()
                self._finish_active_command(
                    'canceled',
                    cancel_message,
                    error=cancel_error,
                )
            return

        if cancel_response.goals_canceling:
            return

        self.get_logger().warning(
            '기존 이동 goal cancel 요청이 거부되었습니다. 새 목표로 전환을 계속 시도합니다.'
        )
        if self._pending_context is not None:
            cancel_message, cancel_error = self._cancel_outcome_for_pending_transition()
            self._finish_active_command(
                'canceled',
                cancel_message,
                error=cancel_error,
            )

    def _finish_active_command(
        self,
        status: str,
        message: str,
        *,
        error: str | None = None,
        result: str | None = None,
    ) -> None:
        if self._active_context is None:
            return

        self._cancel_goal_retry_timer()
        self._goal_reject_retry_count = 0
        payload = self._build_status_payload(
            self._active_context,
            status,
            message,
            error=error,
            result=result,
            completed_at=_iso_now() if status in TERMINAL_STATUSES else None,
        )
        self._write_status(payload)
        self._remember_processed_command_id(self._active_context.command.command_id)
        self._active_context = None
        self._goal_cancel_future = None
        self._service_future = None
        self._patrol_state_wait = None
        self._navigation_cancel_reason = ''
        self._resume_release_pending = False
        self._update_control_state()
        if self._pending_context is not None:
            self._start_pending_command()

    def _build_status_payload(
        self,
        context: ActiveCommandContext,
        status: str,
        message: str,
        *,
        error: str | None = None,
        result: str | None = None,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        frame_id = context.target_pose.frame_id if context.target_pose is not None else self._plan.frame_id
        return build_manual_command_status_payload(
            command_id=context.command.command_id,
            command_type=context.command.command_type,
            robot_id=context.command.robot_id,
            requested_by=context.command.requested_by,
            map_id=self._map_id,
            frame_id=frame_id,
            status=status,
            message=message,
            error=error,
            result=result,
            target_pose=(
                context.target_pose.as_status_payload()
                if context.target_pose is not None
                else None
            ),
            home_waypoint_id=context.home_waypoint_id,
            control_state=self._control_state.as_payload(),
            received_at=context.received_at,
            started_at=context.started_at,
            completed_at=completed_at,
        )

    def _write_status(self, payload: dict[str, Any]) -> None:
        write_json_atomic(self._status_path, payload)
        self._last_status_payload = payload

    def _build_pose_stamped(self, pose: Pose2D) -> PoseStamped:
        return build_latest_pose_stamped(
            frame_id=self._plan.frame_id,
            x_value=pose.x,
            y_value=pose.y,
            z_value=pose.z,
            yaw_value=pose.yaw,
        )

    def _schedule_goal_reject_retry(self) -> bool:
        context = self._active_context
        if context is None or context.target_pose is None:
            return False
        if self._goal_reject_retry_sec <= 0.0:
            return False
        if not should_retry_goal_rejection(
            self._goal_reject_retry_count,
            self._goal_reject_retry_limit,
        ):
            return False

        self._goal_reject_retry_count += 1
        self._cancel_goal_retry_timer()
        retry_message = (
            'NavigateToPose goal이 일시적으로 거부되어 '
            f'{self._goal_reject_retry_sec:.2f}s 후 재시도합니다. '
            f'({self._goal_reject_retry_count}/{self._goal_reject_retry_limit})'
        )
        self.get_logger().warning(retry_message)
        self._write_status(self._build_status_payload(context, 'running', retry_message))
        self._goal_retry_timer = self.create_timer(
            self._goal_reject_retry_sec,
            self._retry_active_navigation_goal,
        )
        return True

    def _retry_active_navigation_goal(self) -> None:
        self._cancel_goal_retry_timer()
        context = self._active_context
        if context is None or context.target_pose is None:
            return
        self._dispatch_navigation_goal(
            context,
            target_pose=context.target_pose,
            label=describe_manual_navigation_label(
                context.command.command_type,
                context.home_waypoint_id,
            ),
            is_retry=True,
        )

    def _cancel_goal_retry_timer(self) -> None:
        if self._goal_retry_timer is None:
            return
        self._goal_retry_timer.cancel()
        self.destroy_timer(self._goal_retry_timer)
        self._goal_retry_timer = None

    def destroy_node(self) -> bool:
        self._cancel_goal_retry_timer()
        self._pending_context = None
        self._navigate_client.destroy()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = RobotManualCommandExecutor()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
