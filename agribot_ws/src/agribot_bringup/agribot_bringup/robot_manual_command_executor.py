from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from action_msgs.msg import GoalStatus
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from agribot_navigation.nav_goal_utils import build_latest_pose_stamped
from std_srvs.srv import Trigger

from agribot_navigation.patrol_config import (
    PatrolPlan,
    Pose2D,
    get_default_patrol_waypoints_path,
    load_patrol_plan,
)

from .runtime_snapshot_service import (
    DEFAULT_FRAME_ID,
    DEFAULT_MAP_ID,
    build_manual_command_status_payload,
    manual_command_path,
    manual_command_status_path,
    read_json_object,
    runtime_dir_from_env,
    write_json_atomic,
)

TERMINAL_STATUSES = {'succeeded', 'failed', 'canceled'}
SUPPORTED_COMMAND_TYPES = {
    'navigate_to_pose',
    'pause_patrol',
    'resume_patrol',
    'return_home',
}
NAVIGATION_COMMAND_TYPES = {
    'navigate_to_pose',
    'return_home',
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
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


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


class RobotManualCommandExecutor(Node):
    def __init__(self) -> None:
        super().__init__('robot_manual_command_executor')

        if not self.has_parameter('use_sim_time'):
            self.declare_parameter('use_sim_time', True)
        self.declare_parameter('map_id', DEFAULT_MAP_ID)
        self.declare_parameter('robot_id', 'AGR-02')
        self.declare_parameter('map_frame', DEFAULT_FRAME_ID)
        self.declare_parameter('navigate_to_pose_action', 'navigate_to_pose')
        self.declare_parameter('patrol_stop_service', '/patrol/stop')
        self.declare_parameter('patrol_resume_service', '/patrol/resume')
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
        self._map_id = str(self.get_parameter('map_id').value)
        self._default_robot_id = str(self.get_parameter('robot_id').value)
        self._map_frame = str(self.get_parameter('map_frame').value)
        self._action_name = str(self.get_parameter('navigate_to_pose_action').value)
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

        self._recover_previous_command_status()
        poll_period = float(self.get_parameter('command_poll_period_sec').value)
        self.create_timer(poll_period, self._poll_command_file)

        self.get_logger().info(
            f'robot manual command executor started. command_path={self._command_path}'
        )

    def _load_patrol_plan(self) -> PatrolPlan:
        plan_path = Path(str(self.get_parameter('patrol_waypoints_file').value)).expanduser()
        if not plan_path.is_absolute():
            plan_path = get_default_patrol_waypoints_path().parent.parent / plan_path
        return load_patrol_plan(plan_path)

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
            target_pose=(
                command.target_pose.as_status_payload()
                if command.target_pose is not None
                else None
            ),
            home_waypoint_id=command.home_waypoint_id,
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

        if command.command_type == 'pause_patrol':
            self._call_patrol_service(
                context,
                self._patrol_stop_client,
                success_message='순찰 중지 요청이 완료되었습니다.',
                action_label='순찰 중지',
            )
            return

        if command.command_type == 'resume_patrol':
            self._call_patrol_service(
                context,
                self._patrol_resume_client,
                success_message='순찰 재개 요청이 완료되었습니다.',
                action_label='순찰 재개',
            )
            return

        self._finish_active_command(
            'failed',
            f'지원하지 않는 command_type 입니다: {command.command_type}',
            error='unsupported_command_type',
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
            self._finish_active_command(
                'canceled',
                '새 이동 명령이 들어와 기존 이동 준비를 중단했습니다.',
                error='preempted_by_new_command',
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

    def _call_patrol_service(
        self,
        context: ActiveCommandContext,
        client,
        *,
        success_message: str,
        action_label: str,
    ) -> None:
        if not client.wait_for_service(timeout_sec=self._patrol_service_wait_sec):
            self._finish_active_command(
                'failed',
                f'{action_label} 서비스가 준비되지 않았습니다.',
                error='patrol_service_unavailable',
            )
            return

        context.started_at = _iso_now()
        self._write_status(
            self._build_status_payload(
                context,
                'running',
                f'{action_label} 명령을 실행 중입니다.',
            )
        )
        self._service_future = client.call_async(Trigger.Request())
        self._service_future.add_done_callback(
            lambda future, message=success_message, action_label=action_label: self._handle_patrol_service_response(
                future,
                success_message=message,
                action_label=action_label,
            )
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
                self._finish_active_command(
                    'canceled',
                    '새 이동 명령이 들어와 기존 goal 전송을 중단했습니다.',
                    error='preempted_by_new_command',
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
                self._finish_active_command(
                    'canceled',
                    '새 이동 명령이 들어와 기존 이동을 중단했습니다.',
                    error='preempted_by_new_command',
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
        success_message: str,
        action_label: str,
    ) -> None:
        self._service_future = None
        try:
            response = future.result()
        except Exception as exc:
            self._finish_active_command(
                'failed',
                f'{action_label} 서비스 호출에 실패했습니다: {exc}',
                error='patrol_service_call_failed',
            )
            return

        if not response.success:
            self._finish_active_command(
                'failed',
                f'{action_label} 요청이 실패했습니다: {response.message}',
                error='patrol_service_failed',
            )
            return

        self._finish_active_command('succeeded', success_message)

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
                self._finish_active_command(
                    'canceled',
                    '새 이동 명령이 들어와 기존 이동을 선점 전환합니다.',
                    error='preempted_by_new_command',
                )
            return

        if cancel_response.goals_canceling:
            return

        self.get_logger().warning(
            '기존 이동 goal cancel 요청이 거부되었습니다. 새 목표로 전환을 계속 시도합니다.'
        )
        if self._pending_context is not None:
            self._finish_active_command(
                'canceled',
                '새 이동 명령이 들어와 기존 이동을 선점 전환합니다.',
                error='preempted_by_new_command',
            )

    def _finish_active_command(
        self,
        status: str,
        message: str,
        *,
        error: str | None = None,
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
            completed_at=_iso_now() if status in TERMINAL_STATUSES else None,
        )
        self._write_status(payload)
        self._remember_processed_command_id(self._active_context.command.command_id)
        self._active_context = None
        self._goal_cancel_future = None
        self._service_future = None
        if self._pending_context is not None:
            self._start_pending_command()

    def _build_status_payload(
        self,
        context: ActiveCommandContext,
        status: str,
        message: str,
        *,
        error: str | None = None,
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
            target_pose=(
                context.target_pose.as_status_payload()
                if context.target_pose is not None
                else None
            ),
            home_waypoint_id=context.home_waypoint_id,
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
