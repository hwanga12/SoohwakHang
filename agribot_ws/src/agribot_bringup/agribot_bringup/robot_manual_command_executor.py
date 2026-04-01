# 이 모듈은 통합 실행과 런치 조율 패키지에서 robot manual command executor 절차를 담당한다.
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import time
from typing import Any

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Point, PoseStamped, PoseWithCovarianceStamped
from nav2_msgs.action import BackUp, ComputePathToPose, NavigateThroughPoses, NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.duration import Duration
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
    ManualNavigationPhase,
    MotionActivity,
    ResumeContext,
    ResumeContextType,
    build_control_state_payload,
    iso_now,
)
from .manual_navigation_routing import (
    ManualNavigationRoute,
    build_manual_navigation_route,
    select_best_target_waypoint_id,
    select_route_egress_waypoint_id,
)
from .runtime_snapshot_service import (
    DEFAULT_FRAME_ID,
    DEFAULT_MAP_ID,
    build_manual_command_status_payload,
    control_state_path,
    manual_command_path,
    manual_command_status_path,
    pose_snapshot_path,
    read_json_object,
    runtime_dir_from_env,
    write_json_atomic,
)

TERMINAL_STATUSES = {'succeeded', 'failed', 'canceled'}
FINAL_OBSERVATION_INTERMEDIATE_TARGET_FRACTIONS = (
    0.92,
    0.84,
    0.76,
    0.68,
    0.60,
)
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
NAVIGATE_TO_POSE_NONE_ERROR_CODE = int(getattr(NavigateToPose.Result, 'NONE', 0) or 0)
START_OCCUPIED_ERROR_CODES = {205, 305}
TRANSIENT_NAVIGATION_TF_ERROR_CODES = {102, 202, 302}
_UNSET = object()


@dataclass(frozen=True)
class PatrolStatusSnapshot:
    # patrol 상태 시점의 값을 기록하기 위한 스냅샷 클래스를 정의한다.
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
        # 현재 값을 resume 페이로드 형태로 변환한다.
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
    # 명령 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    x: float
    y: float
    z: float
    yaw: float
    frame_id: str

    def as_status_payload(self) -> dict[str, Any]:
        # 현재 값을 상태 페이로드 형태로 변환한다.
        return {
            'x': self.x,
            'y': self.y,
            'z': self.z,
            'yaw': self.yaw,
            'frame_id': self.frame_id,
        }

    def as_pose2d(self) -> Pose2D:
        # 현재 값을 위치 자세 2 d 형태로 변환한다.
        return Pose2D(x=self.x, y=self.y, z=self.z, yaw=self.yaw)


@dataclass(frozen=True)
class ObservationGoalCandidate:
    # 관측 결과 목표 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    inspect_waypoint_id: str
    inspect_waypoint_name: str | None
    final_target_pose: CommandPose
    navigation_pose: CommandPose | None = None


@dataclass(frozen=True)
class ManualCommand:
    # manual 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    command_id: str
    command_type: str
    robot_id: str
    requested_by: str
    target_pose: CommandPose | None
    plant_id: str | None = None
    inspect_waypoint_id: str | None = None
    inspect_waypoint_ids: tuple[str, ...] = ()
    observation_candidates: tuple[ObservationGoalCandidate, ...] = ()
    home_waypoint_id: str | None = None
    preempt_current_navigation: bool = False


@dataclass
class ActiveCommandContext:
    # 진행 중 명령 context 한 건을 명확한 필드 구조로 담기 위한 데이터 클래스다.
    command: ManualCommand
    received_at: str
    started_at: str | None = None
    target_pose: CommandPose | None = None
    route_target_pose: CommandPose | None = None
    final_target_pose: CommandPose | None = None
    target_waypoint_id: str | None = None
    navigation_phase: ManualNavigationPhase | None = None
    home_waypoint_id: str | None = None
    route_egress_release_attempted: bool = False


class CommandValidationError(ValueError):
    # 명령 validation error 문제를 구분하기 위한 예외 클래스다.
    def __init__(
        self,
        message: str,
        *,
        command_id: str | None = None,
        command_type: str | None = None,
        robot_id: str = 'AGR-02',
        requested_by: str = '',
    ) -> None:
        # CommandValidationError 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__(message)
        self.command_id = command_id
        self.command_type = command_type
        self.robot_id = robot_id
        self.requested_by = requested_by


def _iso_now() -> str:
    # iso now 정보를 계산해 반환한다.
    return iso_now()


def _extract_string(payload: dict[str, Any], key: str, *, default: str = '') -> str:
    # 원본 데이터에서 string만 골라 추출한다.
    raw_value = payload.get(key, default)
    return str(raw_value).strip() if raw_value is not None else default


def _extract_optional_bool(payload: dict[str, Any], key: str) -> bool | None:
    # 원본 데이터에서 optional bool만 골라 추출한다.
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


