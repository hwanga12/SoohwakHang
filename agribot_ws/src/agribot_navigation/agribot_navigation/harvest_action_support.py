# 이 모듈은 자율주행과 경로 계획 패키지에서 harvest action support 기능을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import uuid

from agribot_interfaces.action import HarvestTomato
from agribot_interfaces.msg import HarvestBasketState, HarvestEvent, MissionStatus

from .harvest_routing import CropCatalog, HarvestRoutePlan


@dataclass(frozen=True)
class ResolvedHarvestGoal:
    # resolved harvest 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    mission_id: str
    zone_id: str
    plant_id: str
    tomato_id: str
    preferred_approach_waypoint_id: str


PHASE_PROGRESS_PCT = {
    'PLANNING': 5.0,
    'WAITING_FOR_PATROL_PAUSE': 10.0,
    'APPROACHING': 35.0,
    'ALIGNING': 55.0,
    'PICKING': 70.0,
    'VERIFYING': 85.0,
    'STOWING': 95.0,
    'RETURN_HOME': 98.0,
    'RESUME': 100.0,
    'SAFETY_STOP': 100.0,
    'COMPLETED': 100.0,
}


def _normalize_text(value: str | None) -> str:
    # text를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    if value is None:
        return ''
    normalized = str(value).strip()
    if normalized.lower() in {'none', 'null'}:
        return ''
    return normalized


def resolve_harvest_goal(
    *,
    mission_id: str | None,
    zone_id: str | None,
    plant_id: str | None,
    fruit_id: str | None,
    approach_waypoint_id: str | None,
    default_zone_id: str,
    catalog: CropCatalog,
) -> ResolvedHarvestGoal:
    # 현재 입력 조건을 바탕으로 harvest 목표를 계산하거나 결정한다.
    normalized_fruit_id = _normalize_text(fruit_id)
    if not normalized_fruit_id:
        raise ValueError('HarvestTomato goal requires a non-empty fruit_id.')
    if normalized_fruit_id not in catalog.tomatoes:
        raise ValueError(f'Unknown fruit_id: {normalized_fruit_id}')

    tomato = catalog.tomatoes[normalized_fruit_id]
    normalized_zone_id = _normalize_text(zone_id) or default_zone_id
    if normalized_zone_id != catalog.zone_id:
        raise ValueError(
            f'Harvest zone_id {normalized_zone_id} does not match crop catalog zone_id '
            f'{catalog.zone_id}.'
        )

    normalized_plant_id = _normalize_text(plant_id) or tomato.parent_plant_id
    if normalized_plant_id != tomato.parent_plant_id:
        raise ValueError(
            f'fruit_id {normalized_fruit_id} belongs to plant {tomato.parent_plant_id}, '
            f'got {normalized_plant_id}.'
        )

    normalized_mission_id = _normalize_text(mission_id) or f'harvest-{uuid.uuid4()}'
    return ResolvedHarvestGoal(
        mission_id=normalized_mission_id,
        zone_id=normalized_zone_id,
        plant_id=normalized_plant_id,
        tomato_id=normalized_fruit_id,
        preferred_approach_waypoint_id=_normalize_text(approach_waypoint_id),
    )


def ensure_harvest_target_available(
    *,
    catalog: CropCatalog,
    tomato_id: str,
    harvested_tomato_ids: set[str],
) -> None:
    # harvest target 사용 가능 상태가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
    tomato = catalog.tomatoes[tomato_id]
    if not tomato.ready_to_harvest:
        raise ValueError(f'Tomato {tomato_id} is not marked ready_to_harvest.')
    if tomato_id in harvested_tomato_ids:
        raise ValueError(f'Tomato {tomato_id} was already harvested in this runtime.')


def alignment_required(route_plan: HarvestRoutePlan) -> bool:
    # alignment required 정보를 계산해 반환한다.
    distance = math.hypot(
        route_plan.align_pose.x - route_plan.approach_pose.x,
        route_plan.align_pose.y - route_plan.approach_pose.y,
    )
    yaw_delta = math.atan2(
        math.sin(route_plan.align_pose.yaw - route_plan.approach_pose.yaw),
        math.cos(route_plan.align_pose.yaw - route_plan.approach_pose.yaw),
    )
    return distance > 0.05 or abs(yaw_delta) > math.radians(5.0)


def build_feedback(
    *,
    current_phase: str,
    progress_pct: float,
    aligned_to_target: bool,
    gripper_engaged: bool,
) -> HarvestTomato.Feedback:
    # feedback를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    feedback = HarvestTomato.Feedback()
    feedback.current_phase = current_phase
    feedback.progress_pct = max(0.0, min(100.0, float(progress_pct)))
    feedback.aligned_to_target = bool(aligned_to_target)
    feedback.gripper_engaged = bool(gripper_engaged)
    return feedback


def build_result(
    *,
    success: bool,
    harvest_event_id: str,
    basket_count: int,
    message: str,
) -> HarvestTomato.Result:
    # 결과를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    result = HarvestTomato.Result()
    result.success = bool(success)
    result.harvest_event_id = harvest_event_id
    result.basket_count = int(basket_count)
    result.message = message
    return result


def build_harvest_event(
    *,
    event_id: str,
    mission_id: str,
    zone_id: str,
    plant_id: str,
    fruit_id: str,
    frame_id: str,
    basket_count: int,
    success: bool,
    failure_reason: str = '',
) -> HarvestEvent:
    # harvest 이벤트를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    event = HarvestEvent()
    event.header.frame_id = frame_id
    event.event_id = event_id
    event.mission_id = mission_id
    event.zone_id = zone_id
    event.plant_id = plant_id
    event.fruit_id = fruit_id
    event.success = bool(success)
    event.failure_reason = failure_reason.strip()
    event.basket_count = int(basket_count)
    return event


