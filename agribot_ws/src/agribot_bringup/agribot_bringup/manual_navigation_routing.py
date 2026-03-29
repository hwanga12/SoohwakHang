from __future__ import annotations

from dataclasses import dataclass
import heapq
import math

from agribot_navigation.patrol_config import PatrolPlan, PatrolRoute, Pose2D


CONNECTOR_Y_TOLERANCE_M = 0.25
CONNECTOR_BAND_SELECTION_TOLERANCE_M = 0.9
LANE_SELECTION_TOLERANCE_M = 1.1
POSE_MATCH_TOLERANCE_M = 0.4
CURRENT_POSE_SKIP_TOLERANCE_M = 0.55
LANE_DIRECTION_SELECTION_TOLERANCE_M = 0.35


@dataclass(frozen=True)
class ManualNavigationRoute:
    target_waypoint_id: str | None
    waypoint_ids: tuple[str, ...]
    poses: tuple[Pose2D, ...]


def pose_distance_xy(left: Pose2D, right: Pose2D) -> float:
    return math.hypot(left.x - right.x, left.y - right.y)


def normalize_waypoint_id(
    plan: PatrolPlan,
    *,
    explicit_waypoint_id: str | None = None,
    target_pose: Pose2D | None = None,
    pose_match_tolerance_m: float = POSE_MATCH_TOLERANCE_M,
) -> str | None:
    if explicit_waypoint_id:
        waypoint_id = explicit_waypoint_id.strip()
        if waypoint_id in plan.waypoints:
            return waypoint_id

    if target_pose is None:
        return None

    best_waypoint_id = ''
    best_distance = float('inf')
    for waypoint_id, waypoint in plan.waypoints.items():
        distance = pose_distance_xy(waypoint.pose, target_pose)
        if distance < best_distance:
            best_distance = distance
            best_waypoint_id = waypoint_id

    if best_waypoint_id and best_distance <= pose_match_tolerance_m:
        return best_waypoint_id
    return None


def select_start_waypoint_id(
    plan: PatrolPlan,
    current_pose: Pose2D | None,
    *,
    target_waypoint_id: str | None = None,
) -> str | None:
    if current_pose is None:
        return None

    target_waypoint = plan.waypoints.get(target_waypoint_id) if target_waypoint_id else None
    target_lane_id = target_waypoint.lane_id if target_waypoint is not None else ''

    nearest_waypoint_id = normalize_waypoint_id(plan, target_pose=current_pose, pose_match_tolerance_m=0.9)
    if nearest_waypoint_id:
        return nearest_waypoint_id

    south_connector_candidates = _connector_waypoint_ids(plan, plan.source_bounds.front_connector_y)
    north_connector_candidates = _connector_waypoint_ids(plan, plan.source_bounds.rear_connector_y)

    if abs(current_pose.y - plan.source_bounds.front_connector_y) <= CONNECTOR_BAND_SELECTION_TOLERANCE_M:
        return _best_connector_candidate(
            plan,
            south_connector_candidates,
            current_pose=current_pose,
            target_waypoint=target_waypoint,
        )

    if abs(current_pose.y - plan.source_bounds.rear_connector_y) <= CONNECTOR_BAND_SELECTION_TOLERANCE_M:
        return _best_connector_candidate(
            plan,
            north_connector_candidates,
            current_pose=current_pose,
            target_waypoint=target_waypoint,
        )

    lane_candidates = [
        waypoint_id
        for waypoint_id, waypoint in plan.waypoints.items()
        if waypoint.lane_id
        and abs(waypoint.pose.x - current_pose.x) <= LANE_SELECTION_TOLERANCE_M
    ]
    if lane_candidates:
        preferred_lane_candidates = [
            waypoint_id
            for waypoint_id in lane_candidates
            if target_lane_id and plan.waypoints[waypoint_id].lane_id == target_lane_id
        ]
        lane_pool = preferred_lane_candidates or lane_candidates
        directional_lane_pool = _filter_lane_candidates_for_target_direction(
            plan,
            lane_pool,
            current_pose=current_pose,
            target_waypoint=target_waypoint,
        )
        lane_pool = directional_lane_pool or lane_pool
        return min(
            lane_pool,
            key=lambda waypoint_id: (
                abs(plan.waypoints[waypoint_id].pose.y - current_pose.y),
                pose_distance_xy(plan.waypoints[waypoint_id].pose, current_pose),
            ),
        )

    route_anchor_waypoint_id = _select_target_route_anchor_waypoint_id(
        plan,
        current_pose=current_pose,
        target_waypoint_id=target_waypoint_id,
    )
    if route_anchor_waypoint_id:
        return route_anchor_waypoint_id

    return min(
        plan.waypoints.keys(),
        key=lambda waypoint_id: _start_waypoint_cost(
            plan,
            waypoint_id,
            current_pose=current_pose,
            target_lane_id=target_lane_id,
        ),
    )


