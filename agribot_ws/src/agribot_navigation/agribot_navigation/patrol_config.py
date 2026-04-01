# 이 모듈은 자율주행과 경로 계획 패키지에서 patrol config 기능을 담당한다.
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory
import yaml


@dataclass(frozen=True)
class Pose2D:
    # 위치 자세 2 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    x: float
    y: float
    z: float
    yaw: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any], field_name: str) -> 'Pose2D':
        # 딕셔너리 값을 읽어 현재 클래스 인스턴스로 복원한다.
        required_fields = {'x', 'y', 'z', 'yaw'}
        missing = required_fields.difference(payload)
        if missing:
            raise ValueError(f'{field_name} is missing pose keys: {sorted(missing)}')
        return cls(
            x=float(payload['x']),
            y=float(payload['y']),
            z=float(payload['z']),
            yaw=float(payload['yaw']),
        )


@dataclass(frozen=True)
class Waypoint:
    # waypoint 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    waypoint_id: str
    display_name: str
    purpose: str
    description: str
    pose: Pose2D
    lane_id: str = ''
    batchable: bool = False
    observe_here: bool = False
    observed_plant_ids: tuple[str, ...] = ()
    observed_tomato_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatrolRoute:
    # patrol 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    route_id: str
    display_name: str
    zone_id: str
    lane_side: str
    description: str
    entry_pose_id: str
    inspect_pose_ids: tuple[str, ...]
    turn_pose_id: str
    exit_pose_id: str
    observed_plant_ids: tuple[str, ...]
    observed_tomato_ids: tuple[str, ...]


@dataclass(frozen=True)
class SourceBounds:
    # source 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    left_bed_edge_x: float
    right_bed_edge_x: float
    front_connector_y: float
    rear_connector_y: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'SourceBounds':
        # 딕셔너리 값을 읽어 현재 클래스 인스턴스로 복원한다.
        required_fields = {
            'left_bed_edge_x',
            'right_bed_edge_x',
            'front_connector_y',
            'rear_connector_y',
        }
        missing = required_fields.difference(payload)
        if missing:
            raise ValueError(f'coordinate_rationale.source_bounds is missing keys: {sorted(missing)}')
        return cls(
            left_bed_edge_x=float(payload['left_bed_edge_x']),
            right_bed_edge_x=float(payload['right_bed_edge_x']),
            front_connector_y=float(payload['front_connector_y']),
            rear_connector_y=float(payload['rear_connector_y']),
        )


@dataclass(frozen=True)
class HarvestRoutingConfig:
    # harvest routing 실행 설정을 한 번에 묶어 다루기 위한 클래스를 정의한다.
    approach_margin_from_bed_edge_m: float
    max_lateral_offset_from_inspect_m: float
    align_standoff_from_crop_m: float
    default_return_mode: str
    fallback_return_mode: str
    max_lateral_offset_from_inspect_m_by_lane_side: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PatrolPlan:
    # patrol 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    schema_version: int
    frame_id: str
    zone_id: str
    home_pose_id: str
    recommended_observation_dwell_sec: float
    source_bounds: SourceBounds
    harvest_routing: HarvestRoutingConfig
    waypoints: dict[str, Waypoint]
    routes: dict[str, PatrolRoute]
    default_patrol_sequence: tuple[str, ...]


def get_default_patrol_waypoints_path() -> Path:
    # default patrol waypoints 경로를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return Path(get_package_share_directory('agribot_navigation')) / 'config' / 'patrol_waypoints.yaml'


def _load_yaml(path: Path) -> dict[str, Any]:
    # YAML 데이터를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    with path.open('r', encoding='utf-8') as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f'Expected a mapping at the top level of {path}.')
    return payload


def _load_waypoints(items: list[dict[str, Any]]) -> dict[str, Waypoint]:
    # waypoints를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    if not items:
        raise ValueError('patrol_waypoints.yaml must define at least one waypoint.')

    waypoints: dict[str, Waypoint] = {}
    for item in items:
        waypoint_id = str(item['waypoint_id'])
        if waypoint_id in waypoints:
            raise ValueError(f'Duplicate waypoint_id: {waypoint_id}')
        purpose = str(item['purpose'])
        waypoints[waypoint_id] = Waypoint(
            waypoint_id=waypoint_id,
            display_name=str(item['display_name']),
            purpose=purpose,
            description=str(item['description']),
            pose=Pose2D.from_dict(item['pose'], f'waypoints[{waypoint_id}]'),
            lane_id=str(item.get('lane_id', '')),
            batchable=bool(item.get('batchable', False)),
            observe_here=bool(item.get('observe_here', purpose == 'inspect')),
            observed_plant_ids=tuple(str(value) for value in item.get('observed_plant_ids', [])),
            observed_tomato_ids=tuple(str(value) for value in item.get('observed_tomato_ids', [])),
        )
    return waypoints


