from agribot_bringup.mission_bridge_contract import (
    MissionBridgeValidationError,
    harvest_bridge_status_from_payload,
    harvest_status_refers_to_request,
    parse_mission_request_payload,
    patrol_bridge_status_from_payload,
)


def test_parse_mission_request_payload_supports_start_patrol_contract() -> None:
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