def build_manual_navigation_route(
    plan: PatrolPlan,
    *,
    current_pose: Pose2D | None,
    target_pose: Pose2D,
    explicit_waypoint_id: str | None = None,
) -> ManualNavigationRoute:
    target_waypoint_id = normalize_waypoint_id(
        plan,
        explicit_waypoint_id=explicit_waypoint_id,
        target_pose=target_pose,
    )

    if target_waypoint_id is None:
        return ManualNavigationRoute(
            target_waypoint_id=None,
            waypoint_ids=(),
            poses=(target_pose,),
        )

    start_waypoint_id = select_start_waypoint_id(
        plan,
        current_pose,
        target_waypoint_id=target_waypoint_id,
    )
    if start_waypoint_id is None:
        return ManualNavigationRoute(
            target_waypoint_id=target_waypoint_id,
            waypoint_ids=(target_waypoint_id,),
            poses=(plan.waypoints[target_waypoint_id].pose,),
        )

    waypoint_ids = shortest_waypoint_path(plan, start_waypoint_id, target_waypoint_id)
    poses = tuple(plan.waypoints[waypoint_id].pose for waypoint_id in waypoint_ids)
    if current_pose is not None:
        poses, waypoint_ids = _trim_visited_prefix(
            poses,
            waypoint_ids,
            current_pose=current_pose,
        )

    if not poses:
        poses = (plan.waypoints[target_waypoint_id].pose,)
        waypoint_ids = (target_waypoint_id,)

    final_pose = poses[-1]
    if pose_distance_xy(final_pose, target_pose) > 0.05:
        poses = (*poses, target_pose)

    return ManualNavigationRoute(
        target_waypoint_id=target_waypoint_id,
        waypoint_ids=waypoint_ids,
        poses=poses,
    )


def estimate_navigation_route_cost(
    plan: PatrolPlan,
    *,
    current_pose: Pose2D | None,
    target_waypoint_id: str,
) -> float:
    if target_waypoint_id not in plan.waypoints:
        return float('inf')

    if current_pose is None:
        return 0.0

    start_waypoint_id = select_start_waypoint_id(
        plan,
        current_pose,
        target_waypoint_id=target_waypoint_id,
    )
    if start_waypoint_id is None:
        return float('inf')

    waypoint_path = shortest_waypoint_path(plan, start_waypoint_id, target_waypoint_id)
    if not waypoint_path:
        return float('inf')

    total_cost = pose_distance_xy(current_pose, plan.waypoints[start_waypoint_id].pose)
    for left_waypoint_id, right_waypoint_id in zip(waypoint_path, waypoint_path[1:]):
        total_cost += _edge_distance(plan, left_waypoint_id, right_waypoint_id)

    return total_cost