def _load_routes(items: list[dict[str, Any]]) -> dict[str, PatrolRoute]:
    # 경로 목록를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    if not items:
        raise ValueError('patrol_waypoints.yaml must define at least one patrol route.')

    routes: dict[str, PatrolRoute] = {}
    for item in items:
        route_id = str(item['route_id'])
        if route_id in routes:
            raise ValueError(f'Duplicate route_id: {route_id}')
        inspect_pose_ids = tuple(str(value) for value in item.get('inspect_pose_ids', []))
        if not inspect_pose_ids:
            raise ValueError(f'Route {route_id} must define at least one inspect pose.')
        routes[route_id] = PatrolRoute(
            route_id=route_id,
            display_name=str(item['display_name']),
            zone_id=str(item['zone_id']),
            lane_side=str(item['lane_side']),
            description=str(item['description']),
            entry_pose_id=str(item['entry_pose_id']),
            inspect_pose_ids=inspect_pose_ids,
            turn_pose_id=str(item['turn_pose_id']),
            exit_pose_id=str(item['exit_pose_id']),
            observed_plant_ids=tuple(str(value) for value in item.get('observed_plant_ids', [])),
            observed_tomato_ids=tuple(str(value) for value in item.get('observed_tomato_ids', [])),
        )
    return routes


def _load_harvest_routing(payload: dict[str, Any]) -> HarvestRoutingConfig:
    # harvest routing를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    return_modes = payload.get('return_modes', {})
    if return_modes is None:
        return_modes = {}
    max_lateral_offset_by_lane_side = payload.get('max_lateral_offset_from_inspect_m_by_lane_side', {})
    if max_lateral_offset_by_lane_side is None:
        max_lateral_offset_by_lane_side = {}
    if not isinstance(max_lateral_offset_by_lane_side, dict):
        raise ValueError(
            'harvest_routing.max_lateral_offset_from_inspect_m_by_lane_side must be a mapping.'
        )

    return HarvestRoutingConfig(
        approach_margin_from_bed_edge_m=float(payload.get('approach_margin_from_bed_edge_m', 0.45)),
        max_lateral_offset_from_inspect_m=float(
            payload.get('max_lateral_offset_from_inspect_m', 2.50)
        ),
        max_lateral_offset_from_inspect_m_by_lane_side={
            str(key).strip(): float(value)
            for key, value in max_lateral_offset_by_lane_side.items()
            if str(key).strip()
        },
        align_standoff_from_crop_m=float(payload.get('align_standoff_from_crop_m', 0.65)),
        default_return_mode=str(return_modes.get('default', 'resume_patrol')),
        fallback_return_mode=str(return_modes.get('fallback', 'home')),
    )


