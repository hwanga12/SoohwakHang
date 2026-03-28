"""수확 route 요청이 plain text와 JSON 두 형식 모두에서 안정적으로 파싱되는지 검증한다."""

import json

from agribot_navigation.harvest_route_contract import (
    HarvestRouteRequest,
    parse_harvest_route_request,
)


def test_parse_harvest_route_request_accepts_plain_tomato_id() -> None:
    request = parse_harvest_route_request('farm01_plant_03_tomato_01')

    assert request == HarvestRouteRequest(
        tomato_id='farm01_plant_03_tomato_01',
        trigger='manual_request',
    )


def test_parse_harvest_route_request_accepts_json_mission_payload() -> None:
    request = parse_harvest_route_request(
        json.dumps(
            {
                'mission_id': 'mission-harvest-003',
                'plant_id': 'farm01_plant_03',
                'fruit_id': 'farm01_plant_03_tomato_01',
                'requested_by': 'frontend-operator',
                'trigger': 'mission_bridge',
            }
        )
    )

    assert request == HarvestRouteRequest(
        tomato_id='farm01_plant_03_tomato_01',
        plant_id='farm01_plant_03',
        mission_id='mission-harvest-003',
        requested_by='frontend-operator',
        trigger='mission_bridge',
    )


def test_parse_harvest_route_request_rejects_invalid_json_payload() -> None:
    assert parse_harvest_route_request('{"mission_id": "broken"') is None
