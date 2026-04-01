# 이 모듈은 통합 실행과 런치 조율 패키지에서 control state 절차를 담당한다.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def iso_now() -> str:
    # 현재 UTC 시각을 ISO 형식 문자열로 반환한다.
    return datetime.now(timezone.utc).isoformat()


class ControlMode(str, Enum):
    # control 모드 값을 명확히 구분하기 위한 열거형 클래스를 정의한다.
    NORMAL = 'normal'
    PAUSED = 'paused'
    EMERGENCY_STOP = 'emergency_stop'

    @property
    def is_latched(self) -> bool:
        # latched인지 여부를 불리언 값으로 판단한다.
        return self is not ControlMode.NORMAL


class MotionActivity(str, Enum):
    # motion 활동 상태 값을 명확히 구분하기 위한 열거형 클래스를 정의한다.
    IDLE = 'idle'
    MANUAL_NAVIGATION = 'manual_navigation'
    PATROL = 'patrol'


class ResumeContextType(str, Enum):
    # resume context type 값을 명확히 구분하기 위한 열거형 클래스를 정의한다.
    MANUAL_NAVIGATION = 'manual_navigation'
    PATROL = 'patrol'


class ManualNavigationPhase(str, Enum):
    # manual navigation 단계 값을 명확히 구분하기 위한 열거형 클래스를 정의한다.
    ROUTE_EGRESS = 'route_egress'
    ROUTE_ANCHOR = 'route_anchor'
    FINAL_OBSERVATION = 'final_observation'


@dataclass(slots=True, frozen=True)
class ResumeContext:
    # resume 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    context_type: ResumeContextType
    captured_at: str
    command_id: str = ''
    command_type: str = ''
    target_pose: dict[str, Any] | None = None
    target_waypoint_id: str | None = None
    home_waypoint_id: str | None = None
    route_target_pose: dict[str, Any] | None = None
    final_target_pose: dict[str, Any] | None = None
    navigation_phase: str | None = None
    patrol_snapshot: dict[str, Any] | None = None

    def as_payload(self) -> dict[str, Any]:
        # 현재 객체 상태를 다른 계층에서 바로 사용할 수 있는 payload 딕셔너리로 변환한다.
        return {
            'context_type': self.context_type.value,
            'captured_at': self.captured_at,
            'command_id': self.command_id or None,
            'command_type': self.command_type or None,
            'target_pose': self.target_pose,
            'target_waypoint_id': self.target_waypoint_id,
            'home_waypoint_id': self.home_waypoint_id,
            'route_target_pose': self.route_target_pose,
            'final_target_pose': self.final_target_pose,
            'navigation_phase': self.navigation_phase,
            'patrol_snapshot': self.patrol_snapshot,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ResumeContext | None:
        # payload 딕셔너리를 현재 클래스 인스턴스로 복원한다.
        raw_context_type = str(payload.get('context_type', '')).strip().lower()
        if raw_context_type not in {item.value for item in ResumeContextType}:
            return None

        return cls(
            context_type=ResumeContextType(raw_context_type),
            captured_at=str(payload.get('captured_at') or ''),
            command_id=str(payload.get('command_id') or ''),
            command_type=str(payload.get('command_type') or ''),
            target_pose=payload.get('target_pose') if isinstance(payload.get('target_pose'), dict) else None,
            target_waypoint_id=(
                str(payload.get('target_waypoint_id')).strip()
                if payload.get('target_waypoint_id') is not None
                else None
            ),
            home_waypoint_id=(
                str(payload.get('home_waypoint_id')).strip()
                if payload.get('home_waypoint_id') is not None
                else None
            ),
            route_target_pose=(
                payload.get('route_target_pose')
                if isinstance(payload.get('route_target_pose'), dict)
                else None
            ),
            final_target_pose=(
                payload.get('final_target_pose')
                if isinstance(payload.get('final_target_pose'), dict)
                else None
            ),
            navigation_phase=(
                str(payload.get('navigation_phase')).strip()
                if str(payload.get('navigation_phase')).strip()
                in {item.value for item in ManualNavigationPhase}
                else None
            ),
            patrol_snapshot=(
                payload.get('patrol_snapshot')
                if isinstance(payload.get('patrol_snapshot'), dict)
                else None
            ),
        )


@dataclass(slots=True, frozen=True)
class ControlStateSnapshot:
    # control 상태 시점의 값을 기록하기 위한 스냅샷 클래스를 정의한다.
    mode: ControlMode
    active_activity: MotionActivity
    blocking_reason: str = ''
    message: str = ''
    resume_context: ResumeContext | None = None
    updated_at: str = ''

    @property
    def resume_available(self) -> bool:
        # resume available 정보를 계산해 반환한다.
        return self.resume_context is not None

    def as_payload(self) -> dict[str, Any]:
        # 현재 객체 상태를 다른 계층에서 바로 사용할 수 있는 payload 딕셔너리로 변환한다.
        return {
            'mode': self.mode.value,
            'is_latched': self.mode.is_latched,
            'active_activity': self.active_activity.value,
            'blocking_reason': self.blocking_reason or None,
            'message': self.message,
            'resume_available': self.resume_available,
            'resume_context': (
                self.resume_context.as_payload()
                if self.resume_context is not None
                else None
            ),
            'updated_at': self.updated_at or iso_now(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ControlStateSnapshot:
        # payload 딕셔너리를 현재 클래스 인스턴스로 복원한다.
        raw_mode = str(payload.get('mode', ControlMode.NORMAL.value)).strip().lower()
        raw_activity = str(payload.get('active_activity', MotionActivity.IDLE.value)).strip().lower()

        mode = ControlMode(raw_mode) if raw_mode in {item.value for item in ControlMode} else ControlMode.NORMAL
        active_activity = (
            MotionActivity(raw_activity)
            if raw_activity in {item.value for item in MotionActivity}
            else MotionActivity.IDLE
        )
        resume_payload = payload.get('resume_context')
        resume_context = (
            ResumeContext.from_payload(resume_payload)
            if isinstance(resume_payload, dict)
            else None
        )
        return cls(
            mode=mode,
            active_activity=active_activity,
            blocking_reason=str(payload.get('blocking_reason') or ''),
            message=str(payload.get('message') or ''),
            resume_context=resume_context,
            updated_at=str(payload.get('updated_at') or ''),
        )


def build_control_state_payload(
    *,
    mode: ControlMode,
    active_activity: MotionActivity,
    blocking_reason: str = '',
    message: str = '',
    resume_context: ResumeContext | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    # control 상태 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return ControlStateSnapshot(
        mode=mode,
        active_activity=active_activity,
        blocking_reason=blocking_reason,
        message=message,
        resume_context=resume_context,
        updated_at=updated_at or iso_now(),
    ).as_payload()
