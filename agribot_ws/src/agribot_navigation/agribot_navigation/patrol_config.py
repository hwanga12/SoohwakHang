"""Load and validate row-level patrol waypoint metadata."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Pose2D:
    x: float
    y: float
    z: float
    yaw: float

    @classmethod
    def from_dict(cls, payload: dict[str, Any], field_name: str) -> 'Pose2D':
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
    waypoint_id: str
    display_name: str
    purpose: str
    description: str
    pose: Pose2D
    observed_plant_ids: tuple[str, ...] = ()
    observed_tomato_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PatrolRoute:
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
class PatrolPlan:
    schema_version: int
    frame_id: str
    zone_id: str
    home_pose_id: str
    waypoints: dict[str, Waypoint]
    routes: dict[str, PatrolRoute]
    default_patrol_sequence: tuple[str, ...]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f'Expected a mapping at the top level of {path}.')
    return payload


def _load_waypoints(items: list[dict[str, Any]]) -> dict[str, Waypoint]:
    if not items:
        raise ValueError('patrol_waypoints.yaml must define at least one waypoint.')

    waypoints: dict[str, Waypoint] = {}
    for item in items:
        waypoint_id = str(item['waypoint_id'])
        if waypoint_id in waypoints:
            raise ValueError(f'Duplicate waypoint_id: {waypoint_id}')
        waypoints[waypoint_id] = Waypoint(
            waypoint_id=waypoint_id,
            display_name=str(item['display_name']),
            purpose=str(item['purpose']),
            description=str(item['description']),
            pose=Pose2D.from_dict(item['pose'], f'waypoints[{waypoint_id}]'),
            observed_plant_ids=tuple(str(value) for value in item.get('observed_plant_ids', [])),
            observed_tomato_ids=tuple(str(value) for value in item.get('observed_tomato_ids', [])),
        )
    return waypoints


def _load_routes(items: list[dict[str, Any]]) -> dict[str, PatrolRoute]:
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


def _validate_references(plan: PatrolPlan) -> None:
    if plan.home_pose_id not in plan.waypoints:
        raise ValueError(f'home_pose_id does not match any waypoint: {plan.home_pose_id}')

    if not plan.default_patrol_sequence:
        raise ValueError('default_patrol_sequence must contain at least one waypoint id.')

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
    payload = _load_yaml(path)
    plan = PatrolPlan(
        schema_version=int(payload['schema_version']),
        frame_id=str(payload['frame_id']),
        zone_id=str(payload['zone_id']),
        home_pose_id=str(payload['home_pose_id']),
        waypoints=_load_waypoints(list(payload.get('waypoints', []))),
        routes=_load_routes(list(payload.get('routes', []))),
        default_patrol_sequence=tuple(
            str(value) for value in payload.get('default_patrol_sequence', [])
        ),
    )
    _validate_references(plan)
    return plan


def parse_args() -> argparse.Namespace:
    package_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description='Validate and summarize agribot patrol waypoint metadata.',
    )
    parser.add_argument(
        '--patrol-waypoints',
        type=Path,
        default=package_root / 'config' / 'patrol_waypoints.yaml',
        help='Path to patrol_waypoints.yaml.',
    )
    return parser.parse_args()


def main() -> int:
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
        f'{len(plan.default_patrol_sequence)} sequence entries'
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
