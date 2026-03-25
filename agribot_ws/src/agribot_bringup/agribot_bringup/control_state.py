from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ControlMode(str, Enum):
    NORMAL = 'normal'
    PAUSED = 'paused'
    EMERGENCY_STOP = 'emergency_stop'

    @property
    def is_latched(self) -> bool:
        return self is not ControlMode.NORMAL


class MotionActivity(str, Enum):
    IDLE = 'idle'
    MANUAL_NAVIGATION = 'manual_navigation'
    PATROL = 'patrol'


class ResumeContextType(str, Enum):
    MANUAL_NAVIGATION = 'manual_navigation'
    PATROL = 'patrol'


@dataclass(slots=True, frozen=True)
class ResumeContext:
    context_type: ResumeContextType
    captured_at: str
    command_id: str = ''
    command_type: str = ''
    target_pose: dict[str, Any] | None = None
    home_waypoint_id: str | None = None
    patrol_snapshot: dict[str, Any] | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            'context_type': self.context_type.value,
            'captured_at': self.captured_at,
            'command_id': self.command_id or None,
            'command_type': self.command_type or None,
            'target_pose': self.target_pose,
            'home_waypoint_id': self.home_waypoint_id,
            'patrol_snapshot': self.patrol_snapshot,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ResumeContext | None:
        raw_context_type = str(payload.get('context_type', '')).strip().lower()
        if raw_context_type not in {item.value for item in ResumeContextType}:
            return None

        return cls(
            context_type=ResumeContextType(raw_context_type),
            captured_at=str(payload.get('captured_at') or ''),
            command_id=str(payload.get('command_id') or ''),
            command_type=str(payload.get('command_type') or ''),
            target_pose=payload.get('target_pose') if isinstance(payload.get('target_pose'), dict) else None,
            home_waypoint_id=(
                str(payload.get('home_waypoint_id')).strip()
                if payload.get('home_waypoint_id') is not None
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
    mode: ControlMode
    active_activity: MotionActivity
    blocking_reason: str = ''
    message: str = ''
    resume_context: ResumeContext | None = None
    updated_at: str = ''

    @property
    def resume_available(self) -> bool:
        return self.resume_context is not None

    def as_payload(self) -> dict[str, Any]:
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
    return ControlStateSnapshot(
        mode=mode,
        active_activity=active_activity,
        blocking_reason=blocking_reason,
        message=message,
        resume_context=resume_context,
        updated_at=updated_at or iso_now(),
    ).as_payload()