def _validate_references(plan: PatrolPlan) -> None:
    # references가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
    if plan.home_pose_id not in plan.waypoints:
        raise ValueError(f'home_pose_id does not match any waypoint: {plan.home_pose_id}')

    if plan.recommended_observation_dwell_sec < 0.0:
        raise ValueError('recommended_observation_dwell_sec must be non-negative.')

    if not plan.default_patrol_sequence:
        raise ValueError('default_patrol_sequence must contain at least one waypoint id.')

    if plan.source_bounds.left_bed_edge_x >= plan.source_bounds.right_bed_edge_x:
        raise ValueError('source_bounds must keep left_bed_edge_x smaller than right_bed_edge_x.')

    if plan.source_bounds.front_connector_y >= plan.source_bounds.rear_connector_y:
        raise ValueError('source_bounds front_connector_y must be smaller than rear_connector_y.')

    if plan.harvest_routing.approach_margin_from_bed_edge_m <= 0.0:
        raise ValueError('harvest_routing.approach_margin_from_bed_edge_m must be positive.')

    if plan.harvest_routing.max_lateral_offset_from_inspect_m <= 0.0:
        raise ValueError('harvest_routing.max_lateral_offset_from_inspect_m must be positive.')

    for lane_side, value in plan.harvest_routing.max_lateral_offset_from_inspect_m_by_lane_side.items():
        if value < 0.0:
            raise ValueError(
                'harvest_routing.max_lateral_offset_from_inspect_m_by_lane_side '
                f'contains a negative value for {lane_side!r}.'
            )

    if plan.harvest_routing.align_standoff_from_crop_m <= 0.0:
        raise ValueError('harvest_routing.align_standoff_from_crop_m must be positive.')

    allowed_return_modes = {'resume_patrol', 'home'}
    for mode_name, mode_value in (
        ('default_return_mode', plan.harvest_routing.default_return_mode),
        ('fallback_return_mode', plan.harvest_routing.fallback_return_mode),
    ):
        if mode_value not in allowed_return_modes:
            raise ValueError(
                f'harvest_routing.{mode_name} must be one of '
                f'{sorted(allowed_return_modes)}, got {mode_value!r}.'
            )

    for waypoint_id in plan.default_patrol_sequence:
        if waypoint_id not in plan.waypoints:
            raise ValueError(f'default_patrol_sequence references unknown waypoint: {waypoint_id}')

    for route in plan.routes.values():
        if route.zone_id != plan.zone_id:
            raise ValueError(
                f'Route {route.route_id} belongs to {route.zone_id}, expected {plan.zone_id}.'
            )
        referenced_waypoints = (
            route.entry_pose_id,
            *route.inspect_pose_ids,
            route.turn_pose_id,
            route.exit_pose_id,
        )
        for waypoint_id in referenced_waypoints:
            if waypoint_id not in plan.waypoints:
                raise ValueError(
                    f'Route {route.route_id} references unknown waypoint: {waypoint_id}'
                )


def load_patrol_plan(path: Path) -> PatrolPlan:
    # patrol 계획를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    payload = _load_yaml(path)
    coordinate_rationale = payload.get('coordinate_rationale', {})
    if not isinstance(coordinate_rationale, dict):
        raise ValueError('coordinate_rationale must be a mapping.')
    source_bounds_payload = coordinate_rationale.get('source_bounds', {})
    if not isinstance(source_bounds_payload, dict):
        raise ValueError('coordinate_rationale.source_bounds must be a mapping.')

    robot_constraints = payload.get('robot_constraints', {})
    if robot_constraints is None:
        robot_constraints = {}
    elif not isinstance(robot_constraints, dict):
        raise ValueError('robot_constraints must be a mapping.')

    harvest_routing = payload.get('harvest_routing', {})
    if harvest_routing is None:
        harvest_routing = {}
    elif not isinstance(harvest_routing, dict):
        raise ValueError('harvest_routing must be a mapping.')

    plan = PatrolPlan(
        schema_version=int(payload['schema_version']),
        frame_id=str(payload['frame_id']),
        zone_id=str(payload['zone_id']),
        home_pose_id=str(payload['home_pose_id']),
        recommended_observation_dwell_sec=float(
            robot_constraints.get('recommended_observation_dwell_sec', 0.0)
        ),
        source_bounds=SourceBounds.from_dict(source_bounds_payload),
        harvest_routing=_load_harvest_routing(harvest_routing),
        waypoints=_load_waypoints(list(payload.get('waypoints', []))),
        routes=_load_routes(list(payload.get('routes', []))),
        default_patrol_sequence=tuple(
            str(value) for value in payload.get('default_patrol_sequence', [])
        ),
    )
    _validate_references(plan)
    return plan


def parse_args() -> argparse.Namespace:
    # args를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    parser = argparse.ArgumentParser(
        description='Validate and summarize agribot patrol waypoint metadata.',
    )
    parser.add_argument(
        '--patrol-waypoints',
        type=Path,
        default=get_default_patrol_waypoints_path(),
        help='Path to patrol_waypoints.yaml.',
    )
    return parser.parse_args()


def main() -> int:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    args = parse_args()
    try:
        plan = load_patrol_plan(args.patrol_waypoints)
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f'Patrol waypoint validation failed: {exc}', file=sys.stderr)
        return 1

    print(f'Loaded patrol plan for zone {plan.zone_id} from {args.patrol_waypoints}')
    print(
        f'- {len(plan.waypoints)} waypoints, '
        f'{len(plan.routes)} routes, '
        f'{len(plan.default_patrol_sequence)} sequence entries, '
        f'{plan.recommended_observation_dwell_sec:.1f}s inspect dwell, '
        f'harvest return={plan.harvest_routing.default_return_mode}'
    )
    for route in plan.routes.values():
        print(
            f'- {route.route_id}: '
            f'{len(route.inspect_pose_ids)} inspect poses, '
            f'{len(route.observed_plant_ids)} plants'
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
