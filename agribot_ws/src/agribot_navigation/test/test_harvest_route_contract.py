# 이 테스트는 자율주행과 경로 계획 패키지의 harvest route contract 동작을 검증한다.
import json

from agribot_navigation.harvest_route_contract import (
    HarvestRouteRequest,
    parse_harvest_route_request,
)


def test_parse_harvest_route_request_accepts_plain_tomato_id() -> None:
    # parse harvest 경로 요청 데이터 accepts plain tomato ID 동작과 회귀 여부를 검증한다.
    request = parse_harvest_route_request('farm01_plant_03_tomato_01')

    assert request == HarvestRouteRequest(
        tomato_id='farm01_plant_03_tomato_01',
        trigger='manual_request',
    )


def test_parse_harvest_route_request_accepts_json_mission_payload() -> None:
    # parse harvest 경로 요청 데이터 accepts JSON 데이터 미션 payload 동작과 회귀 여부를 검증한다.
    request = parse_harvest_route_request(
        json.dumps(
            {
                'mission_id': 'mission-harvest-003',
                'plant_id': 'farm01_plant_03',
                'fruit_id': 'farm01_plant_03_tomato_01',
                'requested_by': 'frontend-operator',
                'trigger': 'mission_bridge',
                'inspect_waypoint_id': 'farm_01_lane_center_inspect_05',
                'inspect_waypoint_ids': [
                    'farm_01_lane_center_inspect_05',
                    'farm_01_lane_02_inspect_02',
                ],
            }
        )
    )

    assert request == HarvestRouteRequest(
        tomato_id='farm01_plant_03_tomato_01',
        plant_id='farm01_plant_03',
        mission_id='mission-harvest-003',
        requested_by='frontend-operator',
        trigger='mission_bridge',
        inspect_waypoint_id='farm_01_lane_center_inspect_05',
        inspect_waypoint_ids=(
            'farm_01_lane_center_inspect_05',
            'farm_01_lane_02_inspect_02',
        ),
    )


def test_parse_harvest_route_request_rejects_invalid_json_payload() -> None:
    # parse harvest 경로 요청 데이터 rejects invalid JSON 데이터 payload 동작과 회귀 여부를 검증한다.
    assert parse_harvest_route_request('{"mission_id": "broken"') is None
