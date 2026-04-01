# 이 테스트는 상위 제어와 의사결정 패키지의 observation priority 동작을 검증한다.
from agribot_control.observation_priority import ObservationInput, ObservationPriorityArbiter


def build_observation(
    *,
    observation_id: str,
    class_name: str,
    plant_id: str,
    fruit_id: str = '',
    confidence: float = 0.9,
    ready_to_harvest: bool = False,
) -> ObservationInput:
    # 관측 결과를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return ObservationInput(
        observation_id=observation_id,
        zone_id='farm_01',
        plant_id=plant_id,
        fruit_id=fruit_id,
        class_name=class_name,
        confidence=confidence,
        health_score=0.5,
        ready_to_harvest=ready_to_harvest,
    )


def test_diseased_leaf_has_higher_priority_than_ripe_tomato() -> None:
    # diseased leaf HAS higher priority than ripe tomato 동작과 회귀 여부를 검증한다.
    arbiter = ObservationPriorityArbiter()

    ripe = build_observation(
        observation_id='obs-ripe',
        class_name='ripe_tomato',
        plant_id='plant_01',
        fruit_id='fruit_01',
        confidence=0.92,
        ready_to_harvest=True,
    )
    disease = build_observation(
        observation_id='obs-disease',
        class_name='diseased_leaf',
        plant_id='plant_02',
        confidence=0.81,
    )

    arbiter.register_observation(ripe, now_ns=1_000)
    selection = arbiter.register_observation(disease, now_ns=2_000)

    assert selection.selected_candidate is not None
    assert selection.selected_candidate.event_kind == 'diseased_leaf'
    assert selection.selected_candidate.mission_type == 'OBSERVE'
    assert selection.selected_candidate.target_id == 'plant_02'


def test_standardized_disease_suffix_is_recognized_as_disease_event() -> None:
    # standardized disease suffix IS recognized AS disease 이벤트 동작과 회귀 여부를 검증한다.
    arbiter = ObservationPriorityArbiter()
    disease = build_observation(
        observation_id='obs-disease-standardized',
        class_name='tomato_gray_mold_disease',
        plant_id='plant_03',
        confidence=0.88,
    )

    selection = arbiter.register_observation(disease, now_ns=1_000)

    assert selection.accepted
    assert selection.selected_candidate is not None
    assert selection.selected_candidate.event_kind == 'diseased_leaf'
    assert selection.selected_candidate.target_id == 'plant_03'


def test_duplicate_observation_inside_window_is_ignored() -> None:
    # duplicate 관측 결과 inside window IS ignored 동작과 회귀 여부를 검증한다.
    arbiter = ObservationPriorityArbiter(duplicate_window_sec=60.0)
    candidate = build_observation(
        observation_id='obs-01',
        class_name='diseased_leaf',
        plant_id='plant_01',
        confidence=0.8,
    )

    first = arbiter.register_observation(candidate, now_ns=1_000)
    assert first.accepted

    activated = arbiter.activate_candidate(first.selected_candidate, now_ns=2_000)
    assert activated.target_id == 'plant_01'
    arbiter.complete_active_candidate(now_ns=3_000)

    duplicate = arbiter.register_observation(candidate, now_ns=4_000)
    assert not duplicate.accepted
    assert duplicate.is_duplicate
    assert duplicate.reason == 'Duplicate observation inside the cooldown window was ignored.'


def test_next_pending_candidate_can_be_activated_after_active_is_completed() -> None:
    # next pending candidate CAN BE activated after active IS completed 동작과 회귀 여부를 검증한다.
    arbiter = ObservationPriorityArbiter()
    disease = build_observation(
        observation_id='obs-disease',
        class_name='diseased_leaf',
        plant_id='plant_01',
        confidence=0.87,
    )
    ripe = build_observation(
        observation_id='obs-ripe',
        class_name='ripe_tomato',
        plant_id='plant_02',
        fruit_id='fruit_02',
        confidence=0.93,
        ready_to_harvest=True,
    )

    arbiter.register_observation(disease, now_ns=1_000)
    arbiter.register_observation(ripe, now_ns=2_000)

    first = arbiter.peek_best_candidate()
    assert first is not None
    assert first.event_kind == 'diseased_leaf'

    arbiter.activate_candidate(first, now_ns=3_000)
    arbiter.complete_active_candidate(now_ns=4_000)

    second = arbiter.peek_best_candidate()
    assert second is not None
    assert second.event_kind == 'ripe_tomato'
    assert second.target_id == 'fruit_02'
