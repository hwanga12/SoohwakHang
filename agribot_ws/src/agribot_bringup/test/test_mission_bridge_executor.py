# 이 테스트는 통합 실행과 런치 조율 패키지의 mission bridge executor 동작을 검증한다.
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from agribot_bringup.mission_bridge_contract import (
    MissionBridgeValidationError,
    MissionRequest,
    harvest_bridge_status_from_payload,
    harvest_status_refers_to_request,
    parse_mission_request_payload,
    patrol_bridge_status_from_payload,
)
from agribot_bringup.mission_bridge_executor import ActiveMissionContext, MissionBridgeExecutor


def test_parse_mission_request_payload_supports_start_patrol_contract() -> None:
    # parse 미션 요청 데이터 payload supports start patrol 계약 동작과 회귀 여부를 검증한다.
    request = parse_mission_request_payload(
        {
            'command_id': 'mission-patrol-001',
            'request_type': 'start_patrol',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
            'zone_ids': ['farm_01_west', 'farm_01_center', 'farm_01_west'],
            'loop_count': 2,
            'patrol_mode': 'harvest',
        }
    )

    assert request.command_id == 'mission-patrol-001'
    assert request.mission_id == 'mission-patrol-001'
    assert request.request_type == 'start_patrol'
    assert request.zone_ids == ('farm_01_west', 'farm_01_center')
    assert request.loop_count == 2
    assert request.patrol_mode == 'harvest'


def test_parse_mission_request_payload_supports_harvest_alias_fields() -> None:
    # parse 미션 요청 데이터 payload supports harvest 별칭 fields 동작과 회귀 여부를 검증한다.
    request = parse_mission_request_payload(
        {
            'command_id': 'mission-harvest-001',
            'command_type': 'harvest_target',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
            'payload': {
                'plant_id': 'farm01_plant_03',
                'fruit_id': 'farm01_plant_03_tomato_01',
                'inspect_waypoint_id': 'farm_01_lane_center_inspect_05',
                'inspect_waypoint_ids': ['farm_01_lane_center_inspect_05', 'farm_01_lane_02_inspect_02'],
            },
        }
    )

    assert request.request_type == 'harvest_target'
    assert request.plant_id == 'farm01_plant_03'
    assert request.fruit_id == 'farm01_plant_03_tomato_01'
    assert request.effective_tomato_id == 'farm01_plant_03_tomato_01'
    assert request.inspect_waypoint_id == 'farm_01_lane_center_inspect_05'
    assert request.inspect_waypoint_ids == (
        'farm_01_lane_center_inspect_05',
        'farm_01_lane_02_inspect_02',
    )


def test_parse_mission_request_payload_rejects_missing_harvest_target() -> None:
    # parse 미션 요청 데이터 payload rejects missing harvest target 동작과 회귀 여부를 검증한다.
    try:
        parse_mission_request_payload(
            {
                'command_id': 'mission-harvest-invalid',
                'request_type': 'harvest_target',
                'robot_id': 'AGR-02',
                'requested_by': 'frontend-operator',
            }
        )
    except MissionBridgeValidationError as exc:
        assert 'fruit_id 또는 tomato_id' in str(exc)
    else:
        raise AssertionError('harvest_target without fruit_id/tomato_id should fail')


def test_patrol_bridge_status_from_payload_maps_running_and_terminal_states() -> None:
    # patrol 브리지 상태 from payload 지도 목록 running AND terminal 상태 묶음 동작과 회귀 여부를 검증한다.
    running = patrol_bridge_status_from_payload(
        {'state': 'running', 'message': 'Navigating to waypoint farm_01_home.'}
    )
    stopped = patrol_bridge_status_from_payload(
        {'state': 'stopped', 'message': 'Patrol paused before waypoint farm_01_lane_02.'}
    )
    failed = patrol_bridge_status_from_payload(
        {'state': 'error', 'message': 'Planner failed.', 'error': 'planner_failed'}
    )

    assert running == ('running', 'Navigating to waypoint farm_01_home.', None, False)
    assert stopped == (
        'canceled',
        'Patrol paused before waypoint farm_01_lane_02.',
        'patrol_stopped',
        True,
    )
    assert failed == ('failed', 'Planner failed.', 'planner_failed', True)


def test_harvest_bridge_helpers_match_active_target_and_terminal_states() -> None:
    # harvest 브리지 helpers match active target AND terminal 상태 묶음 동작과 회귀 여부를 검증한다.
    running_payload = {
        'state': 'harvesting',
        'message': 'Simulating harvest for farm01_plant_03_tomato_01 for 2.0s.',
        'active_tomato_id': 'farm01_plant_03_tomato_01',
    }
    completed_payload = {
        'state': 'completed',
        'message': 'Harvest route completed for farm01_plant_03_tomato_01; patrol resumed successfully.',
        'active_tomato_id': None,
    }

    assert harvest_status_refers_to_request(running_payload, 'farm01_plant_03_tomato_01') is True
    assert harvest_status_refers_to_request(completed_payload, 'farm01_plant_03_tomato_01') is True
    assert harvest_bridge_status_from_payload(running_payload) == (
        'running',
        'Simulating harvest for farm01_plant_03_tomato_01 for 2.0s.',
        None,
        False,
    )
    assert harvest_bridge_status_from_payload(completed_payload) == (
        'succeeded',
        'Harvest route completed for farm01_plant_03_tomato_01; patrol resumed successfully.',
        None,
        True,
    )