def select_best_target_waypoint_id(
    plan: PatrolPlan,
    *,
    current_pose: Pose2D | None,
    candidate_waypoint_ids: tuple[str, ...] | list[str],
    preferred_waypoint_id: str | None = None,
) -> str | None:
    normalized_candidates = tuple(
        dict.fromkeys(
            waypoint_id.strip()
            for waypoint_id in candidate_waypoint_ids
            if waypoint_id.strip() in plan.waypoints
        )
    )

    if not normalized_candidates:
        if preferred_waypoint_id and preferred_waypoint_id in plan.waypoints:
            return preferred_waypoint_id
        return None

    if len(normalized_candidates) == 1:
        return normalized_candidates[0]

    return min(
        normalized_candidates,
        key=lambda waypoint_id: (
            estimate_navigation_route_cost(
                plan,
                current_pose=current_pose,
                target_waypoint_id=waypoint_id,
            ),
            0 if preferred_waypoint_id and waypoint_id == preferred_waypoint_id else 1,
            abs(plan.waypoints[waypoint_id].pose.x),
            waypoint_id,
        ),
    )


def shortest_waypoint_path(
    plan: PatrolPlan,
    start_waypoint_id: str,
    target_waypoint_id: str,
) -> tuple[str, ...]:
    if start_waypoint_id == target_waypoint_id:
        return (target_waypoint_id,)

    adjacency = build_waypoint_adjacency(plan)
    queue: list[tuple[float, str]] = [(0.0, start_waypoint_id)]
    distances = {start_waypoint_id: 0.0}
    previous: dict[str, str] = {}

    while queue:
        current_distance, current_waypoint_id = heapq.heappop(queue)
        if current_waypoint_id == target_waypoint_id:
            break
        if current_distance > distances.get(current_waypoint_id, float('inf')):
            continue

        for neighbor_id in adjacency.get(current_waypoint_id, ()):
            next_distance = current_distance + _edge_distance(plan, current_waypoint_id, neighbor_id)
            if next_distance >= distances.get(neighbor_id, float('inf')):
                continue
            distances[neighbor_id] = next_distance
            previous[neighbor_id] = current_waypoint_id
            heapq.heappush(queue, (next_distance, neighbor_id))

    if target_waypoint_id not in distances:
        return (target_waypoint_id,)

    path = [target_waypoint_id]
    current_waypoint_id = target_waypoint_id
    while current_waypoint_id != start_waypoint_id:
        current_waypoint_id = previous[current_waypoint_id]
        path.append(current_waypoint_id)
    path.reverse()
    return tuple(path)


def build_waypoint_adjacency(plan: PatrolPlan) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {
        waypoint_id: set()
        for waypoint_id in plan.waypoints.keys()
    }

    for route in plan.routes.values():
        ordered_waypoints = (
            route.entry_pose_id,
            *route.inspect_pose_ids,
            route.turn_pose_id,
        )
        for index in range(len(ordered_waypoints) - 1):
            left = ordered_waypoints[index]
            right = ordered_waypoints[index + 1]
            adjacency[left].add(right)
            adjacency[right].add(left)

    for connector_y in (
        plan.source_bounds.front_connector_y,
        plan.source_bounds.rear_connector_y,
    ):
        connector_waypoint_ids = _connector_waypoint_ids(plan, connector_y)
        for index, left in enumerate(connector_waypoint_ids):
            for right in connector_waypoint_ids[index + 1:]:
                adjacency[left].add(right)
                adjacency[right].add(left)

    return adjacency


def _connector_waypoint_ids(plan: PatrolPlan, connector_y: float) -> list[str]:
    connector_waypoint_ids = [
        waypoint_id
        for waypoint_id, waypoint in plan.waypoints.items()
        if abs(waypoint.pose.y - connector_y) <= CONNECTOR_Y_TOLERANCE_M
    ]
    connector_waypoint_ids.sort(key=lambda waypoint_id: plan.waypoints[waypoint_id].pose.x)
    return connector_waypoint_ids


