from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CommandSource(str, Enum):
    AUTO = 'auto'
    MANUAL = 'manual'


@dataclass(slots=True)
class ActuationCommand:
    command_id: str
    zone_id: str
    device_id: str
    device_type: str
    command_type: str
    target_value: float
    unit: str
    requires_approval: bool
    auto_execute: bool
    requested_by: str
    reason: str
    source: str


@dataclass(slots=True)
class ArbitrationResult:
    accepted: bool
    rule: str
    reason: str
    lock_key: str
    conflict_group: str


class ManualPrioritySafetyLock:
    """Guard actuation commands with manual priority and short safety locks."""

    def __init__(
        self,
        *,
        manual_override_seconds: float = 15.0,
        duplicate_window_seconds: float = 2.0,
        execution_lock_seconds: float = 4.0,
        conflict_groups: dict[str, str] | None = None,
    ) -> None:
        self._manual_override_seconds = max(0.0, float(manual_override_seconds))
        self._duplicate_window_seconds = max(0.0, float(duplicate_window_seconds))
        self._execution_lock_seconds = max(0.0, float(execution_lock_seconds))
        self._conflict_groups = {
            key.strip().lower(): value.strip().lower()
            for key, value in (conflict_groups or {}).items()
            if key.strip() and value.strip()
        }
        self._manual_override_until_by_lock_key: dict[str, float] = {}
        self._last_seen_at_by_signature: dict[tuple[str, ...], float] = {}
        self._device_lock_until_by_lock_key: dict[str, float] = {}
        self._conflict_lock_until_by_group_zone: dict[str, float] = {}

    def evaluate(self, command: ActuationCommand, *, now_seconds: float) -> ArbitrationResult:
        normalized_command = self._normalize_command(command)
        self._expire(now_seconds)

        lock_key = self._lock_key(normalized_command)
        conflict_group = self._conflict_group_key(normalized_command)
        signature = self._signature(normalized_command)

        if self._is_duplicate(signature, now_seconds):
            return ArbitrationResult(
                accepted=False,
                rule='R-SAFE-DUPLICATE',
                reason='같은 명령이 짧은 시간 안에 반복되어 중복 실행을 차단합니다.',
                lock_key=lock_key,
                conflict_group=conflict_group,
            )

        if (
            normalized_command.source == CommandSource.AUTO.value
            and self._manual_override_until_by_lock_key.get(lock_key, 0.0) > now_seconds
        ):
            self._last_seen_at_by_signature[signature] = now_seconds
            return ArbitrationResult(
                accepted=False,
                rule='R-SAFE-MANUAL-PRIORITY',
                reason='같은 장치에 대한 수동 제어 우선 시간이 남아 자동 명령을 보류합니다.',
                lock_key=lock_key,
                conflict_group=conflict_group,
            )

        if self._device_lock_until_by_lock_key.get(lock_key, 0.0) > now_seconds:
            self._last_seen_at_by_signature[signature] = now_seconds
            return ArbitrationResult(
                accepted=False,
                rule='R-SAFE-DEVICE-LOCK',
                reason='같은 장치가 아직 실행 잠금 상태라 연속 명령을 차단합니다.',
                lock_key=lock_key,
                conflict_group=conflict_group,
            )

        if self._conflict_lock_until_by_group_zone.get(conflict_group, 0.0) > now_seconds:
            self._last_seen_at_by_signature[signature] = now_seconds
            return ArbitrationResult(
                accepted=False,
                rule='R-SAFE-CONFLICT-LOCK',
                reason='충돌 가능한 장치 그룹이 이미 실행 중이라 동시 명령을 차단합니다.',
                lock_key=lock_key,
                conflict_group=conflict_group,
            )

        self._last_seen_at_by_signature[signature] = now_seconds
        if self._execution_lock_seconds > 0.0:
            lock_until = now_seconds + self._execution_lock_seconds
            self._device_lock_until_by_lock_key[lock_key] = lock_until
            self._conflict_lock_until_by_group_zone[conflict_group] = lock_until

        if normalized_command.source == CommandSource.MANUAL.value:
            self._manual_override_until_by_lock_key[lock_key] = (
                now_seconds + self._manual_override_seconds
            )

        return ArbitrationResult(
            accepted=True,
            rule='R-SAFE-ACCEPT',
            reason='안전 잠금 규칙을 통과해 명령을 수락합니다.',
            lock_key=lock_key,
            conflict_group=conflict_group,
        )

    def _expire(self, now_seconds: float) -> None:
        self._prune(self._manual_override_until_by_lock_key, now_seconds)
        self._prune(self._device_lock_until_by_lock_key, now_seconds)
        self._prune(self._conflict_lock_until_by_group_zone, now_seconds)
        self._prune_duplicates(now_seconds)

    def _prune(self, store: dict, now_seconds: float) -> None:
        expired_keys = [key for key, until in store.items() if until <= now_seconds]
        for key in expired_keys:
            store.pop(key, None)

    def _prune_duplicates(self, now_seconds: float) -> None:
        expired_keys = [
            key
            for key, seen_at in self._last_seen_at_by_signature.items()
            if (now_seconds - seen_at) >= self._duplicate_window_seconds
        ]
        for key in expired_keys:
            self._last_seen_at_by_signature.pop(key, None)

    def _normalize_command(self, command: ActuationCommand) -> ActuationCommand:
        return ActuationCommand(
            command_id=command.command_id.strip(),
            zone_id=command.zone_id.strip(),
            device_id=command.device_id.strip(),
            device_type=command.device_type.strip().lower(),
            command_type=command.command_type.strip().lower(),
            target_value=float(command.target_value),
            unit=command.unit.strip().lower(),
            requires_approval=bool(command.requires_approval),
            auto_execute=bool(command.auto_execute),
            requested_by=command.requested_by.strip(),
            reason=command.reason.strip(),
            source=command.source.strip().lower(),
        )

    def _lock_key(self, command: ActuationCommand) -> str:
        device_identifier = command.device_id or command.device_type
        return f'{command.zone_id}:{device_identifier}'

    def _conflict_group_key(self, command: ActuationCommand) -> str:
        group = self._conflict_groups.get(command.device_type, command.device_type)
        return f'{command.zone_id}:{group}'

    def _signature(self, command: ActuationCommand) -> tuple[str, ...]:
        return (
            self._lock_key(command),
            command.command_type,
            f'{command.target_value:.3f}',
            command.unit,
            command.source,
        )

    def _is_duplicate(self, signature: tuple[str, ...], now_seconds: float) -> bool:
        last_seen_at = self._last_seen_at_by_signature.get(signature)
        if last_seen_at is None:
            return False
        return (now_seconds - last_seen_at) < self._duplicate_window_seconds
