# 이 테스트는 통합 실행과 런치 조율 패키지의 runtime snapshot service 동작을 검증한다.
from agribot_bringup.control_state import (
    ControlMode,
    MotionActivity,
    build_control_state_payload,
)
from agribot_bringup.runtime_snapshot_service import (
    build_pose_snapshot_payload,
    build_manual_command_status_payload,
    build_mission_bridge_status_payload,
    build_semantic_layer_snapshot,
    control_state_path,
    manual_command_path,
    manual_command_status_path,
    mission_request_path,
    mission_status_path,
    mission_status_record_path,
    read_map_metadata,
    runtime_dir_from_env,
)


def test_read_map_metadata_reads_saved_map_dimensions() -> None:
    # read 지도 metadata reads saved 지도 dimensions 동작과 회귀 여부를 검증한다.
    metadata = read_map_metadata()

    assert metadata['map_id'] == 'farm_map'
    assert metadata['frame_id'] == 'map'
    assert metadata['width'] == 410
    assert metadata['height'] == 410
    assert metadata['resolution'] == 0.05


def test_build_semantic_layer_snapshot_contains_plants_and_sprinklers() -> None:
    # build semantic layer 스냅샷 contains 작물 개체 목록 AND sprinklers 동작과 회귀 여부를 검증한다.
    payload = build_semantic_layer_snapshot()

    assert payload['source'] == 'static_config'
    assert payload['counts']['plants'] == 24
    assert payload['counts']['sprinklers'] == 4
    assert payload['row_guides'][0]['value'] == -6.0
    assert payload['lane_guides'][2]['value'] == 0.0

    asset_ids = {asset['id'] for asset in payload['assets']}
    assert 'farm01_plant_01' in asset_ids
    assert 'sprinkler_0' in asset_ids


def test_build_pose_snapshot_payload_preserves_expected_contract() -> None:
    # build 위치 자세 스냅샷 payload preserves expected 계약 동작과 회귀 여부를 검증한다.
    payload = build_pose_snapshot_payload(
        map_id='farm_map',
        robot_id='AGR-02',
        x_value=1.25,
        y_value=-3.5,
        z_value=0.0,
        yaw_value=0.75,
        frame_id='map',
        linear_speed_mps=0.42,
        source_mode='tf_map',
    )

    assert payload['map_id'] == 'farm_map'
    assert payload['robot_id'] == 'AGR-02'
    assert payload['pose']['frame_id'] == 'map'
    assert payload['pose']['x'] == 1.25
    assert payload['linear_speed_mps'] == 0.42
    assert payload['source_mode'] == 'tf_map'
    assert payload['timestamp'] > 0


def test_manual_command_paths_and_status_payload_follow_runtime_contract() -> None:
    # manual 명령 경로 목록 AND 상태 payload follow 런타임 데이터 계약 동작과 회귀 여부를 검증한다.
    runtime_dir = runtime_dir_from_env()

    assert manual_command_path(runtime_dir).name == 'robot_manual_command.json'
    assert manual_command_status_path(runtime_dir).name == 'robot_manual_command_status.json'
    assert control_state_path(runtime_dir).name == 'robot_control_state.json'
    assert mission_request_path(runtime_dir).name == 'robot_mission_request.json'
    assert mission_status_path(runtime_dir).name == 'robot_mission_status.json'
    assert mission_status_record_path('mission:patrol/001', runtime_dir).name == 'mission_patrol_001.json'

    control_state = build_control_state_payload(
        mode=ControlMode.PAUSED,
        active_activity=MotionActivity.IDLE,
        blocking_reason='pause_motion',
        message='일시정지가 활성화되었습니다.',
    )

    payload = build_manual_command_status_payload(
        command_id='cmd-001',
        command_type='return_home',
        robot_id='AGR-02',
        requested_by='frontend-operator',
        status='running',
        message='홈 복귀 명령을 실행 중입니다.',
        result='executed',
        target_pose={'x': 0.0, 'y': 0.0, 'yaw': 0.0, 'frame_id': 'map'},
        home_waypoint_id='farm_01_home',
        control_state=control_state,
        received_at='2026-03-25T00:00:00+00:00',
        started_at='2026-03-25T00:00:01+00:00',
    )

    assert payload['command_id'] == 'cmd-001'
    assert payload['status'] == 'running'
    assert payload['result'] == 'executed'
    assert payload['target_pose']['frame_id'] == 'map'
    assert payload['home_waypoint_id'] == 'farm_01_home'
    assert payload['control_state']['mode'] == 'paused'
    assert payload['received_at'] == '2026-03-25T00:00:00+00:00'


def test_build_mission_bridge_status_payload_preserves_operator_contract() -> None:
    # build 미션 브리지 상태 payload preserves operator 계약 동작과 회귀 여부를 검증한다.
    payload = build_mission_bridge_status_payload(
        mission_id='mission-patrol-001',
        command_id='mission-patrol-001',
        request_type='start_patrol',
        robot_id='AGR-02',
        requested_by='frontend-operator',
        status='running',
        message='Patrol start 요청이 수락되었습니다.',
        result='service_started',
        zone_ids=['farm_01_west', 'farm_01_center'],
        loop_count=2,
        patrol_mode='diagnosis',
        received_at='2026-03-25T00:00:00+00:00',
        started_at='2026-03-25T00:00:01+00:00',
    )

    assert payload['mission_id'] == 'mission-patrol-001'
    assert payload['command_id'] == 'mission-patrol-001'
    assert payload['request_type'] == 'start_patrol'
    assert payload['zone_ids'] == ['farm_01_west', 'farm_01_center']
    assert payload['loop_count'] == 2
    assert payload['patrol_mode'] == 'diagnosis'
    assert payload['status'] == 'running'
    assert payload['result'] == 'service_started'


def test_resume_without_context_uses_no_op_status_result_contract() -> None:
    # resume without context uses NO OP 상태 결과 계약 동작과 회귀 여부를 검증한다.
    payload = build_manual_command_status_payload(
        command_id='cmd-resume-noop',
        command_type='resume_motion',
        robot_id='AGR-02',
        requested_by='frontend-operator',
        status='succeeded',
        message='저장된 재개 문맥이 없어 제어 latch만 해제했습니다.',
        result='no_op',
    )

    assert payload['status'] == 'succeeded'
    assert payload['result'] == 'no_op'