def _best_connector_candidate(
    plan: PatrolPlan,
    candidate_ids: list[str],
    *,
    current_pose: Pose2D,
    target_waypoint: object | None,
) -> str | None:
    if not candidate_ids:
        return None

    target_pose = target_waypoint.pose if target_waypoint is not None else None
    target_lane_id = target_waypoint.lane_id if target_waypoint is not None else ''
    return min(
        candidate_ids,
        key=lambda waypoint_id: (
            abs(plan.waypoints[waypoint_id].pose.x - current_pose.x),
            0 if target_lane_id and plan.waypoints[waypoint_id].lane_id == target_lane_id else 1,
            abs(plan.waypoints[waypoint_id].pose.x - target_pose.x) if target_pose is not None else 0.0,
        ),
    )


def _filter_lane_candidates_for_target_direction(
    plan: PatrolPlan,
    candidate_ids: list[str],
    *,
    current_pose: Pose2D,
    target_waypoint: object | None,
) -> list[str]:
    if not candidate_ids or target_waypoint is None:
        return candidate_ids

    delta_y = target_waypoint.pose.y - current_pose.y
    if abs(delta_y) <= LANE_DIRECTION_SELECTION_TOLERANCE_M:
        return candidate_ids

    if delta_y > 0.0:
        forward_candidates = [
            waypoint_id
            for waypoint_id in candidate_ids
            if plan.waypoints[waypoint_id].pose.y
            >= current_pose.y - LANE_DIRECTION_SELECTION_TOLERANCE_M
        ]
    else:
        forward_candidates = [
            waypoint_id
            for waypoint_id in candidate_ids
            if plan.waypoints[waypoint_id].pose.y
            <= current_pose.y + LANE_DIRECTION_SELECTION_TOLERANCE_M
        ]

    return forward_candidates or candidate_ids


def _select_target_route_anchor_waypoint_id(
    plan: PatrolPlan,
    *,
    current_pose: Pose2D,
    target_waypoint_id: str | None,
) -> str | None:
    if not target_waypoint_id:
        return None

    route = _find_route_for_waypoint_id(plan, target_waypoint_id)
    if route is None:
        return None

    anchor_waypoint_ids = [route.entry_pose_id, route.turn_pose_id]
    return min(
        anchor_waypoint_ids,
        key=lambda waypoint_id: (
            abs(plan.waypoints[waypoint_id].pose.y - current_pose.y),
            pose_distance_xy(plan.waypoints[waypoint_id].pose, current_pose),
        ),
    )


def _find_route_for_waypoint_id(plan: PatrolPlan, waypoint_id: str) -> PatrolRoute | None:
    for route in plan.routes.values():
        if waypoint_id in (
            route.entry_pose_id,
            *route.inspect_pose_ids,
            route.turn_pose_id,
            route.exit_pose_id,
        ):
            return route
    return None


def _start_waypoint_cost(
    plan: PatrolPlan,
    waypoint_id: str,
    *,
    current_pose: Pose2D,
    target_lane_id: str,
) -> float:
    waypoint = plan.waypoints[waypoint_id]
    distance = pose_distance_xy(waypoint.pose, current_pose)
    lane_bonus = -0.45 if target_lane_id and waypoint.lane_id == target_lane_id else 0.0
    connector_bonus = -0.15 if waypoint.purpose in {'entry', 'turn', 'home'} else 0.0
    return distance + lane_bonus + connector_bonus


def _edge_distance(plan: PatrolPlan, left_waypoint_id: str, right_waypoint_id: str) -> float:
    return pose_distance_xy(plan.waypoints[left_waypoint_id].pose, plan.waypoints[right_waypoint_id].pose)


def _trim_visited_prefix(
    poses: tuple[Pose2D, ...],
    waypoint_ids: tuple[str, ...],
    *,
    current_pose: Pose2D,
) -> tuple[tuple[Pose2D, ...], tuple[str, ...]]:
    trimmed_index = 0
    for index, pose in enumerate(poses):
        if pose_distance_xy(pose, current_pose) <= CURRENT_POSE_SKIP_TOLERANCE_M:
            trimmed_index = index + 1
            continue
        break

    return poses[trimmed_index:], waypoint_ids[trimmed_index:]
