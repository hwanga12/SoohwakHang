from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ObservationInput:
    observation_id: str
    zone_id: str
    plant_id: str
    fruit_id: str
    class_name: str
    confidence: float
    health_score: float
    ready_to_harvest: bool
    image_path: str = ''


@dataclass(slots=True)
class ObservationTaskCandidate:
    observation_id: str
    dedup_key: str
    event_kind: str
    mission_type: str
    target_id: str
    priority: int
    confidence: float
    observed_at_ns: int
    detail_message: str
    plant_id: str
    fruit_id: str
    class_name: str


@dataclass(slots=True)
class ObservationSelection:
    selected_candidate: ObservationTaskCandidate | None
    accepted: bool
    is_duplicate: bool
    reason: str
    pending_count: int


class ObservationPriorityArbiter:
    """Apply duplicate filtering and event priority for perception observations."""

    def __init__(
        self,
        *,
        duplicate_window_sec: float = 120.0,
        max_pending_events: int = 16,
        diseased_leaf_priority: int = 300,
        ripe_tomato_priority: int = 200,
        generic_observation_priority: int = 100,
    ) -> None:
        self._duplicate_window_ns = max(1, int(duplicate_window_sec * 1_000_000_000))
        self._max_pending_events = max(1, max_pending_events)
        self._diseased_leaf_priority = diseased_leaf_priority
        self._ripe_tomato_priority = ripe_tomato_priority
        self._generic_observation_priority = generic_observation_priority
        self._pending_by_key: dict[str, ObservationTaskCandidate] = {}
        self._recent_until_ns: dict[str, int] = {}
        self._active_candidate: ObservationTaskCandidate | None = None

    @property
    def active_candidate(self) -> ObservationTaskCandidate | None:
        return self._active_candidate

    def clear(self) -> None:
        self._pending_by_key.clear()
        self._recent_until_ns.clear()
        self._active_candidate = None

    def register_observation(
        self,
        observation: ObservationInput,
        *,
        now_ns: int,
    ) -> ObservationSelection:
        self._expire_stale_entries(now_ns)
        candidate = self._build_candidate(observation, now_ns=now_ns)

        if not candidate.target_id:
            return ObservationSelection(
                selected_candidate=self.peek_best_candidate(),
                accepted=False,
                is_duplicate=False,
                reason='Observation is missing a usable target id.',
                pending_count=len(self._pending_by_key),
            )

        if (
            self._active_candidate is not None
            and self._active_candidate.dedup_key == candidate.dedup_key
        ):
            return ObservationSelection(
                selected_candidate=self._active_candidate,
                accepted=False,
                is_duplicate=True,
                reason='Duplicate observation for the active target was ignored.',
                pending_count=len(self._pending_by_key),
            )

        recent_until_ns = self._recent_until_ns.get(candidate.dedup_key, 0)
        if recent_until_ns > now_ns and candidate.dedup_key not in self._pending_by_key:
            return ObservationSelection(
                selected_candidate=self.peek_best_candidate(),
                accepted=False,
                is_duplicate=True,
                reason='Duplicate observation inside the cooldown window was ignored.',
                pending_count=len(self._pending_by_key),
            )

        existing_candidate = self._pending_by_key.get(candidate.dedup_key)
        if existing_candidate is not None:
            if self._should_replace(existing_candidate, candidate):
                self._pending_by_key[candidate.dedup_key] = candidate
                reason = 'Pending observation was refreshed with a stronger duplicate.'
            else:
                return ObservationSelection(
                    selected_candidate=self.peek_best_candidate(),
                    accepted=False,
                    is_duplicate=True,
                    reason='Duplicate pending observation was ignored.',
                    pending_count=len(self._pending_by_key),
                )
        else:
            if len(self._pending_by_key) >= self._max_pending_events:
                lowest_candidate = self._lowest_priority_candidate()
                if lowest_candidate is None or not self._should_replace(lowest_candidate, candidate):
                    return ObservationSelection(
                        selected_candidate=self.peek_best_candidate(),
                        accepted=False,
                        is_duplicate=False,
                        reason='Pending observation queue is full; lower-priority event was dropped.',
                        pending_count=len(self._pending_by_key),
                    )
                del self._pending_by_key[lowest_candidate.dedup_key]
            self._pending_by_key[candidate.dedup_key] = candidate
            reason = 'Observation candidate was queued.'

        return ObservationSelection(
            selected_candidate=self.peek_best_candidate(),
            accepted=True,
            is_duplicate=False,
            reason=reason,
            pending_count=len(self._pending_by_key),
        )

    def peek_best_candidate(self) -> ObservationTaskCandidate | None:
        if not self._pending_by_key:
            return None
        return min(self._pending_by_key.values(), key=self._candidate_sort_key)

    def activate_candidate(
        self,
        candidate: ObservationTaskCandidate,
        *,
        now_ns: int,
    ) -> ObservationTaskCandidate:
        self._expire_stale_entries(now_ns)
        self._pending_by_key.pop(candidate.dedup_key, None)
        self._active_candidate = candidate
        return candidate

    def complete_active_candidate(self, *, now_ns: int) -> ObservationTaskCandidate | None:
        self._expire_stale_entries(now_ns)
        if self._active_candidate is None:
            return None
        candidate = self._active_candidate
        self._recent_until_ns[candidate.dedup_key] = now_ns + self._duplicate_window_ns
        self._active_candidate = None
        return candidate

    def pending_count(self) -> int:
        return len(self._pending_by_key)

    def _build_candidate(
        self,
        observation: ObservationInput,
        *,
        now_ns: int,
    ) -> ObservationTaskCandidate:
        normalized_class = observation.class_name.strip().lower()
        event_kind = 'generic_observation'
        mission_type = 'OBSERVE'
        priority = self._generic_observation_priority

        if 'disease' in normalized_class:
            event_kind = 'diseased_leaf'
            mission_type = 'OBSERVE'
            priority = self._diseased_leaf_priority
        elif observation.ready_to_harvest or ('ripe' in normalized_class and 'tomato' in normalized_class):
            event_kind = 'ripe_tomato'
            mission_type = 'HARVEST'
            priority = self._ripe_tomato_priority

        target_id = observation.fruit_id or observation.plant_id
        dedup_key = ':'.join(
            (
                observation.zone_id or '-',
                observation.plant_id or '-',
                observation.fruit_id or '-',
                event_kind,
            )
        )
        detail_message = (
            f'Selected {event_kind} event for target {target_id or observation.plant_id or "unknown"}.'
        )

        return ObservationTaskCandidate(
            observation_id=observation.observation_id,
            dedup_key=dedup_key,
            event_kind=event_kind,
            mission_type=mission_type,
            target_id=target_id,
            priority=priority,
            confidence=max(0.0, min(1.0, float(observation.confidence))),
            observed_at_ns=now_ns,
            detail_message=detail_message,
            plant_id=observation.plant_id,
            fruit_id=observation.fruit_id,
            class_name=observation.class_name,
        )

    def _expire_stale_entries(self, now_ns: int) -> None:
        stale_keys = [
            dedup_key
            for dedup_key, until_ns in self._recent_until_ns.items()
            if until_ns <= now_ns
        ]
        for dedup_key in stale_keys:
            del self._recent_until_ns[dedup_key]

    def _should_replace(
        self,
        current: ObservationTaskCandidate,
        new: ObservationTaskCandidate,
    ) -> bool:
        return (
            new.priority > current.priority
            or (
                new.priority == current.priority
                and new.confidence > current.confidence
            )
            or (
                new.priority == current.priority
                and abs(new.confidence - current.confidence) <= 1.0e-6
                and new.observed_at_ns < current.observed_at_ns
            )
        )

    def _lowest_priority_candidate(self) -> ObservationTaskCandidate | None:
        if not self._pending_by_key:
            return None
        return max(self._pending_by_key.values(), key=self._candidate_sort_key)

    @staticmethod
    def _candidate_sort_key(candidate: ObservationTaskCandidate) -> tuple[int, float, int]:
        return (-candidate.priority, -candidate.confidence, candidate.observed_at_ns)