def _extract_string_list(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    # 원본 데이터에서 string list만 골라 추출한다.
    raw_value = payload.get(key)
    if raw_value is None:
        return ()
    if not isinstance(raw_value, list):
        raise ValueError(f'{key} 는 문자열 배열이어야 합니다.')

    return tuple(
        normalized
        for item in raw_value
        if (normalized := str(item).strip())
    )


def _extract_observation_candidates(
    payload: dict[str, Any],
    default_frame: str,
) -> tuple[ObservationGoalCandidate, ...]:
    # 원본 데이터에서 관측 결과 candidates만 골라 추출한다.
    raw_value = payload.get('observation_candidates')
    if raw_value is None:
        return ()
    if not isinstance(raw_value, list):
        raise ValueError('observation_candidates 는 배열이어야 합니다.')

    candidates: list[ObservationGoalCandidate] = []
    seen_waypoint_ids: set[str] = set()
    for index, item in enumerate(raw_value):
        if not isinstance(item, dict):
            raise ValueError(f'observation_candidates[{index}] 는 JSON object여야 합니다.')

        inspect_waypoint_id = str(item.get('inspect_waypoint_id', '')).strip()
        if not inspect_waypoint_id:
            raise ValueError(f'observation_candidates[{index}].inspect_waypoint_id 가 필요합니다.')
        if inspect_waypoint_id in seen_waypoint_ids:
            continue

        final_target_pose = item.get('final_target_pose')
        if not isinstance(final_target_pose, dict):
            raise ValueError(f'observation_candidates[{index}].final_target_pose 가 필요합니다.')

        navigation_pose = item.get('navigation_pose')
        candidates.append(
            ObservationGoalCandidate(
                inspect_waypoint_id=inspect_waypoint_id,
                inspect_waypoint_name=(
                    str(item.get('inspect_waypoint_name')).strip()
                    if item.get('inspect_waypoint_name') is not None
                    else None
                ) or None,
                final_target_pose=_coerce_pose(final_target_pose, default_frame),
                navigation_pose=(
                    _coerce_pose(navigation_pose, default_frame)
                    if isinstance(navigation_pose, dict)
                    else None
                ),
            )
        )
        seen_waypoint_ids.add(inspect_waypoint_id)

    return tuple(candidates)


def _coerce_pose(payload: dict[str, Any], default_frame: str) -> CommandPose:
    # coerce 위치 자세 정보를 계산해 반환한다.
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
    # 원본 데이터에서 target 위치 자세만 골라 추출한다.
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
    # 수동 주행 라벨을 설명 문자열로 만든다.
    if command_type == 'return_home':
        if home_waypoint_id:
            return f'홈 복귀({home_waypoint_id})'
        return '홈 복귀'
    return '수동 목표점'


def should_retry_goal_rejection(retry_count: int, retry_limit: int) -> bool:
    # retry 목표 rejection가 필요한 상황인지 여부를 판단한다.
    return retry_limit > 0 and retry_count < retry_limit


def should_retry_start_occupied_recovery(retry_count: int, retry_limit: int) -> bool:
    # retry start occupied recovery가 필요한 상황인지 여부를 판단한다.
    return retry_limit > 0 and retry_count < retry_limit


def is_navigation_command_type(command_type: str) -> bool:
    # navigation 명령 type인지 여부를 불리언 값으로 판단한다.
    return command_type in NAVIGATION_COMMAND_TYPES


def is_pause_command_type(command_type: str) -> bool:
    # pause 명령 type인지 여부를 불리언 값으로 판단한다.
    return command_type in PAUSE_COMMAND_TYPES


def is_resume_command_type(command_type: str) -> bool:
    # resume 명령 type인지 여부를 불리언 값으로 판단한다.
    return command_type in RESUME_COMMAND_TYPES


def parse_patrol_status_payload(raw_data: str) -> PatrolStatusSnapshot | None:
    # patrol 상태 payload를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
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
    # patrol resume context를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
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
    # resume context을 설명 문자열로 만든다.
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
    # block 명령 FOR control 모드가 필요한 상황인지 여부를 판단한다.
    if not mode.is_latched:
        return False
    return command_type not in {'emergency_stop', 'resume_motion', 'resume_patrol'}

def resolve_preempt_current_navigation(
    command_type: str,
    *,
    raw_payload: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    # 현재 입력 조건을 바탕으로 preempt current navigation를 계산하거나 결정한다.
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
    # manual 명령 payload를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
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
    plant_id = _extract_string(payload, 'plant_id') or _extract_string(
        raw_payload,
        'plant_id',
    )
    inspect_waypoint_id = _extract_string(payload, 'inspect_waypoint_id') or _extract_string(
        raw_payload,
        'inspect_waypoint_id',
    )
    inspect_waypoint_ids = _extract_string_list(payload, 'inspect_waypoint_ids') or _extract_string_list(
        raw_payload,
        'inspect_waypoint_ids',
    )
    observation_candidates = _extract_observation_candidates(payload, default_frame) or _extract_observation_candidates(
        raw_payload,
        default_frame,
    )

    return ManualCommand(
        command_id=command_id,
        command_type=command_type,
        robot_id=robot_id,
        requested_by=requested_by,
        target_pose=target_pose,
        plant_id=plant_id or None,
        inspect_waypoint_id=inspect_waypoint_id or None,
        inspect_waypoint_ids=inspect_waypoint_ids,
        observation_candidates=observation_candidates,
        home_waypoint_id=home_waypoint_id or None,
        preempt_current_navigation=preempt_current_navigation,
    )


def resolve_return_home_target(
    command: ManualCommand,
    plan: PatrolPlan,
) -> tuple[str, CommandPose]:
    # 현재 입력 조건을 바탕으로 return home target를 계산하거나 결정한다.
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
    # manual resume context를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
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
        target_waypoint_id=context.target_waypoint_id,
        home_waypoint_id=context.home_waypoint_id,
        route_target_pose=(
            context.route_target_pose.as_status_payload()
            if context.route_target_pose is not None
            else None
        ),
        final_target_pose=(
            context.final_target_pose.as_status_payload()
            if context.final_target_pose is not None
            else None
        ),
        navigation_phase=context.navigation_phase.value if context.navigation_phase is not None else None,
    )


def context_has_navigation_target(context: ActiveCommandContext | None) -> bool:
    # context has 주행 대상 정보를 계산해 반환한다.
    return context is not None and context.target_pose is not None


def should_restore_paused_manual_navigation_after_failed_resume(
    context: ActiveCommandContext | None,
    *,
    status: str,
) -> bool:
    # restore paused manual navigation after failed resume가 필요한 상황인지 여부를 판단한다.
    return (
        status == 'failed'
        and context is not None
        and context.command.command_type in RESUME_COMMAND_TYPES
        and context.target_pose is not None
    )


def should_run_resume_release_recovery(
    context: ActiveCommandContext | None,
    *,
    distance_m: float,
) -> bool:
    # RUN resume release recovery가 필요한 상황인지 여부를 판단한다.
    return (
        distance_m > 0.0
        and context is not None
        and context.command.command_type == 'resume_motion'
        and context.target_pose is not None
    )


def should_run_route_egress_release_recovery(
    context: ActiveCommandContext | None,
    *,
    distance_m: float,
) -> bool:
    # RUN 경로 egress release recovery가 필요한 상황인지 여부를 판단한다.
    return (
        distance_m > 0.0
        and context is not None
        and context.navigation_phase is ManualNavigationPhase.ROUTE_EGRESS
        and context.target_pose is not None
        and not context.route_egress_release_attempted
    )


def _navigation_error_code(nav_result: Any) -> int:
    # 주행 error code 정보를 계산해 반환한다.
    return int(getattr(nav_result, 'error_code', NAVIGATE_TO_POSE_NONE_ERROR_CODE) or 0)


def _navigation_error_message(nav_result: Any) -> str:
    # 주행 error 메시지 정보를 계산해 반환한다.
    return str(getattr(nav_result, 'error_msg', '') or '').strip()


def _navigation_result_indicates_start_occupied(nav_result: Any) -> bool:
    # 주행 결과 indicates start occupied 정보를 계산해 반환한다.
    error_code = _navigation_error_code(nav_result)
    if error_code in START_OCCUPIED_ERROR_CODES:
        return True
    error_msg = _navigation_error_message(nav_result).lower()
    return bool(error_msg) and 'start' in error_msg and 'occupied' in error_msg


def _navigation_result_indicates_transient_tf_error(nav_result: Any) -> bool:
    # 주행 결과 indicates transient tf error 정보를 계산해 반환한다.
    error_code = _navigation_error_code(nav_result)
    if error_code in TRANSIENT_NAVIGATION_TF_ERROR_CODES:
        return True
    error_msg = _navigation_error_message(nav_result).lower()
    return bool(error_msg) and (
        'transform' in error_msg
        or 'extrapolation' in error_msg
        or 'tf' in error_msg
    )


def _navigation_failure_message(nav_result: Any) -> str:
    # 주행 failure 메시지 정보를 계산해 반환한다.
    error_msg = _navigation_error_message(nav_result)
    error_code = _navigation_error_code(nav_result)
    if _navigation_result_indicates_start_occupied(nav_result):
        return (
            '현재 시작 위치가 통로 밖 장애물로 판정되어 새 이동을 시작할 수 없습니다. '
            f'{error_msg or "로봇을 통로 중앙으로 되돌린 뒤 다시 시도하세요."} '
            f'(error_code={error_code})'
        )

    message = error_msg or '이동 명령이 실패했습니다.'
    if error_code != NAVIGATE_TO_POSE_NONE_ERROR_CODE:
        message = f'{message} (error_code={error_code})'
    return message


def is_pose_within_xy_tolerance(
    current_pose: Pose2D | None,
    target_pose: CommandPose | Pose2D | None,
    *,
    xy_tolerance_m: float,
) -> bool:
    # 위치 자세 within XY tolerance인지 여부를 불리언 값으로 판단한다.
    if current_pose is None or target_pose is None or xy_tolerance_m <= 0.0:
        return False

    return math.hypot(
        float(target_pose.x) - current_pose.x,
        float(target_pose.y) - current_pose.y,
    ) <= xy_tolerance_m


def pose_distance_xy(
    left: CommandPose | Pose2D | None,
    right: CommandPose | Pose2D | None,
) -> float:
    # 위치 자세 distance xy 정보를 계산해 반환한다.
    if left is None or right is None:
        return float('inf')

    return math.hypot(float(left.x) - float(right.x), float(left.y) - float(right.y))


def interpolate_command_pose(
    start_pose: CommandPose,
    end_pose: CommandPose,
    *,
    fraction: float,
) -> CommandPose:
    # interpolate 명령 위치 자세 정보를 계산해 반환한다.
    clamped_fraction = max(0.0, min(1.0, fraction))
    interpolated_yaw = math.atan2(
        math.sin(start_pose.yaw + (end_pose.yaw - start_pose.yaw) * clamped_fraction),
        math.cos(start_pose.yaw + (end_pose.yaw - start_pose.yaw) * clamped_fraction),
    )
    return CommandPose(
        x=start_pose.x + ((end_pose.x - start_pose.x) * clamped_fraction),
        y=start_pose.y + ((end_pose.y - start_pose.y) * clamped_fraction),
        z=start_pose.z + ((end_pose.z - start_pose.z) * clamped_fraction),
        yaw=interpolated_yaw,
        frame_id=end_pose.frame_id,
    )


def build_intermediate_final_observation_targets(
    route_target_pose: CommandPose | None,
    final_target_pose: CommandPose | None,
    *,
    fractions: tuple[float, ...] = FINAL_OBSERVATION_INTERMEDIATE_TARGET_FRACTIONS,
    min_spacing_m: float = 0.12,
) -> tuple[CommandPose, ...]:
    # intermediate final 관측 결과 targets를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    if route_target_pose is None or final_target_pose is None:
        return ()

    total_distance = pose_distance_xy(route_target_pose, final_target_pose)
    if not math.isfinite(total_distance) or total_distance <= min_spacing_m:
        return ()

    targets: list[CommandPose] = []
    for fraction in fractions:
        candidate = interpolate_command_pose(
            route_target_pose,
            final_target_pose,
            fraction=fraction,
        )
        if pose_distance_xy(candidate, route_target_pose) <= min_spacing_m:
            continue
        if pose_distance_xy(candidate, final_target_pose) <= min_spacing_m:
            continue
        if targets and pose_distance_xy(candidate, targets[-1]) <= min_spacing_m:
            continue
        targets.append(candidate)

    return tuple(targets)


def read_runtime_pose_snapshot(
    runtime_dir: Path,
    *,
    expected_frame: str,
    max_age_sec: float | None = None,
) -> Pose2D | None:
    # 런타임 데이터 위치 자세 스냅샷를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    try:
        payload = read_json_object(pose_snapshot_path(runtime_dir))
    except (OSError, ValueError):
        return None

    if max_age_sec is not None and max_age_sec > 0.0:
        try:
            snapshot_timestamp = float(payload['timestamp'])
        except (KeyError, TypeError, ValueError):
            return None
        if (time.time() - snapshot_timestamp) > max_age_sec:
            return None

    pose = payload.get('pose')
    if not isinstance(pose, dict):
        return None

    frame_id = str(pose.get('frame_id', expected_frame)).strip() or expected_frame
    if frame_id != expected_frame:
        return None

    try:
        return Pose2D(
            x=float(pose['x']),
            y=float(pose['y']),
            z=float(pose.get('z', 0.0)),
            yaw=float(pose.get('yaw', 0.0)),
        )
    except (KeyError, TypeError, ValueError):
        return None


def should_treat_failed_navigation_as_success(
    runtime_dir: Path,
    *,
    expected_frame: str,
    target_pose: CommandPose | None,
    xy_tolerance_m: float,
    max_snapshot_age_sec: float | None = None,
) -> bool:
    # treat failed navigation AS success가 필요한 상황인지 여부를 판단한다.
    if target_pose is None or xy_tolerance_m <= 0.0:
        return False

    current_pose = read_runtime_pose_snapshot(
        runtime_dir,
        expected_frame=expected_frame,
        max_age_sec=max_snapshot_age_sec,
    )
    return is_pose_within_xy_tolerance(
        current_pose,
        target_pose,
        xy_tolerance_m=xy_tolerance_m,
    )


def should_complete_route_anchor_only(
    *,
    current_pose: Pose2D | None,
    route_target_pose: CommandPose | None,
    final_path_available: bool,
    xy_tolerance_m: float,
) -> bool:
    # complete 경로 anchor only가 필요한 상황인지 여부를 판단한다.
    if final_path_available:
        return False
    return is_pose_within_xy_tolerance(
        current_pose,
        route_target_pose,
        xy_tolerance_m=xy_tolerance_m,
    )


def should_attempt_route_egress_simulation_pose_reset(
    active_context: ActiveCommandContext | None,
) -> bool:
    # attempt 경로 egress 시뮬레이션 위치 자세 reset가 필요한 상황인지 여부를 판단한다.
    return (
        active_context is not None
        and active_context.navigation_phase is ManualNavigationPhase.ROUTE_EGRESS
        and active_context.target_pose is not None
    )


def should_release_orphaned_active_command(
    active_context: ActiveCommandContext | None,
    last_status_payload: dict[str, Any] | None,
    *,
    has_pending_activity: bool,
) -> bool:
    # release orphaned active 명령가 필요한 상황인지 여부를 판단한다.
    if active_context is None or has_pending_activity or not isinstance(last_status_payload, dict):
        return False

    last_command_id = str(last_status_payload.get('command_id', '')).strip()
    last_status = str(last_status_payload.get('status', '')).strip()
    return (
        bool(last_command_id)
        and last_command_id == active_context.command.command_id
        and last_status in TERMINAL_STATUSES
    )


class RobotManualCommandExecutor(Node):
    # robot manual 명령 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    def __init__(self) -> None:
        # RobotManualCommandExecutor 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__('robot_manual_command_executor')

        if not self.has_parameter('use_sim_time'):
            self.declare_parameter('use_sim_time', True)
        self.declare_parameter('map_id', DEFAULT_MAP_ID)
        self.declare_parameter('robot_id', 'AGR-02')
        self.declare_parameter('map_frame', DEFAULT_FRAME_ID)
        self.declare_parameter('navigate_to_pose_action', 'navigate_to_pose')
        self.declare_parameter('navigate_through_poses_action', 'navigate_through_poses')
        self.declare_parameter('compute_path_to_pose_action', 'compute_path_to_pose')
        self.declare_parameter('patrol_status_topic', '/patrol/status')
        self.declare_parameter('patrol_stop_service', '/patrol/stop')
        self.declare_parameter('patrol_resume_service', '/patrol/resume')
        self.declare_parameter('control_state_topic', '/robot/control_state')
        self.declare_parameter('nav_server_wait_sec', 5.0)
        self.declare_parameter('patrol_service_wait_sec', 1.0)
        self.declare_parameter('backup_action', 'backup')
        self.declare_parameter('goal_reject_retry_sec', 0.75)
        self.declare_parameter('goal_reject_retry_limit', 4)
        self.declare_parameter('resume_release_recovery_distance_m', 0.14)
        self.declare_parameter('resume_release_recovery_speed_mps', 0.05)
        self.declare_parameter('resume_release_recovery_time_allowance_sec', 3.0)
        self.declare_parameter('route_egress_release_recovery_distance_m', 0.24)
        self.declare_parameter('route_egress_release_recovery_speed_mps', 0.06)
        self.declare_parameter('route_egress_release_recovery_time_allowance_sec', 3.5)
        self.declare_parameter('start_occupied_recovery_distance_m', 0.28)
        self.declare_parameter('start_occupied_recovery_speed_mps', 0.08)
        self.declare_parameter('start_occupied_recovery_time_allowance_sec', 4.0)
        self.declare_parameter('start_occupied_recovery_limit', 1)
        self.declare_parameter('goal_soft_complete_xy_tolerance_m', 0.55)
        self.declare_parameter('runtime_pose_snapshot_max_age_sec', 1.5)
        self.declare_parameter('final_observation_stage_trigger_distance_m', 0.08)
        self.declare_parameter('final_observation_soft_complete_xy_tolerance_m', 0.4)
        self.declare_parameter('route_anchor_fallback_xy_tolerance_m', 0.65)
        self.declare_parameter('simulation_pose_reset_recovery_enabled', True)
        self.declare_parameter('simulation_pose_reset_retry_limit', 1)
        self.declare_parameter('simulation_pose_reset_retry_delay_sec', 0.8)
        self.declare_parameter('simulation_pose_reset_robot_model_name', 'agribot')
        self.declare_parameter('gazebo_world_name', 'farm_world')
        self.declare_parameter('gazebo_partition', os.environ.get('GZ_PARTITION', 'agribot_sim'))
        self.declare_parameter('gazebo_command_timeout_ms', 3000)
        self.declare_parameter('gz_executable', 'gz')
        self.declare_parameter('initial_pose_topic', '/initialpose')
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
        self._batch_action_name = str(self.get_parameter('navigate_through_poses_action').value)
        self._path_probe_action_name = str(self.get_parameter('compute_path_to_pose_action').value)
        self._backup_action_name = str(self.get_parameter('backup_action').value)
        self._patrol_status_topic = str(self.get_parameter('patrol_status_topic').value)
        self._control_state_topic = str(self.get_parameter('control_state_topic').value)
        self._nav_server_wait_sec = float(self.get_parameter('nav_server_wait_sec').value)
        self._patrol_service_wait_sec = float(self.get_parameter('patrol_service_wait_sec').value)
        self._goal_reject_retry_sec = max(0.0, float(self.get_parameter('goal_reject_retry_sec').value))
        self._goal_reject_retry_limit = max(0, int(self.get_parameter('goal_reject_retry_limit').value))
        self._resume_release_recovery_distance_m = max(
            0.0,
            float(self.get_parameter('resume_release_recovery_distance_m').value),
        )
        self._resume_release_recovery_speed_mps = max(
            0.01,
            float(self.get_parameter('resume_release_recovery_speed_mps').value),
        )
        self._resume_release_recovery_time_allowance_sec = max(
            0.5,
            float(self.get_parameter('resume_release_recovery_time_allowance_sec').value),
        )
        self._route_egress_release_recovery_distance_m = max(
            0.0,
            float(self.get_parameter('route_egress_release_recovery_distance_m').value),
        )
        self._route_egress_release_recovery_speed_mps = max(
            0.01,
            float(self.get_parameter('route_egress_release_recovery_speed_mps').value),
        )
        self._route_egress_release_recovery_time_allowance_sec = max(
            0.5,
            float(self.get_parameter('route_egress_release_recovery_time_allowance_sec').value),
        )
        self._start_occupied_recovery_distance_m = max(
            0.0,
            float(self.get_parameter('start_occupied_recovery_distance_m').value),
        )
        self._start_occupied_recovery_speed_mps = max(
            0.01,
            float(self.get_parameter('start_occupied_recovery_speed_mps').value),
        )
        self._start_occupied_recovery_time_allowance_sec = max(
            0.5,
            float(self.get_parameter('start_occupied_recovery_time_allowance_sec').value),
        )
        self._start_occupied_recovery_limit = max(
            0,
            int(self.get_parameter('start_occupied_recovery_limit').value),
        )
        self._goal_soft_complete_xy_tolerance_m = max(
            0.0,
            float(self.get_parameter('goal_soft_complete_xy_tolerance_m').value),
        )
        self._runtime_pose_snapshot_max_age_sec = max(
            0.0,
            float(self.get_parameter('runtime_pose_snapshot_max_age_sec').value),
        )
        self._final_observation_stage_trigger_distance_m = max(
            0.0,
            float(self.get_parameter('final_observation_stage_trigger_distance_m').value),
        )
        self._final_observation_soft_complete_xy_tolerance_m = max(
            0.0,
            float(self.get_parameter('final_observation_soft_complete_xy_tolerance_m').value),
        )
        self._route_anchor_fallback_xy_tolerance_m = max(
            0.0,
            float(self.get_parameter('route_anchor_fallback_xy_tolerance_m').value),
        )
        self._simulation_pose_reset_recovery_enabled = bool(
            self.get_parameter('simulation_pose_reset_recovery_enabled').value
        )
        self._simulation_pose_reset_retry_limit = max(
            0,
            int(self.get_parameter('simulation_pose_reset_retry_limit').value),
        )
        self._simulation_pose_reset_retry_delay_sec = max(
            0.0,
            float(self.get_parameter('simulation_pose_reset_retry_delay_sec').value),
        )
        self._simulation_pose_reset_robot_model_name = str(
            self.get_parameter('simulation_pose_reset_robot_model_name').value
        ).strip() or 'agribot'
        self._gazebo_world_name = str(self.get_parameter('gazebo_world_name').value).strip()
        self._gazebo_partition = str(self.get_parameter('gazebo_partition').value).strip()
        self._gazebo_command_timeout_ms = max(
            1,
            int(self.get_parameter('gazebo_command_timeout_ms').value),
        )
        self._gz_executable = str(self.get_parameter('gz_executable').value).strip() or 'gz'
        self._initial_pose_topic = str(self.get_parameter('initial_pose_topic').value).strip() or '/initialpose'
        history_size = max(8, int(self.get_parameter('processed_command_history_size').value))

        self._plan = self._load_patrol_plan()
        self._navigate_client = ActionClient(self, NavigateToPose, self._action_name)
        self._navigate_through_client = ActionClient(
            self,
            NavigateThroughPoses,
            self._batch_action_name,
        )
        self._compute_path_client = ActionClient(
            self,
            ComputePathToPose,
            self._path_probe_action_name,
        )
        self._backup_client = ActionClient(self, BackUp, self._backup_action_name)
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
        self._initial_pose_publisher = self.create_publisher(
            PoseWithCovarianceStamped,
            self._initial_pose_topic,
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
        self._path_probe_send_future = None
        self._path_probe_result_future = None
        self._active_path_probe_handle = None
        self._active_path_probe_target_pose: CommandPose | None = None
        self._pending_final_observation_probe_targets: deque[CommandPose] = deque()
        self._recovery_send_future = None
        self._recovery_result_future = None
        self._recovery_cancel_future = None
        self._active_recovery_handle = None
        self._start_occupied_recovery_count = 0
        self._simulation_pose_reset_recovery_count = 0
        self._simulation_pose_reset_retry_timer = None
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
        # patrol 계획를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        plan_path = Path(str(self.get_parameter('patrol_waypoints_file').value)).expanduser()
        if not plan_path.is_absolute():
            plan_path = get_default_patrol_waypoints_path().parent.parent / plan_path
        return load_patrol_plan(plan_path)

    def _recover_previous_control_state(self) -> None:
        # recover previous 제어 상태 정보를 계산해 반환한다.
        if not self._control_state_path.exists():
            return

        try:
            payload = read_json_object(self._control_state_path)
        except (OSError, ValueError) as exc:
            self.get_logger().warning(f'기존 control state 파일을 읽지 못했습니다: {exc}')
            return

        self._control_state = ControlStateSnapshot.from_payload(payload)

    def _derive_active_activity(self) -> MotionActivity:
        # derive active activity 정보를 계산해 반환한다.
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
        # control 상태를 최신 상태로 갱신한다.
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
        # 제어 latch을 설정한다.
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
        # 제어 latch을 비운다.
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
        # control 상태를 파일이나 저장소에 기록한다.
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
        # resume context 정보를 계산해 반환한다.
        return self._control_state.resume_context

    def _is_patrol_resumable(self) -> bool:
        # patrol resumable인지 여부를 불리언 값으로 판단한다.
        return build_patrol_resume_context(self._latest_patrol_status) is not None

    def _recover_previous_command_status(self) -> None:
        # recover previous 명령 상태 정보를 계산해 반환한다.
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
        # remember processed 명령 id 정보를 계산해 반환한다.
        if command_id in self._processed_command_ids:
            return

        if len(self._processed_command_order) == self._processed_command_order.maxlen:
            oldest = self._processed_command_order.popleft()
            self._processed_command_ids.discard(oldest)

        self._processed_command_order.append(command_id)
        self._processed_command_ids.add(command_id)

    def _handle_patrol_status(self, msg: String) -> None:
        # handle patrol 상태 정보를 계산해 반환한다.
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
        # maybe finish patrol 상태 wait 정보를 계산해 반환한다.
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
        # patrol 상태 wait failure 메시지 정보를 계산해 반환한다.
        if self._latest_patrol_status is None or not self._latest_patrol_status.message:
            return '순찰 상태 전환이 실패했습니다.'
        return self._latest_patrol_status.message

    def _poll_command_file(self) -> None:
        # poll 명령 file 정보를 계산해 반환한다.
        self._release_orphaned_active_command_if_needed()

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
        # 명령 file signature 정보를 계산해 반환한다.
        stat_result = path.stat()
        return stat_result.st_mtime_ns, stat_result.st_size

    def _handle_invalid_command(self, exc: CommandValidationError) -> None:
        # handle invalid 명령 정보를 계산해 반환한다.
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

    def _has_pending_executor_activity(self) -> bool:
        # pending executor 활동 상태가 포함되어 있는지 여부를 판단한다.
        return any(
            value is not None
            for value in (
                self._goal_send_future,
                self._goal_result_future,
                self._active_goal_handle,
                self._goal_cancel_future,
                self._path_probe_send_future,
                self._path_probe_result_future,
                self._active_path_probe_handle,
                self._service_future,
                self._recovery_send_future,
                self._recovery_result_future,
                self._active_recovery_handle,
                self._recovery_cancel_future,
                self._goal_retry_timer,
                self._simulation_pose_reset_retry_timer,
                self._patrol_state_wait,
            )
        )

    def _release_orphaned_active_command_if_needed(self) -> None:
        # release orphaned active 명령 if needed 정보를 계산해 반환한다.
        if not should_release_orphaned_active_command(
            self._active_context,
            self._last_status_payload,
            has_pending_activity=self._has_pending_executor_activity(),
        ):
            return

        active_context = self._active_context
        if active_context is None:
            return

        self.get_logger().warning(
            '터미널 status가 이미 기록됐지만 내부 active context가 남아 있어 정리합니다: '
            f'{active_context.command.command_id}'
        )
        self._remember_processed_command_id(active_context.command.command_id)
        self._active_context = None
        self._active_goal_handle = None
        self._goal_send_future = None
        self._goal_result_future = None
        self._goal_cancel_future = None
        self._path_probe_send_future = None
        self._path_probe_result_future = None
        self._active_path_probe_handle = None
        self._active_path_probe_target_pose = None
        self._pending_final_observation_probe_targets.clear()
        self._service_future = None
        self._recovery_send_future = None
        self._recovery_result_future = None
        self._recovery_cancel_future = None
        self._active_recovery_handle = None
        self._start_occupied_recovery_count = 0
        self._simulation_pose_reset_recovery_count = 0
        self._patrol_state_wait = None
        self._navigation_cancel_reason = ''
        self._resume_release_pending = False
        self._goal_reject_retry_count = 0
        self._cancel_simulation_pose_reset_retry_timer()
        self._update_control_state()

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
        # NON active 명령 상태 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
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
        # pending context를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
        return ActiveCommandContext(
            command=command,
            received_at=_iso_now(),
            target_pose=command.target_pose,
            final_target_pose=command.target_pose,
            target_waypoint_id=command.inspect_waypoint_id or command.home_waypoint_id,
            home_waypoint_id=command.home_waypoint_id,
        )

    def _handle_command_while_active(self, command: ManualCommand) -> None:
        # handle 명령 while active 정보를 계산해 반환한다.
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
        # request 주행 preemption 정보를 계산해 반환한다.
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

        if self._active_recovery_handle is not None:
            self._request_active_recovery_cancel_for_preemption()
            return

        if self._recovery_send_future is not None or self._recovery_result_future is not None:
            self.get_logger().info(
                '새 이동 명령을 대기열에 올렸습니다. 현재 시작 위치 recovery가 끝나는 즉시 선점 전환합니다.'
            )
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
        # resume context FOR interruption를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
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
        # request 제어 interruption 정보를 계산해 반환한다.
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

        if self._active_recovery_handle is not None:
            self._request_active_recovery_cancel_for_preemption()
            return

        if self._recovery_send_future is not None or self._recovery_result_future is not None:
            self.get_logger().info(
                '제어 상태 전환 명령을 대기열에 올렸습니다. 시작 위치 recovery가 끝나는 즉시 적용합니다.'
            )
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
        # pending 명령 실행 흐름을 시작하거나 마무리한다.
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
        # 명령 실행 흐름을 시작하거나 마무리한다.
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
            context.target_waypoint_id = command.inspect_waypoint_id
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
            context.target_waypoint_id = home_waypoint_id
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
        # emergency stop 명령 실행 흐름을 시작하거나 마무리한다.
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
        # pause 명령 실행 흐름을 시작하거나 마무리한다.
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
        # resume 명령 실행 흐름을 시작하거나 마무리한다.
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
        context.target_waypoint_id = resume_context.target_waypoint_id or resume_context.home_waypoint_id
        context.target_pose = _coerce_pose(resume_context.target_pose, self._map_frame)
        context.route_target_pose = (
            _coerce_pose(resume_context.route_target_pose, self._map_frame)
            if isinstance(resume_context.route_target_pose, dict)
            else (
                context.target_pose
                if resume_context.navigation_phase == ManualNavigationPhase.ROUTE_ANCHOR.value
                else None
            )
        )
        context.final_target_pose = (
            _coerce_pose(resume_context.final_target_pose, self._map_frame)
            if isinstance(resume_context.final_target_pose, dict)
            else context.target_pose
        )
        context.navigation_phase = (
            ManualNavigationPhase(resume_context.navigation_phase)
            if resume_context.navigation_phase in {item.value for item in ManualNavigationPhase}
            else ManualNavigationPhase.FINAL_OBSERVATION
        )
        self._resume_release_pending = True
        if self._schedule_resume_release_recovery(context):
            return
        self._start_navigation_command(
            context,
            target_pose=context.target_pose,
            label='저장된 수동 이동 재개',
            preserve_navigation_plan=True,
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
        # call patrol 서비스 wait 정보를 계산해 반환한다.
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

    def _observation_candidate_waypoint_ids(
        self,
        context: ActiveCommandContext,
    ) -> tuple[str, ...]:
        # 관측 후보 웨이포인트 ids 정보를 계산해 반환한다.
        candidate_ids = [
            candidate.inspect_waypoint_id
            for candidate in context.command.observation_candidates
            if candidate.inspect_waypoint_id in self._plan.waypoints
        ]
        if candidate_ids:
            return tuple(dict.fromkeys(candidate_ids))

        if context.command.inspect_waypoint_ids:
            return tuple(
                dict.fromkeys(
                    waypoint_id
                    for waypoint_id in context.command.inspect_waypoint_ids
                    if waypoint_id in self._plan.waypoints
                )
            )

        if context.command.inspect_waypoint_id and context.command.inspect_waypoint_id in self._plan.waypoints:
            return (context.command.inspect_waypoint_id,)

        return ()

    def _selected_observation_candidate(
        self,
        context: ActiveCommandContext,
        selected_waypoint_id: str | None,
    ) -> ObservationGoalCandidate | None:
        # selected 관측 후보 정보를 계산해 반환한다.
        if not selected_waypoint_id:
            return None

        for candidate in context.command.observation_candidates:
            if candidate.inspect_waypoint_id == selected_waypoint_id:
                return candidate
        return None

    def _configure_navigation_targets(
        self,
        context: ActiveCommandContext,
        requested_target_pose: CommandPose,
    ) -> None:
        # configure 주행 대상 정보를 계산해 반환한다.
        current_pose = read_runtime_pose_snapshot(
            self._runtime_dir,
            expected_frame=self._map_frame,
            max_age_sec=self._runtime_pose_snapshot_max_age_sec,
        )
        candidate_waypoint_ids = self._observation_candidate_waypoint_ids(context)
        selected_waypoint_id = select_best_target_waypoint_id(
            self._plan,
            current_pose=current_pose,
            candidate_waypoint_ids=candidate_waypoint_ids,
            preferred_waypoint_id=context.command.inspect_waypoint_id,
        )
        selected_waypoint = self._plan.waypoints.get(selected_waypoint_id) if selected_waypoint_id else None
        selected_candidate = self._selected_observation_candidate(context, selected_waypoint_id)

        context.final_target_pose = (
            selected_candidate.final_target_pose
            if selected_candidate is not None
            else requested_target_pose
        )
        context.route_target_pose = (
            self._command_pose_from_pose2d(selected_waypoint.pose)
            if selected_waypoint is not None
            else None
        )
        context.target_waypoint_id = (
            selected_waypoint_id
            or context.command.inspect_waypoint_id
            or context.home_waypoint_id
        )

        if selected_waypoint_id and context.command.inspect_waypoint_id != selected_waypoint_id:
            self.get_logger().info(
                '식물 관측 후보 중 현재 위치에서 가장 효율적인 waypoint를 선택했습니다. '
                f'plant_id={context.command.plant_id or "-"}, '
                f'selected={selected_waypoint_id}, '
                f'preferred={context.command.inspect_waypoint_id or "-"}'
            )

        egress_waypoint_id = select_route_egress_waypoint_id(
            self._plan,
            current_pose,
        )
        if egress_waypoint_id:
            egress_pose = self._command_pose_from_pose2d(self._plan.waypoints[egress_waypoint_id].pose)
            if (
                context.route_target_pose is None
                or pose_distance_xy(egress_pose, context.route_target_pose) > 0.05
            ):
                context.navigation_phase = ManualNavigationPhase.ROUTE_EGRESS
                context.target_pose = egress_pose
                context.route_egress_release_attempted = False
                self.get_logger().info(
                    '작물 옆 최종 관측 위치에서 새 장거리 이동을 시작해 먼저 안전 통로로 복귀합니다. '
                    f'plant_id={context.command.plant_id or "-"}, '
                    f'egress_waypoint={egress_waypoint_id}, '
                    f'egress_pose=({egress_pose.x:.2f}, {egress_pose.y:.2f}), '
                    f'final_waypoint={context.target_waypoint_id or "-"}'
                )
                return

        if self._is_two_stage_observation(context):
            context.navigation_phase = ManualNavigationPhase.ROUTE_ANCHOR
            context.target_pose = context.route_target_pose
            return

        context.navigation_phase = ManualNavigationPhase.FINAL_OBSERVATION
        context.target_pose = context.final_target_pose

    def _is_two_stage_observation(self, context: ActiveCommandContext) -> bool:
        # TWO stage 관측 결과인지 여부를 불리언 값으로 판단한다.
        return (
            context.route_target_pose is not None
            and context.final_target_pose is not None
            and pose_distance_xy(context.route_target_pose, context.final_target_pose)
            > self._final_observation_stage_trigger_distance_m
        )

    def _dispatch_current_navigation_stage(
        self,
        context: ActiveCommandContext,
        *,
        label: str,
        is_retry: bool,
    ) -> None:
        # current navigation stage를 외부 시스템이나 다음 처리 단계로 전달한다.
        if (
            context.navigation_phase is ManualNavigationPhase.ROUTE_EGRESS
            and context.target_pose is not None
        ):
            if self._schedule_route_egress_release_recovery(context):
                return
            self._dispatch_route_egress_goal(
                context,
                target_pose=context.target_pose,
                label=label,
                is_retry=is_retry,
            )
            return

        if (
            context.navigation_phase is ManualNavigationPhase.FINAL_OBSERVATION
            and self._is_two_stage_observation(context)
            and context.final_target_pose is not None
        ):
            self._dispatch_final_observation_goal(
                context,
                target_pose=context.final_target_pose,
                label=label,
                is_retry=is_retry,
            )
            return

        active_target_pose = context.target_pose or context.final_target_pose
        self._dispatch_navigation_goal(
            context,
            target_pose=active_target_pose,
            label=label,
            is_retry=is_retry,
        )

    def _start_navigation_command(
        self,
        context: ActiveCommandContext,
        *,
        target_pose: CommandPose | None,
        label: str,
        preserve_navigation_plan: bool = False,
    ) -> None:
        # navigation 명령 실행 흐름을 시작하거나 마무리한다.
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
        self._start_occupied_recovery_count = 0
        self._simulation_pose_reset_recovery_count = 0
        self._cancel_simulation_pose_reset_retry_timer()
        if preserve_navigation_plan:
            context.target_pose = target_pose
            context.final_target_pose = context.final_target_pose or target_pose
            context.navigation_phase = context.navigation_phase or ManualNavigationPhase.FINAL_OBSERVATION
        else:
            self._configure_navigation_targets(context, target_pose)
        self._update_control_state()
        if context.command.preempt_current_navigation:
            self._prepare_navigation_preemption(context, label=label)
            return
        self._dispatch_current_navigation_stage(
            context,
            label=label,
            is_retry=False,
        )

    def _prepare_navigation_preemption(
        self,
        context: ActiveCommandContext,
        *,
        label: str,
    ) -> None:
        # prepare 주행 preemption 정보를 계산해 반환한다.
        if not self._patrol_stop_client.wait_for_service(timeout_sec=self._patrol_service_wait_sec):
            self.get_logger().warning(
                '순찰 중지 서비스를 찾지 못해 stop 확인 없이 새 이동 명령을 실행합니다.'
            )
            self._dispatch_current_navigation_stage(
                context,
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
        # handle pre 주행 patrol stop response 정보를 계산해 반환한다.
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
            self._dispatch_current_navigation_stage(
                context,
                label=label,
                is_retry=False,
            )
            return

        if not response.success:
            self.get_logger().info(
                f'순찰 중지 선행 호출 응답: {response.message or "추가 메시지 없음"}. '
                '새 이동 명령은 계속 실행합니다.'
            )

        self._dispatch_current_navigation_stage(
            context,
            label=label,
            is_retry=False,
        )

    def _command_pose_from_pose2d(self, pose: Pose2D) -> CommandPose:
        # 명령 위치 자세 2 d 정보를 계산해 반환한다.
        return CommandPose(
            x=pose.x,
            y=pose.y,
            z=pose.z,
            yaw=pose.yaw,
            frame_id=self._plan.frame_id,
        )

    def _resolve_navigation_route(
        self,
        context: ActiveCommandContext,
        target_pose: CommandPose,
    ) -> ManualNavigationRoute:
        # 현재 입력 조건을 바탕으로 navigation 경로를 계산하거나 결정한다.
        current_pose = read_runtime_pose_snapshot(
            self._runtime_dir,
            expected_frame=self._map_frame,
            max_age_sec=self._runtime_pose_snapshot_max_age_sec,
        )
        route = build_manual_navigation_route(
            self._plan,
            current_pose=current_pose,
            target_pose=target_pose.as_pose2d(),
            explicit_waypoint_id=context.target_waypoint_id,
        )
        if route.target_waypoint_id:
            context.target_waypoint_id = route.target_waypoint_id
        if route.poses:
            context.target_pose = self._command_pose_from_pose2d(route.poses[-1])
        if route.waypoint_ids:
            self.get_logger().info(
                '수동 이동 경로를 patrol waypoint 기준으로 재해석했습니다. '
                f'target_waypoint={context.target_waypoint_id or "-"}, '
                f'route={" -> ".join(route.waypoint_ids)}'
            )
        return route

    def _dispatch_navigation_batch_goal(
        self,
        context: ActiveCommandContext,
        *,
        route: ManualNavigationRoute,
        label: str,
        is_retry: bool,
    ) -> None:
        # navigation batch 목표를 외부 시스템이나 다음 처리 단계로 전달한다.
        if not self._navigate_through_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self._finish_active_command(
                'failed',
                f'NavigateThroughPoses action server를 찾지 못했습니다: {self._batch_action_name}',
                error='navigate_through_action_unavailable',
            )
            return

        if context.started_at is None:
            context.started_at = _iso_now()

        goal = NavigateThroughPoses.Goal()
        goal.poses = [self._build_pose_stamped(pose) for pose in route.poses]
        goal.behavior_tree = ''

        if is_retry:
            message = (
                f'{label} 안전 경로 재시도 중입니다. '
                f'({self._goal_reject_retry_count}/{self._goal_reject_retry_limit})'
            )
        else:
            message = f'{label} 안전 경로를 실행 중입니다.'

        self._write_status(self._build_status_payload(context, 'running', message))
        self._goal_send_future = self._navigate_through_client.send_goal_async(goal)
        self._goal_send_future.add_done_callback(self._handle_navigation_goal_response)

    def _probe_final_observation_path(
        self,
        context: ActiveCommandContext,
        *,
        label: str,
        is_retry: bool,
    ) -> None:
        # probe 최종 관측 경로 정보를 계산해 반환한다.
        if context.final_target_pose is None:
            self._finish_active_command(
                'failed',
                '최종 관측 위치가 없어 작물 앞 접근을 이어갈 수 없습니다.',
                error='missing_final_target_pose',
            )
            return

        if not self._compute_path_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self.get_logger().warning(
                f'ComputePathToPose action server를 찾지 못해 {label} 최종 접근 경로 탐색을 건너뜁니다.'
            )
            self._dispatch_final_observation_goal(
                context,
                target_pose=context.final_target_pose,
                label=label,
                is_retry=is_retry,
            )
            return
        self._pending_final_observation_probe_targets = deque(
            (
                context.final_target_pose,
                *build_intermediate_final_observation_targets(
                    context.route_target_pose,
                    context.final_target_pose,
                ),
            )
        )
        self._dispatch_next_final_observation_path_probe(
            context,
            label=label,
            is_retry=is_retry,
        )

    def _dispatch_next_final_observation_path_probe(
        self,
        context: ActiveCommandContext,
        *,
        label: str,
        is_retry: bool,
    ) -> None:
        # next final 관측 결과 경로 probe를 외부 시스템이나 다음 처리 단계로 전달한다.
        if context is not self._active_context:
            return

        if not self._pending_final_observation_probe_targets:
            if should_complete_route_anchor_only(
                current_pose=read_runtime_pose_snapshot(
                    self._runtime_dir,
                    expected_frame=self._map_frame,
                    max_age_sec=self._runtime_pose_snapshot_max_age_sec,
                ),
                route_target_pose=context.route_target_pose,
                final_path_available=False,
                xy_tolerance_m=self._route_anchor_fallback_xy_tolerance_m,
            ):
                self._finish_active_command(
                    'succeeded',
                    '안전 관측 경유점까지는 도착했고, 울타리 방향으로 더 들어갈 수 있는 근접 경로도 찾지 못해 현재 위치에서 접근을 마쳤습니다.',
                    result='anchor_only',
                )
                return
            self._dispatch_final_observation_goal(
                context,
                target_pose=context.final_target_pose,
                label=label,
                is_retry=is_retry,
            )
            return

        probe_target_pose = self._pending_final_observation_probe_targets.popleft()
        self._active_path_probe_target_pose = probe_target_pose
        probe_goal = ComputePathToPose.Goal()
        probe_goal.goal = self._build_pose_stamped(probe_target_pose.as_pose2d())
        probe_goal.planner_id = ''
        probe_goal.use_start = False

        is_primary_probe = (
            pose_distance_xy(probe_target_pose, context.final_target_pose) <= 0.05
        )
        status_message = (
            f'{label} 최종 관측 경로 가능 여부를 확인 중입니다.'
            if is_primary_probe
            else (
                f'{label} 울타리 쪽으로 더 가까운 대체 관측 지점을 탐색 중입니다. '
                f'(x={probe_target_pose.x:.2f}, y={probe_target_pose.y:.2f})'
            )
        )
        self._write_status(
            self._build_status_payload(
                context,
                'running',
                status_message,
            )
        )
        self._path_probe_send_future = self._compute_path_client.send_goal_async(probe_goal)
        self._path_probe_send_future.add_done_callback(
            lambda future, dispatch_label=label, retry_flag=is_retry: self._handle_final_observation_probe_goal_response(
                future,
                label=dispatch_label,
                is_retry=retry_flag,
            )
        )

    def _handle_final_observation_probe_goal_response(
        self,
        future: Any,
        *,
        label: str,
        is_retry: bool,
    ) -> None:
        # handle 최종 관측 probe 목표 response 정보를 계산해 반환한다.
        self._path_probe_send_future = None
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f'최종 관측 경로 확인 goal 전송에 실패했습니다. 다음 대체 지점이 있으면 이어서 확인합니다: {exc}'
            )
            context = self._active_context
            if context is not None and context.final_target_pose is not None:
                self._dispatch_next_final_observation_path_probe(
                    context,
                    label=label,
                    is_retry=is_retry,
                )
            return

        if not goal_handle.accepted:
            self.get_logger().warning(
                '최종 관측 경로 확인 goal이 거부됐습니다. 다음 대체 지점이 있으면 이어서 확인합니다.'
            )
            context = self._active_context
            if context is not None and context.final_target_pose is not None:
                self._dispatch_next_final_observation_path_probe(
                    context,
                    label=label,
                    is_retry=is_retry,
                )
            return

        self._active_path_probe_handle = goal_handle
        self._path_probe_result_future = goal_handle.get_result_async()
        self._path_probe_result_future.add_done_callback(
            lambda result_future, dispatch_label=label, retry_flag=is_retry: self._handle_final_observation_probe_result(
                result_future,
                label=dispatch_label,
                is_retry=retry_flag,
            )
        )

    def _handle_final_observation_probe_result(
        self,
        future: Any,
        *,
        label: str,
        is_retry: bool,
    ) -> None:
        # handle 최종 관측 probe 결과 정보를 계산해 반환한다.
        self._active_path_probe_handle = None
        self._path_probe_result_future = None
        context = self._active_context
        if context is None or context.final_target_pose is None:
            self._active_path_probe_target_pose = None
            return

        probe_target_pose = self._active_path_probe_target_pose or context.final_target_pose
        self._active_path_probe_target_pose = None

        final_path_available = False
        try:
            result = future.result()
            path_payload = getattr(result.result, 'path', None)
            final_path_available = bool(path_payload and getattr(path_payload, 'poses', None))
        except Exception as exc:
            self.get_logger().warning(
                f'최종 관측 경로 확인 결과를 받지 못했습니다. 다음 대체 지점이 있으면 이어서 확인합니다: {exc}'
            )
            self._dispatch_next_final_observation_path_probe(
                context,
                label=label,
                is_retry=is_retry,
            )
            return

        if not final_path_available:
            self._dispatch_next_final_observation_path_probe(
                context,
                label=label,
                is_retry=is_retry,
            )
            return

        self._dispatch_final_observation_goal(
            context,
            target_pose=probe_target_pose,
            label=label,
            is_retry=is_retry,
        )

    def _dispatch_route_egress_goal(
        self,
        context: ActiveCommandContext,
        *,
        target_pose: CommandPose,
        label: str,
        is_retry: bool,
    ) -> None:
        # 경로 egress 목표를 외부 시스템이나 다음 처리 단계로 전달한다.
        if not self._navigate_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self._finish_active_command(
                'failed',
                f'NavigateToPose action server를 찾지 못했습니다: {self._action_name}',
                error='navigate_action_unavailable',
            )
            return

        context.target_pose = target_pose
        context.navigation_phase = ManualNavigationPhase.ROUTE_EGRESS
        if context.started_at is None:
            context.started_at = _iso_now()

        goal = NavigateToPose.Goal()
        goal.pose = self._build_pose_stamped(target_pose.as_pose2d())
        goal.behavior_tree = ''

        if is_retry:
            message = (
                f'{label} 안전 통로 복귀를 재시도 중입니다. '
                f'({self._goal_reject_retry_count}/{self._goal_reject_retry_limit})'
            )
        else:
            message = f'{label} 새 장거리 경로를 위해 안전 통로로 복귀 중입니다.'

        self._write_status(self._build_status_payload(context, 'running', message))
        self._goal_send_future = self._navigate_client.send_goal_async(goal)
        self._goal_send_future.add_done_callback(self._handle_navigation_goal_response)

    def _dispatch_final_observation_goal(
        self,
        context: ActiveCommandContext,
        *,
        target_pose: CommandPose,
        label: str,
        is_retry: bool,
    ) -> None:
        # final 관측 결과 목표를 외부 시스템이나 다음 처리 단계로 전달한다.
        if not self._navigate_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self._finish_active_command(
                'failed',
                f'NavigateToPose action server를 찾지 못했습니다: {self._action_name}',
                error='navigate_action_unavailable',
            )
            return

        self._active_path_probe_target_pose = None
        self._pending_final_observation_probe_targets.clear()
        context.target_pose = target_pose
        context.navigation_phase = ManualNavigationPhase.FINAL_OBSERVATION
        if context.started_at is None:
            context.started_at = _iso_now()

        goal = NavigateToPose.Goal()
        goal.pose = self._build_pose_stamped(target_pose.as_pose2d())
        goal.behavior_tree = ''

        if is_retry:
            message = (
                f'{label} 최종 관측 접근을 재시도 중입니다. '
                f'({self._goal_reject_retry_count}/{self._goal_reject_retry_limit})'
            )
        else:
            message = f'{label} 최종 관측 위치로 접근 중입니다.'

        self._write_status(self._build_status_payload(context, 'running', message))
        self._goal_send_future = self._navigate_client.send_goal_async(goal)
        self._goal_send_future.add_done_callback(self._handle_navigation_goal_response)

    def _dispatch_navigation_goal(
        self,
        context: ActiveCommandContext,
        *,
        target_pose: CommandPose,
        label: str,
        is_retry: bool,
    ) -> None:
        # navigation 목표를 외부 시스템이나 다음 처리 단계로 전달한다.
        route = self._resolve_navigation_route(context, target_pose)
        if len(route.poses) > 1:
            self._dispatch_navigation_batch_goal(
                context,
                route=route,
                label=label,
                is_retry=is_retry,
            )
            return

        if not self._navigate_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self._finish_active_command(
                'failed',
                f'NavigateToPose action server를 찾지 못했습니다: {self._action_name}',
                error='navigate_action_unavailable',
            )
            return

        if route.poses:
            context.target_pose = self._command_pose_from_pose2d(route.poses[-1])
        else:
            context.target_pose = target_pose
        if context.started_at is None:
            context.started_at = _iso_now()

        goal = NavigateToPose.Goal()
        goal.pose = self._build_pose_stamped(context.target_pose.as_pose2d())
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
        # cancel outcome pending transition 정보를 계산해 반환한다.
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
        # handle 주행 목표 response 정보를 계산해 반환한다.
        self._goal_send_future = None
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._finish_active_command(
                'failed',
                f'주행 goal 전송에 실패했습니다: {exc}',
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
                '주행 goal이 반복해서 거부되었습니다. 현재 로봇 위치 추정과 TF 상태를 확인하세요.',
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
        # handle 주행 결과 정보를 계산해 반환한다.
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
        active_context = self._active_context
        in_final_observation_stage = (
            active_context is not None
            and active_context.navigation_phase is ManualNavigationPhase.FINAL_OBSERVATION
            and self._is_two_stage_observation(active_context)
        )
        using_adjusted_final_observation_target = (
            in_final_observation_stage
            and active_context is not None
            and active_context.target_pose is not None
            and active_context.final_target_pose is not None
            and pose_distance_xy(active_context.target_pose, active_context.final_target_pose) > 0.05
        )

        if status == GoalStatus.STATUS_SUCCEEDED:
            self._start_occupied_recovery_count = 0
            if (
                active_context is not None
                and active_context.navigation_phase is ManualNavigationPhase.ROUTE_EGRESS
            ):
                if self._is_two_stage_observation(active_context):
                    active_context.navigation_phase = ManualNavigationPhase.ROUTE_ANCHOR
                    active_context.target_pose = active_context.route_target_pose
                else:
                    active_context.navigation_phase = ManualNavigationPhase.FINAL_OBSERVATION
                    active_context.target_pose = active_context.final_target_pose
                self._dispatch_current_navigation_stage(
                    active_context,
                    label=describe_manual_navigation_label(
                        active_context.command.command_type,
                        active_context.home_waypoint_id,
                    ),
                    is_retry=False,
                )
                return
            if (
                active_context is not None
                and active_context.navigation_phase is ManualNavigationPhase.ROUTE_ANCHOR
                and self._is_two_stage_observation(active_context)
                and active_context.final_target_pose is not None
            ):
                self._probe_final_observation_path(
                    active_context,
                    label=describe_manual_navigation_label(
                        active_context.command.command_type,
                        active_context.home_waypoint_id,
                    ),
                    is_retry=False,
                )
                return

            success_message = (
                '울타리 쪽으로 갈 수 있는 최대 근접 관측 위치까지 이동을 완료했습니다.'
                if using_adjusted_final_observation_target
                else '최종 관측 위치까지 이동을 완료했습니다.'
                if in_final_observation_stage
                else '이동 명령이 완료되었습니다.'
            )
            self._finish_active_command('succeeded', success_message)
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

        if should_treat_failed_navigation_as_success(
            self._runtime_dir,
            expected_frame=self._map_frame,
            target_pose=active_context.target_pose if active_context is not None else None,
            xy_tolerance_m=(
                self._final_observation_soft_complete_xy_tolerance_m
                if in_final_observation_stage
                else self._goal_soft_complete_xy_tolerance_m
            ),
            max_snapshot_age_sec=self._runtime_pose_snapshot_max_age_sec,
        ):
            self._start_occupied_recovery_count = 0
            self._finish_active_command(
                'succeeded',
                (
                    '울타리 쪽 근접 관측 위치 허용 오차 안으로 들어와 작물 앞 접근을 완료한 것으로 처리했습니다.'
                    if using_adjusted_final_observation_target
                    else '최종 관측 위치 근처의 허용 오차 안으로 들어와 작물 앞 접근을 완료한 것으로 처리했습니다.'
                    if in_final_observation_stage
                    else '목표 좌표 근처의 안전 허용 오차 안으로 들어와 이동을 완료한 것으로 처리했습니다.'
                ),
            )
            return

        if in_final_observation_stage and active_context is not None:
            current_pose = read_runtime_pose_snapshot(
                self._runtime_dir,
                expected_frame=self._map_frame,
                max_age_sec=self._runtime_pose_snapshot_max_age_sec,
            )
            if should_complete_route_anchor_only(
                current_pose=current_pose,
                route_target_pose=active_context.route_target_pose,
                final_path_available=False,
                xy_tolerance_m=self._route_anchor_fallback_xy_tolerance_m,
            ):
                self._finish_active_command(
                    'succeeded',
                    '안전 관측 경유점까지는 도착했지만 울타리 근접 구간 충돌 위험으로 최종 작물 접근은 생략했습니다.',
                    result='anchor_only',
                )
                return

        if should_attempt_route_egress_simulation_pose_reset(active_context):
            if self._schedule_simulation_pose_reset_recovery():
                return

        if not in_final_observation_stage and _navigation_result_indicates_start_occupied(nav_result):
            if self._schedule_simulation_pose_reset_recovery():
                return
            if self._schedule_start_occupied_recovery():
                return
        if _navigation_result_indicates_transient_tf_error(nav_result):
            if self._schedule_transient_navigation_retry():
                return

        message = _navigation_failure_message(nav_result)
        self._finish_active_command('failed', message, error='navigate_failed')

    def _schedule_start_occupied_recovery(self) -> bool:
        # start occupied recovery를 어떤 순서와 조건으로 처리할지 계획한다.
        context = self._active_context
        if context is None or context.target_pose is None:
            return False
        if self._start_occupied_recovery_distance_m <= 0.0:
            return False
        if not should_retry_start_occupied_recovery(
            self._start_occupied_recovery_count,
            self._start_occupied_recovery_limit,
        ):
            return False
        if not self._backup_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self.get_logger().warning(
                f'시작 위치 recovery용 {self._backup_action_name} action server를 찾지 못했습니다.'
            )
            return False

        self._start_occupied_recovery_count += 1
        recovery_label = (
            '현재 위치가 통로 가장자리에 걸려 있어 잠시 후진한 뒤 목표를 다시 시도합니다. '
            f'({self._start_occupied_recovery_count}/{self._start_occupied_recovery_limit})'
        )
        self.get_logger().warning(recovery_label)
        self._write_status(self._build_status_payload(context, 'running', recovery_label))

        goal = BackUp.Goal()
        goal.target = Point(x=float(self._start_occupied_recovery_distance_m))
        goal.speed = float(self._start_occupied_recovery_speed_mps)
        goal.time_allowance = Duration(
            seconds=float(self._start_occupied_recovery_time_allowance_sec)
        ).to_msg()
        self._recovery_send_future = self._backup_client.send_goal_async(goal)
        self._recovery_send_future.add_done_callback(self._handle_start_occupied_recovery_goal_response)
        return True

    def _schedule_resume_release_recovery(self, context: ActiveCommandContext) -> bool:
        # resume release recovery를 어떤 순서와 조건으로 처리할지 계획한다.
        if not should_run_resume_release_recovery(
            context,
            distance_m=self._resume_release_recovery_distance_m,
        ):
            return False
        if not self._backup_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self.get_logger().warning(
                f'재개 직전 안전 후진용 {self._backup_action_name} action server를 찾지 못해 '
                '원래 목표를 바로 다시 시도합니다.'
            )
            return False

        recovery_label = (
            '일시정지된 위치에서 바로 재출발하면 충돌로 판정될 수 있어 '
            '잠시 후진한 뒤 저장된 목적지를 다시 시도합니다.'
        )
        self.get_logger().info(recovery_label)
        self._write_status(self._build_status_payload(context, 'running', recovery_label))

        goal = BackUp.Goal()
        goal.target = Point(x=float(self._resume_release_recovery_distance_m))
        goal.speed = float(self._resume_release_recovery_speed_mps)
        goal.time_allowance = Duration(
            seconds=float(self._resume_release_recovery_time_allowance_sec)
        ).to_msg()
        self._recovery_send_future = self._backup_client.send_goal_async(goal)
        self._recovery_send_future.add_done_callback(self._handle_resume_release_recovery_goal_response)
        return True

    def _schedule_route_egress_release_recovery(self, context: ActiveCommandContext) -> bool:
        # 경로 egress release recovery를 어떤 순서와 조건으로 처리할지 계획한다.
        if not should_run_route_egress_release_recovery(
            context,
            distance_m=self._route_egress_release_recovery_distance_m,
        ):
            return False
        if not self._backup_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self.get_logger().warning(
                f'crop-side egress용 {self._backup_action_name} action server를 찾지 못해 '
                '안전 통로 복귀 goal을 바로 시도합니다.'
            )
            return False

        context.route_egress_release_attempted = True
        recovery_label = (
            '작물 옆 최종 관측 위치에서 바로 새 경로를 시작하면 충돌로 판정될 수 있어 '
            '통로 쪽으로 잠시 후진한 뒤 안전 통로 복귀를 시도합니다.'
        )
        self.get_logger().info(recovery_label)
        self._write_status(self._build_status_payload(context, 'running', recovery_label))

        goal = BackUp.Goal()
        goal.target = Point(x=float(self._route_egress_release_recovery_distance_m))
        goal.speed = float(self._route_egress_release_recovery_speed_mps)
        goal.time_allowance = Duration(
            seconds=float(self._route_egress_release_recovery_time_allowance_sec)
        ).to_msg()
        self._recovery_send_future = self._backup_client.send_goal_async(goal)
        self._recovery_send_future.add_done_callback(self._handle_route_egress_release_recovery_goal_response)
        return True

    def _handle_resume_release_recovery_goal_response(self, future: Any) -> None:
        # handle resume release recovery 목표 response 정보를 계산해 반환한다.
        self._recovery_send_future = None
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f'재개 직전 안전 후진 goal 전송에 실패해 원래 목표를 바로 다시 시도합니다: {exc}'
            )
            self._resume_navigation_after_release_recovery()
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
            self.get_logger().warning(
                '재개 직전 안전 후진 goal이 거부되어 원래 목표를 바로 다시 시도합니다.'
            )
            self._resume_navigation_after_release_recovery()
            return

        self._active_recovery_handle = goal_handle
        self._recovery_result_future = goal_handle.get_result_async()
        self._recovery_result_future.add_done_callback(self._handle_resume_release_recovery_result)

    def _handle_resume_release_recovery_result(self, future: Any) -> None:
        # handle resume release recovery 결과 정보를 계산해 반환한다.
        self._active_recovery_handle = None
        self._recovery_result_future = None

        if self._pending_context is not None:
            cancel_message, cancel_error = self._cancel_outcome_for_pending_transition()
            self._finish_active_command(
                'canceled',
                cancel_message,
                error=cancel_error,
            )
            return

        try:
            result = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f'재개 직전 안전 후진 결과를 받지 못해 원래 목표를 바로 다시 시도합니다: {exc}'
            )
            self._resume_navigation_after_release_recovery()
            return

        if result.status != GoalStatus.STATUS_SUCCEEDED:
            recovery_result = result.result
            error_msg = str(getattr(recovery_result, 'error_msg', '') or '').strip()
            error_code = int(getattr(recovery_result, 'error_code', BackUp.Result.UNKNOWN) or 0)
            detail = error_msg or '후진으로 충분한 여유 공간을 만들지 못했습니다.'
            self.get_logger().warning(
                '재개 직전 안전 후진이 실패했지만 저장된 목적지는 유지한 채 '
                f'원래 목표를 다시 시도합니다: {detail} (error_code={error_code})'
            )

        self._resume_navigation_after_release_recovery()

    def _handle_route_egress_release_recovery_goal_response(self, future: Any) -> None:
        # handle 경로 egress release recovery 목표 response 정보를 계산해 반환한다.
        self._recovery_send_future = None
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f'crop-side egress 전 안전 후진 goal 전송에 실패해 바로 통로 복귀를 시도합니다: {exc}'
            )
            self._resume_navigation_after_route_egress_release_recovery()
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
            self.get_logger().warning(
                'crop-side egress 전 안전 후진 goal이 거부되어 바로 통로 복귀를 시도합니다.'
            )
            self._resume_navigation_after_route_egress_release_recovery()
            return

        self._active_recovery_handle = goal_handle
        self._recovery_result_future = goal_handle.get_result_async()
        self._recovery_result_future.add_done_callback(self._handle_route_egress_release_recovery_result)

    def _handle_route_egress_release_recovery_result(self, future: Any) -> None:
        # handle 경로 egress release recovery 결과 정보를 계산해 반환한다.
        self._active_recovery_handle = None
        self._recovery_result_future = None

        if self._pending_context is not None:
            cancel_message, cancel_error = self._cancel_outcome_for_pending_transition()
            self._finish_active_command(
                'canceled',
                cancel_message,
                error=cancel_error,
            )
            return

        try:
            result = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f'crop-side egress 전 안전 후진 결과를 받지 못해 바로 통로 복귀를 시도합니다: {exc}'
            )
            self._resume_navigation_after_route_egress_release_recovery()
            return

        if result.status != GoalStatus.STATUS_SUCCEEDED:
            recovery_result = result.result
            error_msg = str(getattr(recovery_result, 'error_msg', '') or '').strip()
            error_code = int(getattr(recovery_result, 'error_code', BackUp.Result.UNKNOWN) or 0)
            detail = error_msg or '후진으로 충분한 통로 여유를 만들지 못했습니다.'
            self.get_logger().warning(
                'crop-side egress 전 안전 후진이 실패했지만 '
                f'통로 복귀 goal은 계속 시도합니다: {detail} (error_code={error_code})'
            )

        self._resume_navigation_after_route_egress_release_recovery()

    def _resume_navigation_after_release_recovery(self) -> None:
        # resume 주행 after release recovery 정보를 계산해 반환한다.
        context = self._active_context
        if context is None or context.target_pose is None:
            return
        self._dispatch_current_navigation_stage(
            context,
            label='저장된 수동 이동 재개',
            is_retry=True,
        )

    def _resume_navigation_after_route_egress_release_recovery(self) -> None:
        # resume 주행 after 경로 egress release recovery 정보를 계산해 반환한다.
        context = self._active_context
        if context is None or context.target_pose is None:
            return
        self._dispatch_current_navigation_stage(
            context,
            label=describe_manual_navigation_label(
                context.command.command_type,
                context.home_waypoint_id,
            ),
            is_retry=True,
        )

    def _handle_start_occupied_recovery_goal_response(self, future: Any) -> None:
        # handle start occupied recovery 목표 response 정보를 계산해 반환한다.
        self._recovery_send_future = None
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._finish_active_command(
                'failed',
                f'시작 위치 recovery goal 전송에 실패했습니다: {exc}',
                error='start_occupied_recovery_send_failed',
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
            self._finish_active_command(
                'failed',
                '시작 위치 recovery가 거부되어 새 이동을 계속할 수 없습니다.',
                error='start_occupied_recovery_rejected',
            )
            return

        self._active_recovery_handle = goal_handle
        self._recovery_result_future = goal_handle.get_result_async()
        self._recovery_result_future.add_done_callback(self._handle_start_occupied_recovery_result)

    def _handle_start_occupied_recovery_result(self, future: Any) -> None:
        # handle start occupied recovery 결과 정보를 계산해 반환한다.
        self._active_recovery_handle = None
        self._recovery_result_future = None

        if self._pending_context is not None:
            cancel_message, cancel_error = self._cancel_outcome_for_pending_transition()
            self._finish_active_command(
                'canceled',
                cancel_message,
                error=cancel_error,
            )
            return

        context = self._active_context
        if context is None or context.target_pose is None:
            return

        try:
            result = future.result()
        except Exception as exc:
            self._finish_active_command(
                'failed',
                f'시작 위치 recovery 결과 수신에 실패했습니다: {exc}',
                error='start_occupied_recovery_result_failed',
            )
            return

        if result.status != GoalStatus.STATUS_SUCCEEDED:
            recovery_result = result.result
            error_msg = str(getattr(recovery_result, 'error_msg', '') or '').strip()
            error_code = int(getattr(recovery_result, 'error_code', BackUp.Result.UNKNOWN) or 0)
            detail = error_msg or '후진 recovery로도 통로를 확보하지 못했습니다.'
            if self._schedule_simulation_pose_reset_recovery():
                return
            self._finish_active_command(
                'failed',
                f'시작 위치 recovery가 실패했습니다: {detail} (error_code={error_code})',
                error='start_occupied_recovery_failed',
            )
            return

        retry_label = describe_manual_navigation_label(
            context.command.command_type,
            context.home_waypoint_id,
        )
        self._dispatch_current_navigation_stage(
            context,
            label=retry_label,
            is_retry=True,
        )

    def _build_gazebo_robot_pose_request(self, pose: CommandPose) -> str:
        # gazebo robot 위치 자세 요청 데이터를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
        half_yaw = float(pose.yaw) / 2.0
        orientation_z = math.sin(half_yaw)
        orientation_w = math.cos(half_yaw)
        return (
            f'name: "{self._simulation_pose_reset_robot_model_name}", '
            f'position: {{x: {pose.x:.6f}, y: {pose.y:.6f}, z: {pose.z:.6f}}}, '
            'orientation: {'
            f'x: 0.000000, y: 0.000000, z: {orientation_z:.6f}, w: {orientation_w:.6f}'
            '}'
        )

    def _set_gazebo_robot_pose(self, pose: CommandPose) -> bool:
        # gazebo 로봇 위치 자세을 설정한다.
        command_env = os.environ.copy()
        if self._gazebo_partition:
            command_env['GZ_PARTITION'] = self._gazebo_partition

        service_candidates = (
            f'/world/{self._gazebo_world_name}/set_pose/blocking',
            f'/world/{self._gazebo_world_name}/set_pose',
        )
        last_error = ''
        for service_name in service_candidates:
            try:
                completed = subprocess.run(
                    [
                        self._gz_executable,
                        'service',
                        '-s',
                        service_name,
                        '--reqtype',
                        'gz.msgs.Pose',
                        '--reptype',
                        'gz.msgs.Boolean',
                        '--timeout',
                        str(self._gazebo_command_timeout_ms),
                        '--req',
                        self._build_gazebo_robot_pose_request(pose),
                    ],
                    check=False,
                    capture_output=True,
                    env=command_env,
                    text=True,
                )
            except FileNotFoundError:
                self.get_logger().warning(
                    f'Gazebo CLI "{self._gz_executable}"를 찾지 못해 시뮬레이션 pose 복구를 건너뜁니다.'
                )
                return False

            combined_output = f'{completed.stdout}\n{completed.stderr}'.strip()
            if completed.returncode == 0 and 'data: false' not in combined_output.lower():
                return True
            last_error = combined_output or str(completed.returncode)

        self.get_logger().warning(f'Gazebo pose 복구에 실패했습니다: {last_error}')
        return False

    def _publish_initial_pose(self, pose: CommandPose) -> None:
        # initial 위치 자세를 외부 시스템이나 다음 처리 단계로 전달한다.
        message = PoseWithCovarianceStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = pose.frame_id
        message.pose.pose.position.x = pose.x
        message.pose.pose.position.y = pose.y
        message.pose.pose.position.z = pose.z
        message.pose.pose.orientation.z = math.sin(float(pose.yaw) / 2.0)
        message.pose.pose.orientation.w = math.cos(float(pose.yaw) / 2.0)
        covariance = [0.0] * 36
        covariance[0] = 0.15
        covariance[7] = 0.15
        covariance[35] = math.radians(10.0) ** 2
        message.pose.covariance = covariance
        self._initial_pose_publisher.publish(message)

    def _choose_simulation_pose_reset_target(self, context: ActiveCommandContext) -> CommandPose | None:
        # 시뮬레이션 위치 자세 reset 대상 가운데 최종 대상을 고른다.
        if context.target_pose is None:
            return None
        if context.navigation_phase is ManualNavigationPhase.ROUTE_EGRESS:
            return context.target_pose

        route = self._resolve_navigation_route(context, context.target_pose)
        if route.poses:
            return self._command_pose_from_pose2d(route.poses[0])
        return context.target_pose

    def _schedule_simulation_pose_reset_recovery(self) -> bool:
        # 시뮬레이션 위치 자세 reset recovery를 어떤 순서와 조건으로 처리할지 계획한다.
        context = self._active_context
        if context is None or context.target_pose is None:
            return False
        if not self._simulation_pose_reset_recovery_enabled:
            return False
        if self._simulation_pose_reset_recovery_count >= self._simulation_pose_reset_retry_limit:
            return False

        recovery_pose = self._choose_simulation_pose_reset_target(context)
        if recovery_pose is None:
            return False
        if not self._set_gazebo_robot_pose(recovery_pose):
            return False

        self._publish_initial_pose(recovery_pose)
        self._simulation_pose_reset_recovery_count += 1
        self._cancel_simulation_pose_reset_retry_timer()
        recovery_label = (
            '현재 위치가 통로 밖으로 걸려 Gazebo 시뮬레이션 pose를 안전 waypoint로 복구한 뒤 '
            '원래 목적지를 다시 시도합니다. '
            f'({self._simulation_pose_reset_recovery_count}/{self._simulation_pose_reset_retry_limit})'
        )
        self.get_logger().warning(recovery_label)
        self._write_status(self._build_status_payload(context, 'running', recovery_label))
        self._simulation_pose_reset_retry_timer = self.create_timer(
            self._simulation_pose_reset_retry_delay_sec,
            self._retry_active_navigation_after_simulation_pose_reset,
        )
        return True

    def _retry_active_navigation_after_simulation_pose_reset(self) -> None:
        # retry active 주행 after 시뮬레이션 위치 자세 reset 정보를 계산해 반환한다.
        self._cancel_simulation_pose_reset_retry_timer()
        context = self._active_context
        if context is None or context.target_pose is None:
            return
        self._dispatch_current_navigation_stage(
            context,
            label=describe_manual_navigation_label(
                context.command.command_type,
                context.home_waypoint_id,
            ),
            is_retry=True,
        )

    def _handle_patrol_service_response(
        self,
        future: Any,
        *,
        action_label: str,
    ) -> None:
        # handle patrol 서비스 response 정보를 계산해 반환한다.
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
        # request active 목표 cancel preemption 정보를 계산해 반환한다.
        if self._active_goal_handle is None or self._goal_cancel_future is not None:
            return
        self._goal_cancel_future = self._active_goal_handle.cancel_goal_async()
        self._goal_cancel_future.add_done_callback(self._handle_active_goal_cancel_response)

    def _handle_active_goal_cancel_response(self, future: Any) -> None:
        # handle active 목표 cancel response 정보를 계산해 반환한다.
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

    def _request_active_recovery_cancel_for_preemption(self) -> None:
        # request active recovery cancel preemption 정보를 계산해 반환한다.
        if self._active_recovery_handle is None or self._recovery_cancel_future is not None:
            return
        self._recovery_cancel_future = self._active_recovery_handle.cancel_goal_async()
        self._recovery_cancel_future.add_done_callback(self._handle_active_recovery_cancel_response)

    def _handle_active_recovery_cancel_response(self, future: Any) -> None:
        # handle active recovery cancel response 정보를 계산해 반환한다.
        self._recovery_cancel_future = None
        try:
            cancel_response = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f'시작 위치 recovery cancel 응답을 받지 못했습니다. 새 목표 전환을 계속 시도합니다: {exc}'
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
            '시작 위치 recovery cancel 요청이 거부되었습니다. 새 목표 전환을 계속 시도합니다.'
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
        # finish active 명령 정보를 계산해 반환한다.
        if self._active_context is None:
            return

        if should_restore_paused_manual_navigation_after_failed_resume(
            self._active_context,
            status=status,
        ):
            resume_context = build_manual_resume_context(
                self._active_context,
                captured_at=self._active_context.started_at,
            )
            if resume_context is not None:
                self._set_control_latch(
                    mode=ControlMode.PAUSED,
                    blocking_reason='resume_motion_failed',
                    message=(
                        '재개 이동이 실패해 저장된 목적지를 유지한 채 다시 일시정지했습니다. '
                        '경로를 정리한 뒤 재개하세요.'
                    ),
                    resume_context=resume_context,
                )
                message = (
                    '재개 이동이 실패해 저장된 목적지를 유지한 채 다시 일시정지했습니다. '
                    f'{message}'
                )

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
        self._active_goal_handle = None
        self._goal_send_future = None
        self._goal_result_future = None
        self._goal_cancel_future = None
        self._path_probe_send_future = None
        self._path_probe_result_future = None
        self._active_path_probe_handle = None
        self._active_path_probe_target_pose = None
        self._pending_final_observation_probe_targets.clear()
        self._service_future = None
        self._recovery_send_future = None
        self._recovery_result_future = None
        self._recovery_cancel_future = None
        self._active_recovery_handle = None
        self._start_occupied_recovery_count = 0
        self._simulation_pose_reset_recovery_count = 0
        self._patrol_state_wait = None
        self._navigation_cancel_reason = ''
        self._resume_release_pending = False
        self._cancel_simulation_pose_reset_retry_timer()
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
        # 상태 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
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
            route_target_pose=(
                context.route_target_pose.as_status_payload()
                if context.route_target_pose is not None
                else None
            ),
            final_target_pose=(
                context.final_target_pose.as_status_payload()
                if context.final_target_pose is not None
                else None
            ),
            target_waypoint_id=context.target_waypoint_id,
            navigation_phase=context.navigation_phase.value if context.navigation_phase is not None else None,
            home_waypoint_id=context.home_waypoint_id,
            control_state=self._control_state.as_payload(),
            received_at=context.received_at,
            started_at=context.started_at,
            completed_at=completed_at,
        )

    def _write_status(self, payload: dict[str, Any]) -> None:
        # 상태를 파일이나 저장소에 기록한다.
        write_json_atomic(self._status_path, payload)
        self._last_status_payload = payload

    def _build_pose_stamped(self, pose: Pose2D) -> PoseStamped:
        # 위치 자세 stamped를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
        return build_latest_pose_stamped(
            frame_id=self._plan.frame_id,
            x_value=pose.x,
            y_value=pose.y,
            z_value=pose.z,
            yaw_value=pose.yaw,
        )

    def _schedule_goal_reject_retry(self) -> bool:
        # 목표 reject retry를 어떤 순서와 조건으로 처리할지 계획한다.
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
            '주행 goal이 일시적으로 거부되어 '
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

    def _schedule_transient_navigation_retry(self) -> bool:
        # transient navigation retry를 어떤 순서와 조건으로 처리할지 계획한다.
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
            'TF 동기화가 아직 안정화되지 않아 '
            f'{self._goal_reject_retry_sec:.2f}s 후 같은 목적지를 다시 시도합니다. '
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
        # retry active 주행 목표 정보를 계산해 반환한다.
        self._cancel_goal_retry_timer()
        context = self._active_context
        if context is None or context.target_pose is None:
            return
        self._dispatch_current_navigation_stage(
            context,
            label=describe_manual_navigation_label(
                context.command.command_type,
                context.home_waypoint_id,
            ),
            is_retry=True,
        )

    def _cancel_goal_retry_timer(self) -> None:
        # cancel 목표 retry timer 정보를 계산해 반환한다.
        if self._goal_retry_timer is None:
            return
        self._goal_retry_timer.cancel()
        self.destroy_timer(self._goal_retry_timer)
        self._goal_retry_timer = None

    def _cancel_simulation_pose_reset_retry_timer(self) -> None:
        # cancel 시뮬레이션 위치 자세 reset retry timer 정보를 계산해 반환한다.
        if self._simulation_pose_reset_retry_timer is None:
            return
        self._simulation_pose_reset_retry_timer.cancel()
        self.destroy_timer(self._simulation_pose_reset_retry_timer)
        self._simulation_pose_reset_retry_timer = None

    def destroy_node(self) -> bool:
        # destroy 노드 정보를 계산해 반환한다.
        self._cancel_goal_retry_timer()
        self._cancel_simulation_pose_reset_retry_timer()
        self._pending_context = None
        self._navigate_client.destroy()
        self._navigate_through_client.destroy()
        self._compute_path_client.destroy()
        self._backup_client.destroy()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
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