def build_basket_state(
    *,
    zone_id: str,
    frame_id: str,
    basket_count: int,
    harvested_count: int,
    remaining_ready_count: int,
    last_event_id: str,
    last_harvested_fruit_id: str,
    loaded_fruit_ids: list[str],
) -> HarvestBasketState:
    # basket 상태를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    state = HarvestBasketState()
    state.header.frame_id = frame_id
    state.zone_id = zone_id
    state.basket_count = int(basket_count)
    state.harvested_count = int(harvested_count)
    state.remaining_ready_count = int(remaining_ready_count)
    state.last_event_id = last_event_id
    state.last_harvested_fruit_id = last_harvested_fruit_id
    state.loaded_fruit_ids = list(loaded_fruit_ids)
    return state


def build_mission_status(
    *,
    mission_id: str,
    mission_type: str,
    state: str,
    current_phase: str,
    zone_id: str,
    target_id: str,
    progress_pct: float,
    detail_message: str,
    retry_count: int = 0,
) -> MissionStatus:
    # 미션 상태를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    status = MissionStatus()
    status.mission_id = mission_id
    status.mission_type = mission_type
    status.state = state
    status.current_phase = current_phase
    status.zone_id = zone_id
    status.target_id = target_id
    status.progress_pct = max(0.0, min(100.0, float(progress_pct)))
    status.retry_count = max(0, int(retry_count))
    status.detail_message = detail_message
    return status


def _stamp_payload(stamp: object) -> dict[str, int]:
    # stamp 페이로드 정보를 계산해 반환한다.
    return {
        'sec': int(getattr(stamp, 'sec', 0)),
        'nanosec': int(getattr(stamp, 'nanosec', 0)),
    }


def _normalize_mission_runtime_status(state: str) -> str:
    # 미션 런타임 데이터 상태를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(state).strip().lower()
    if normalized in {'planned', 'pending'}:
        return 'pending'
    if normalized == 'running':
        return 'running'
    if normalized in {'completed', 'complete', 'succeeded'}:
        return 'succeeded'
    if normalized in {'failed', 'error'}:
        return 'failed'
    if normalized in {'canceled', 'cancelled'}:
        return 'canceled'
    return 'idle'


def build_harvest_event_payload(
    event: HarvestEvent,
    *,
    occurred_at: str,
) -> dict[str, object]:
    # harvest 이벤트 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return {
        'event_id': event.event_id,
        'mission_id': event.mission_id,
        'zone_id': event.zone_id,
        'plant_id': event.plant_id,
        'fruit_id': event.fruit_id,
        'success': bool(event.success),
        'status': 'succeeded' if event.success else 'failed',
        'failure_reason': event.failure_reason,
        'basket_count': int(event.basket_count),
        'frame_id': event.header.frame_id,
        'stamp': _stamp_payload(event.header.stamp),
        'occurred_at': occurred_at,
    }


def build_basket_state_payload(
    state: HarvestBasketState,
    *,
    updated_at: str,
) -> dict[str, object]:
    # basket 상태 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return {
        'zone_id': state.zone_id,
        'basket_count': int(state.basket_count),
        'harvested_count': int(state.harvested_count),
        'remaining_ready_count': int(state.remaining_ready_count),
        'last_event_id': state.last_event_id,
        'last_harvested_fruit_id': state.last_harvested_fruit_id,
        'loaded_fruit_ids': list(state.loaded_fruit_ids),
        'frame_id': state.header.frame_id,
        'stamp': _stamp_payload(state.header.stamp),
        'updated_at': updated_at,
    }


def build_mission_status_payload(
    status: MissionStatus,
    *,
    updated_at: str,
) -> dict[str, object]:
    # 미션 상태 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return {
        'mission_id': status.mission_id,
        'mission_type': status.mission_type,
        'state': status.state,
        'status': _normalize_mission_runtime_status(status.state),
        'current_phase': status.current_phase,
        'zone_id': status.zone_id,
        'target_id': status.target_id,
        'progress_pct': float(status.progress_pct),
        'retry_count': int(status.retry_count),
        'detail_message': status.detail_message,
        'frame_id': status.header.frame_id,
        'stamp': _stamp_payload(status.header.stamp),
        'updated_at': updated_at,
    }


def should_retry_phase(
    *,
    current_phase: str,
    retryable_phases: set[str],
    retry_count: int,
    retry_limit: int,
) -> bool:
    # retry 단계가 필요한 상황인지 여부를 판단한다.
    normalized_phase = current_phase.strip().upper()
    if not normalized_phase:
        return False
    if retry_limit <= 0:
        return False
    if normalized_phase not in retryable_phases:
        return False
    return retry_count < retry_limit


def build_failure_alert_payload(
    *,
    mission_id: str,
    zone_id: str,
    fruit_id: str,
    current_phase: str,
    failure_reason: str,
    retry_count: int,
    safety_stop_requested: bool,
    safety_stop_completed: bool,
    harvest_completed: bool,
) -> str:
    # failure alert payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    payload = {
        'alert_type': 'HARVEST_FAILURE',
        'severity': 'ERROR',
        'mission_id': mission_id,
        'zone_id': zone_id,
        'fruit_id': fruit_id,
        'current_phase': current_phase,
        'retry_count': max(0, int(retry_count)),
        'safety_stop_requested': bool(safety_stop_requested),
        'safety_stop_completed': bool(safety_stop_completed),
        'harvest_completed': bool(harvest_completed),
        'failure_reason': failure_reason.strip(),
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)