class _FakePublisher:
    # 테스트에서 publish 호출과 subscriber 수를 추적하기 위한 도우미 클래스다.
    def __init__(self, *, subscription_count: int = 0) -> None:
        self.subscription_count = subscription_count
        self.messages: list[str] = []

    def publish(self, message) -> None:
        self.messages.append(message.data)

    def get_subscription_count(self) -> int:
        return self.subscription_count


def _build_harvest_request(*, command_id: str) -> MissionRequest:
    # harvest request를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return MissionRequest(
        command_id=command_id,
        mission_id=command_id,
        request_type='harvest_target',
        robot_id='AGR-02',
        requested_by='frontend-operator',
        plant_id='farm01_plant_03',
        fruit_id='farm01_plant_03_tomato_01',
        tomato_id='farm01_plant_03_tomato_01',
    )


def _build_executor_for_retry_tests(*, subscription_count: int = 0) -> MissionBridgeExecutor:
    # retry 관련 단위 테스트에 필요한 최소 executor fixture를 구성한다.
    node = object.__new__(MissionBridgeExecutor)
    node._active_context = None
    node._harvest_request_retry_period_sec = 1.0
    node._harvest_request_pending_timeout_sec = 20.0
    node._harvest_request_publisher = _FakePublisher(subscription_count=subscription_count)
    node.get_logger = lambda: SimpleNamespace(info=lambda *_args, **_kwargs: None, warning=lambda *_args, **_kwargs: None)
    return node


def test_retry_active_harvest_request_republishes_pending_target_until_runtime_progress() -> None:
    # startup race로 subscriber가 늦게 붙어도 pending harvest 요청을 재전송한다.
    node = _build_executor_for_retry_tests()
    node._monotonic_now = lambda: 5.0
    request = _build_harvest_request(command_id='mission-harvest-retry-001')
    context = ActiveMissionContext(
        request=request,
        received_at='2026-04-05T13:39:14.810166+00:00',
        received_monotonic=0.0,
        last_harvest_publish_monotonic=0.0,
        harvest_publish_attempt_count=1,
    )
    node._active_context = context
    finish_calls: list[tuple[str, str, str | None]] = []
    node._finish_active_request = lambda status, message, *, error=None, result=None: finish_calls.append((status, message, error))

    MissionBridgeExecutor._retry_active_harvest_request_if_needed(node)

    assert finish_calls == []
    assert context.harvest_publish_attempt_count == 2
    assert context.last_harvest_publish_monotonic == 5.0
    assert len(node._harvest_request_publisher.messages) == 1
    payload = json.loads(node._harvest_request_publisher.messages[0])
    assert payload['mission_id'] == 'mission-harvest-retry-001'
    assert payload['tomato_id'] == 'farm01_plant_03_tomato_01'


def test_retry_active_harvest_request_times_out_when_runtime_never_responds() -> None:
    # harvest route status가 끝내 안 오면 명확한 timeout 실패로 마무리한다.
    node = _build_executor_for_retry_tests(subscription_count=0)
    node._monotonic_now = lambda: 25.0
    request = _build_harvest_request(command_id='mission-harvest-timeout-001')
    context = ActiveMissionContext(
        request=request,
        received_at='2026-04-05T13:39:14.810166+00:00',
        received_monotonic=0.0,
        last_harvest_publish_monotonic=24.0,
        harvest_publish_attempt_count=1,
    )
    node._active_context = context
    finish_calls: list[tuple[str, str, str | None]] = []
    node._finish_active_request = lambda status, message, *, error=None, result=None: finish_calls.append((status, message, error))

    MissionBridgeExecutor._retry_active_harvest_request_if_needed(node)

    assert finish_calls == [
        (
            'failed',
            'harvest_route/status 응답을 기다리다 시간 초과되었습니다. harvest_route_node 와 Nav2 기동 상태를 확인하세요.',
            'harvest_status_timeout',
        )
    ]
    assert node._harvest_request_publisher.messages == []


def test_poll_request_file_retries_active_harvest_even_without_new_request_file() -> None:
    # 새 request 파일이 없어도 active harvest 재전송 루프는 계속 돌아야 한다.
    node = _build_executor_for_retry_tests()
    with TemporaryDirectory() as temp_dir:
        node._request_path = Path(temp_dir) / 'missing_request.json'
        retry_calls: list[str] = []
        node._retry_active_harvest_request_if_needed = lambda: retry_calls.append('called')

        MissionBridgeExecutor._poll_request_file(node)

    assert retry_calls == ['called']
