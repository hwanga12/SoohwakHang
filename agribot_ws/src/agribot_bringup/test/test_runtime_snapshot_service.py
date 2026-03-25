from agribot_bringup.runtime_snapshot_service import (
    build_pose_snapshot_payload,
    build_manual_command_status_payload,
    build_semantic_layer_snapshot,
    manual_command_path,
    manual_command_status_path,
    read_map_metadata,
    runtime_dir_from_env,
)


def test_read_map_metadata_reads_saved_map_dimensions() -> None:
    metadata = read_map_metadata()

    assert metadata['map_id'] == 'farm_map'
    assert metadata['frame_id'] == 'map'
    assert metadata['width'] == 410
    assert metadata['height'] == 410
    assert metadata['resolution'] == 0.05


def test_build_semantic_layer_snapshot_contains_plants_and_sprinklers() -> None:
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
    runtime_dir = runtime_dir_from_env()

    assert manual_command_path(runtime_dir).name == 'robot_manual_command.json'
    assert manual_command_status_path(runtime_dir).name == 'robot_manual_command_status.json'

    payload = build_manual_command_status_payload(
        command_id='cmd-001',
        command_type='return_home',
        robot_id='AGR-02',
        requested_by='frontend-operator',
        status='running',
        message='홈 복귀 명령을 실행 중입니다.',
        target_pose={'x': 0.0, 'y': 0.0, 'yaw': 0.0, 'frame_id': 'map'},
        home_waypoint_id='farm_01_home',
        received_at='2026-03-25T00:00:00+00:00',
        started_at='2026-03-25T00:00:01+00:00',
    )

    assert payload['command_id'] == 'cmd-001'
    assert payload['status'] == 'running'
    assert payload['target_pose']['frame_id'] == 'map'
    assert payload['home_waypoint_id'] == 'farm_01_home'
    assert payload['received_at'] == '2026-03-25T00:00:00+00:00'
