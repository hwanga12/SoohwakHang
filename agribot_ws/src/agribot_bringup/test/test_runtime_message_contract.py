from agribot_bringup.runtime_message_contract import (
    mission_bridge_status_message_from_payload,
    mission_request_message_from_payload,
)


def test_mission_request_message_from_payload_tolerates_none_optional_lists() -> None:
    message = mission_request_message_from_payload(
        {
            'command_id': 'mission-harvest-001',
            'request_type': 'harvest_target',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
            'zone_ids': None,
            'inspect_waypoint_ids': None,
            'payload': {
                'fruit_id': 'farm01_plant_11_tomato_01',
            },
        }
    )

    assert list(message.zone_ids) == []
    assert list(message.inspect_waypoint_ids) == []
    assert message.fruit_id == 'farm01_plant_11_tomato_01'


def test_mission_bridge_status_message_from_payload_tolerates_none_optional_lists() -> None:
    message = mission_bridge_status_message_from_payload(
        {
            'mission_id': 'mission-harvest-001',
            'command_id': 'mission-harvest-001',
            'request_type': 'harvest_target',
            'robot_id': 'AGR-02',
            'status': 'pending',
            'message': 'waiting',
            'zone_ids': None,
            'inspect_waypoint_ids': None,
        }
    )

    assert list(message.zone_ids) == []
    assert list(message.inspect_waypoint_ids) == []
    assert message.status == 'pending'
