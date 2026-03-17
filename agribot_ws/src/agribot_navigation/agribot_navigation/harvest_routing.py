"""Plan tomato harvest approach and return poses from patrol metadata."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ament_index_python.packages import get_package_share_directory
import yaml

from .patrol_config import (
    PatrolPlan,
    PatrolRoute,
    Pose2D,
    Waypoint,
    get_default_patrol_waypoints_path,
    load_patrol_plan,
)


@dataclass(frozen=True)
class PlantInstance:
    plant_id: str
    zone_id: str
    display_name: str
    world_model_name: str
    pose: Pose2D


@dataclass(frozen=True)
class TomatoInstance:
    tomato_id: str
    zone_id: str
    parent_plant_id: str
    display_name: str
    world_model_name: str
    pose: Pose2D
    ready_to_harvest: bool


@dataclass(frozen=True)
class CropCatalog:
    frame_id: str
    zone_id: str
    plants: dict[str, PlantInstance]
    tomatoes: dict[str, TomatoInstance]


@dataclass(frozen=True)
class HarvestObservationContext:
    route: PatrolRoute
    inspect_waypoint: Waypoint


@dataclass(frozen=True)
class HarvestRoutePlan:
    tomato_id: str
    plant_id: str
    route_id: str
    lane_side: str
    inspect_waypoint_id: str
    inspect_waypoint_name: str
    approach_pose: Pose2D
    return_mode: str
    return_waypoint_id: str
    fallback_return_waypoint_id: str
    fallback_return_mode: str


def get_default_crop_instances_path() -> Path:
    return Path(get_package_share_directory('agribot_description')) / 'config' / 'crop_instances.yaml'


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f'Expected a mapping at the top level of {path}.')
    return payload


def _load_plants(items: list[dict[str, Any]]) -> dict[str, PlantInstance]:
    plants: dict[str, PlantInstance] = {}
    for item in items:
        plant_id = str(item['plant_id'])
        if plant_id in plants:
            raise ValueError(f'Duplicate plant_id in crop catalog: {plant_id}')
        plants[plant_id] = PlantInstance(
            plant_id=plant_id,
            zone_id=str(item['zone_id']),
            display_name=str(item['display_name']),
            world_model_name=str(item['world_model_name']),
            pose=Pose2D.from_dict(item['pose'], f'plants[{plant_id}]'),
        )
    return plants


def _load_tomatoes(items: list[dict[str, Any]]) -> dict[str, TomatoInstance]:
    tomatoes: dict[str, TomatoInstance] = {}
    for item in items:
        tomato_id = str(item['tomato_id'])
        if tomato_id in tomatoes:
            raise ValueError(f'Duplicate tomato_id in crop catalog: {tomato_id}')
        tomatoes[tomato_id] = TomatoInstance(
            tomato_id=tomato_id,
            zone_id=str(item['zone_id']),
            parent_plant_id=str(item['parent_plant_id']),
            display_name=str(item['display_name']),
            world_model_name=str(item['world_model_name']),
            pose=Pose2D.from_dict(item['pose'], f'tomatoes[{tomato_id}]'),
            ready_to_harvest=bool(item.get('ready_to_harvest', False)),
        )
    return tomatoes


def load_crop_catalog(path: Path) -> CropCatalog:
    payload = _load_yaml(path)
    zone_id = str(payload['default_zone_id'])
    catalog = CropCatalog(
        frame_id=str(payload['frame_id']),
        zone_id=zone_id,
        plants=_load_plants(list(payload.get('plants', []))),
        tomatoes=_load_tomatoes(list(payload.get('tomatoes', []))),
    )

    if not catalog.plants:
        raise ValueError('crop_instances.yaml must define at least one plant.')
    if not catalog.tomatoes:
        raise ValueError('crop_instances.yaml must define at least one tomato.')

    for plant in catalog.plants.values():
        if plant.zone_id != catalog.zone_id:
            raise ValueError(
                f'Plant {plant.plant_id} belongs to {plant.zone_id}, expected {catalog.zone_id}.'
            )

    for tomato in catalog.tomatoes.values():
        if tomato.zone_id != catalog.zone_id:
            raise ValueError(
                f'Tomato {tomato.tomato_id} belongs to {tomato.zone_id}, expected {catalog.zone_id}.'
            )
        if tomato.parent_plant_id not in catalog.plants:
            raise ValueError(
                f'Tomato {tomato.tomato_id} references unknown plant {tomato.parent_plant_id}.'
            )

    return catalog


def _route_y_bounds(plan: PatrolPlan, route: PatrolRoute) -> tuple[float, float]:
    referenced_waypoints = (
        route.entry_pose_id,
        *route.inspect_pose_ids,
        route.turn_pose_id,
        route.exit_pose_id,
    )
    y_values = [plan.waypoints[waypoint_id].pose.y for waypoint_id in referenced_waypoints]
    return min(y_values), max(y_values)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _find_observation_context(
    plan: PatrolPlan,
    catalog: CropCatalog,
    tomato_id: str,
) -> HarvestObservationContext:
    tomato = catalog.tomatoes[tomato_id]
    plant_id = tomato.parent_plant_id
    candidates: list[tuple[int, float, PatrolRoute, Waypoint]] = []

    for route in plan.routes.values():
        for inspect_pose_id in route.inspect_pose_ids:
            inspect_waypoint = plan.waypoints[inspect_pose_id]
            score = 0
            if tomato_id in inspect_waypoint.observed_tomato_ids:
                score += 2
            if plant_id in inspect_waypoint.observed_plant_ids:
                score += 1
            if score > 0:
                candidates.append(
                    (
                        score,
                        abs(inspect_waypoint.pose.y - tomato.pose.y),
                        route,
                        inspect_waypoint,
                    )
                )

    if candidates:
        candidates.sort(key=lambda item: (-item[0], item[1], item[2].route_id, item[3].waypoint_id))
        _, _, route, inspect_waypoint = candidates[0]
        return HarvestObservationContext(route=route, inspect_waypoint=inspect_waypoint)

    route_candidates: list[tuple[float, PatrolRoute, Waypoint]] = []
    for route in plan.routes.values():
        if tomato_id not in route.observed_tomato_ids and plant_id not in route.observed_plant_ids:
            continue

        inspect_waypoints = [plan.waypoints[waypoint_id] for waypoint_id in route.inspect_pose_ids]
        inspect_waypoint = min(
            inspect_waypoints,
            key=lambda waypoint: abs(waypoint.pose.y - tomato.pose.y),
        )
        route_candidates.append(
            (
                abs(inspect_waypoint.pose.y - tomato.pose.y),
                route,
                inspect_waypoint,
            )
        )

    if route_candidates:
        route_candidates.sort(key=lambda item: (item[0], item[1].route_id, item[2].waypoint_id))
        _, route, inspect_waypoint = route_candidates[0]
        return HarvestObservationContext(route=route, inspect_waypoint=inspect_waypoint)

    raise ValueError(
        f'No patrol route or inspect waypoint observes tomato {tomato_id} '
        f'(parent plant {plant_id}).'
    )


def _compute_approach_pose(
    plan: PatrolPlan,
    route: PatrolRoute,
    inspect_waypoint: Waypoint,
    tomato: TomatoInstance,
) -> Pose2D:
    margin = plan.harvest_routing.approach_margin_from_bed_edge_m
    lateral_limit = plan.harvest_routing.max_lateral_offset_from_inspect_m
    min_route_y, max_route_y = _route_y_bounds(plan, route)

    if route.lane_side == 'left':
        bed_edge_candidate_x = plan.source_bounds.left_bed_edge_x + margin
        lateral_limit_x = inspect_waypoint.pose.x - lateral_limit
        approach_x = max(bed_edge_candidate_x, lateral_limit_x)
    elif route.lane_side == 'right':
        bed_edge_candidate_x = plan.source_bounds.right_bed_edge_x - margin
        lateral_limit_x = inspect_waypoint.pose.x + lateral_limit
        approach_x = min(bed_edge_candidate_x, lateral_limit_x)
    else:
        raise ValueError(f'Unsupported lane_side for route {route.route_id}: {route.lane_side}')

    approach_y = _clamp(tomato.pose.y, min_route_y, max_route_y)
    return Pose2D(
        x=approach_x,
        y=approach_y,
        z=inspect_waypoint.pose.z,
        yaw=inspect_waypoint.pose.yaw,
    )


def _resolve_return_waypoint_id(
    plan: PatrolPlan,
    context: HarvestObservationContext,
    requested_return_mode: str,
    preferred_return_waypoint_id: str | None,
) -> str:
    if requested_return_mode == 'home':
        return plan.home_pose_id
    if requested_return_mode == 'resume_patrol':
        if preferred_return_waypoint_id and preferred_return_waypoint_id in plan.waypoints:
            return preferred_return_waypoint_id
        return context.inspect_waypoint.waypoint_id
    raise ValueError(
        'requested_return_mode must be either "resume_patrol" or "home", '
        f'got {requested_return_mode!r}.'
    )


def compute_harvest_route(
    plan: PatrolPlan,
    catalog: CropCatalog,
    tomato_id: str,
    *,
    return_mode: str | None = None,
    preferred_return_waypoint_id: str | None = None,
) -> HarvestRoutePlan:
    if plan.zone_id != catalog.zone_id:
        raise ValueError(
            f'Patrol plan zone_id {plan.zone_id} does not match crop catalog zone_id {catalog.zone_id}.'
        )

    if tomato_id not in catalog.tomatoes:
        raise ValueError(f'Unknown tomato_id: {tomato_id}')

    tomato = catalog.tomatoes[tomato_id]
    context = _find_observation_context(plan, catalog, tomato_id)
    requested_return_mode = return_mode or plan.harvest_routing.default_return_mode

    return_waypoint_id = _resolve_return_waypoint_id(
        plan,
        context,
        requested_return_mode,
        preferred_return_waypoint_id,
    )
    fallback_return_mode = plan.harvest_routing.fallback_return_mode
    fallback_return_waypoint_id = _resolve_return_waypoint_id(
        plan,
        context,
        fallback_return_mode,
        None,
    )

    return HarvestRoutePlan(
        tomato_id=tomato.tomato_id,
        plant_id=tomato.parent_plant_id,
        route_id=context.route.route_id,
        lane_side=context.route.lane_side,
        inspect_waypoint_id=context.inspect_waypoint.waypoint_id,
        inspect_waypoint_name=context.inspect_waypoint.display_name,
        approach_pose=_compute_approach_pose(
            plan,
            context.route,
            context.inspect_waypoint,
            tomato,
        ),
        return_mode=requested_return_mode,
        return_waypoint_id=return_waypoint_id,
        fallback_return_waypoint_id=fallback_return_waypoint_id,
        fallback_return_mode=fallback_return_mode,
    )


def _pose_to_dict(pose: Pose2D) -> dict[str, float]:
    return {
        'x': pose.x,
        'y': pose.y,
        'z': pose.z,
        'yaw': pose.yaw,
    }


def _route_plan_to_dict(plan: PatrolPlan, route_plan: HarvestRoutePlan) -> dict[str, Any]:
    return {
        'tomato_id': route_plan.tomato_id,
        'plant_id': route_plan.plant_id,
        'route_id': route_plan.route_id,
        'lane_side': route_plan.lane_side,
        'inspect_waypoint_id': route_plan.inspect_waypoint_id,
        'inspect_waypoint_name': route_plan.inspect_waypoint_name,
        'approach_pose': _pose_to_dict(route_plan.approach_pose),
        'return_mode': route_plan.return_mode,
        'return_waypoint_id': route_plan.return_waypoint_id,
        'return_pose': _pose_to_dict(plan.waypoints[route_plan.return_waypoint_id].pose),
        'fallback_return_mode': route_plan.fallback_return_mode,
        'fallback_return_waypoint_id': route_plan.fallback_return_waypoint_id,
        'fallback_return_pose': _pose_to_dict(
            plan.waypoints[route_plan.fallback_return_waypoint_id].pose
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Compute a harvest approach pose and return target for a tomato.',
    )
    parser.add_argument(
        '--tomato-id',
        required=True,
        help='Canonical tomato ID from agribot_description/config/crop_instances.yaml.',
    )
    parser.add_argument(
        '--patrol-waypoints',
        type=Path,
        default=get_default_patrol_waypoints_path(),
        help='Path to patrol_waypoints.yaml.',
    )
    parser.add_argument(
        '--crop-instances',
        type=Path,
        default=get_default_crop_instances_path(),
        help='Path to crop_instances.yaml.',
    )
    parser.add_argument(
        '--return-mode',
        choices=('resume_patrol', 'home'),
        default=None,
        help='Override the default harvest return mode.',
    )
    parser.add_argument(
        '--preferred-return-waypoint-id',
        default=None,
        help='Optional waypoint to use when return-mode is resume_patrol.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        patrol_plan = load_patrol_plan(args.patrol_waypoints)
        crop_catalog = load_crop_catalog(args.crop_instances)
        route_plan = compute_harvest_route(
            patrol_plan,
            crop_catalog,
            args.tomato_id,
            return_mode=args.return_mode,
            preferred_return_waypoint_id=args.preferred_return_waypoint_id,
        )
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f'Harvest routing failed: {exc}', file=sys.stderr)
        return 1

    print(json.dumps(_route_plan_to_dict(patrol_plan, route_plan), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
