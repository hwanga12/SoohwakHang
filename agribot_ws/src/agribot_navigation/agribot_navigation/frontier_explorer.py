"""Hybrid exploration supervisor for autonomous SLAM mapping sessions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
from typing import Any

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import Point, PoseStamped, Twist
from nav2_msgs.action import BackUp, DriveOnHeading, NavigateToPose, Spin
from nav_msgs.msg import OccupancyGrid
import rclpy
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformException, TransformListener


UNKNOWN = -1
FREE_THRESHOLD = 20
OCCUPIED_THRESHOLD = 50

MODE_IDLE = 'idle'
MODE_STARTING = 'starting'
MODE_BOOTSTRAP = 'bootstrap_find_wall'
MODE_BOUNDARY = 'boundary_follow'
MODE_FRONTIER = 'frontier_explore'
MODE_RECOVERY = 'recovery_escape'
MODE_COVERAGE = 'coverage_fill'
MODE_STOPPING = 'stopping'
MODE_STOPPED = 'stopped'
MODE_COMPLETED = 'completed'
MODE_ERROR = 'error'


@dataclass(frozen=True)
class RobotPose:
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class FrontierCandidate:
    map_x: int
    map_y: int
    world_x: float
    world_y: float
    size: int
    distance_m: float
    score: float
    support_score: float
    forward_score: float


@dataclass(frozen=True)
class RecoveryCommand:
    kind: str
    distance_or_yaw: float
    speed: float
    time_allowance_sec: float
    description: str


@dataclass
class BlacklistRegion:
    x: float
    y: float
    expires_at_ns: int


@dataclass(frozen=True)
class CoverageGoal:
    world_x: float
    world_y: float
    heading: float


def map_index(width: int, x: int, y: int) -> int:
    return y * width + x


def is_free(value: int) -> bool:
    return 0 <= value <= FREE_THRESHOLD


def is_unknown(value: int) -> bool:
    return value == UNKNOWN


def is_occupied(value: int) -> bool:
    return value >= OCCUPIED_THRESHOLD


def normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def iter_neighbors(x: int, y: int, width: int, height: int) -> tuple[tuple[int, int], ...]:
    neighbors: list[tuple[int, int]] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx = x + dx
            ny = y + dy
            if 0 <= nx < width and 0 <= ny < height:
                neighbors.append((nx, ny))
    return tuple(neighbors)


def is_frontier_cell(
    data: list[int] | tuple[int, ...],
    width: int,
    height: int,
    x: int,
    y: int,
) -> bool:
    if not is_free(data[map_index(width, x, y)]):
        return False
    return any(
        is_unknown(data[map_index(width, nx, ny)])
        for nx, ny in iter_neighbors(x, y, width, height)
    )


def frontier_clusters(
    map_msg: OccupancyGrid,
    minimum_cluster_size: int,
) -> list[list[tuple[int, int]]]:
    width = int(map_msg.info.width)
    height = int(map_msg.info.height)
    if width <= 0 or height <= 0:
        return []

    data = map_msg.data
    visited = bytearray(width * height)
    clusters: list[list[tuple[int, int]]] = []

    for y in range(height):
        row_offset = y * width
        for x in range(width):
            idx = row_offset + x
            if visited[idx]:
                continue
            visited[idx] = 1
            if not is_frontier_cell(data, width, height, x, y):
                continue

            cluster: list[tuple[int, int]] = []
            queue = deque([(x, y)])
            while queue:
                cx, cy = queue.popleft()
                cluster.append((cx, cy))
                for nx, ny in iter_neighbors(cx, cy, width, height):
                    nidx = map_index(width, nx, ny)
                    if visited[nidx]:
                        continue
                    visited[nidx] = 1
                    if is_frontier_cell(data, width, height, nx, ny):
                        queue.append((nx, ny))

            if len(cluster) >= minimum_cluster_size:
                clusters.append(cluster)

    return clusters


def map_to_world(map_msg: OccupancyGrid, x: int, y: int) -> tuple[float, float]:
    origin = map_msg.info.origin.position
    resolution = float(map_msg.info.resolution)
    world_x = origin.x + (x + 0.5) * resolution
    world_y = origin.y + (y + 0.5) * resolution
    return world_x, world_y


def world_to_map(map_msg: OccupancyGrid, x: float, y: float) -> tuple[int, int] | None:
    resolution = float(map_msg.info.resolution)
    if resolution <= 0.0:
        return None
    origin = map_msg.info.origin.position
    map_x = int(math.floor((x - origin.x) / resolution))
    map_y = int(math.floor((y - origin.y) / resolution))
    if 0 <= map_x < int(map_msg.info.width) and 0 <= map_y < int(map_msg.info.height):
        return map_x, map_y
    return None


def is_blacklisted(
    world_x: float,
    world_y: float,
    blacklisted_points: list[tuple[float, float]],
    blacklist_radius_m: float,
) -> bool:
    radius_sq = blacklist_radius_m * blacklist_radius_m
    return any(
        (world_x - blocked_x) ** 2 + (world_y - blocked_y) ** 2 <= radius_sq
        for blocked_x, blocked_y in blacklisted_points
    )


def boundary_allows(boundary_map: OccupancyGrid | None, world_x: float, world_y: float) -> bool:
    if boundary_map is None:
        return True
    coords = world_to_map(boundary_map, world_x, world_y)
    if coords is None:
        return False
    value = boundary_map.data[map_index(int(boundary_map.info.width), coords[0], coords[1])]
    return is_free(value)


def count_free_support(
    data: list[int] | tuple[int, ...],
    width: int,
    height: int,
    x: int,
    y: int,
    radius_cells: int,
) -> int:
    support = 0
    radius_sq = radius_cells * radius_cells
    for ny in range(max(0, y - radius_cells), min(height, y + radius_cells + 1)):
        for nx in range(max(0, x - radius_cells), min(width, x + radius_cells + 1)):
            if (nx - x) ** 2 + (ny - y) ** 2 > radius_sq:
                continue
            if is_free(data[map_index(width, nx, ny)]):
                support += 1
    return support


def find_staging_cell(
    map_msg: OccupancyGrid,
    *,
    frontier_cell: tuple[int, int],
    robot_cell: tuple[int, int],
    standoff_cells: int,
    search_radius_cells: int,
    support_radius_cells: int,
) -> tuple[tuple[int, int], float] | None:
    width = int(map_msg.info.width)
    height = int(map_msg.info.height)
    data = map_msg.data
    frontier_x, frontier_y = frontier_cell
    robot_x, robot_y = robot_cell

    direction_x = frontier_x - robot_x
    direction_y = frontier_y - robot_y
    length = math.hypot(direction_x, direction_y)
    if length <= 1.0e-6:
        direction_x, direction_y = 1.0, 0.0
        length = 1.0

    target_x = int(round(frontier_x - direction_x / length * standoff_cells))
    target_y = int(round(frontier_y - direction_y / length * standoff_cells))

    best_cell: tuple[int, int] | None = None
    best_score = float('-inf')
    for ny in range(max(0, target_y - search_radius_cells), min(height, target_y + search_radius_cells + 1)):
        for nx in range(max(0, target_x - search_radius_cells), min(width, target_x + search_radius_cells + 1)):
            value = data[map_index(width, nx, ny)]
            if not is_free(value):
                continue

            support = count_free_support(data, width, height, nx, ny, support_radius_cells)
            offset_penalty = math.hypot(nx - target_x, ny - target_y)
            frontier_penalty = abs(
                math.hypot(nx - frontier_x, ny - frontier_y) - float(standoff_cells)
            )
            score = support - 0.8 * offset_penalty - 0.6 * frontier_penalty
            if score > best_score:
                best_score = score
                best_cell = (nx, ny)

    if best_cell is None:
        return None

    return best_cell, best_score


def scan_ranges(scan_msg: LaserScan) -> list[float]:
    valid_ranges: list[float] = []
    range_min = float(scan_msg.range_min)
    range_max = float(scan_msg.range_max)
    for reading in scan_msg.ranges:
        if math.isfinite(reading) and range_min <= reading <= range_max:
            valid_ranges.append(float(reading))
        else:
            valid_ranges.append(range_max)
    return valid_ranges


def sector_clearance(
    scan_msg: LaserScan,
    *,
    center_angle: float,
    window_angle: float,
    clearance_percentile: float = 0.20,
) -> float:
    ranges = scan_ranges(scan_msg)
    if not ranges:
        return 0.0

    angle_increment = float(scan_msg.angle_increment)
    if abs(angle_increment) < 1e-9:
        return 0.0

    sector_ranges: list[float] = []
    for index, reading in enumerate(ranges):
        angle = float(scan_msg.angle_min + index * angle_increment)
        if abs(normalize_angle(angle - center_angle)) > window_angle:
            continue
        sector_ranges.append(reading)

    if not sector_ranges:
        return 0.0

    percentile = min(max(clearance_percentile, 0.0), 1.0)
    sector_ranges.sort()
    percentile_index = int(math.floor(percentile * (len(sector_ranges) - 1)))
    return sector_ranges[percentile_index]


def choose_open_heading(
    scan_msg: LaserScan,
    *,
    preferred_heading: float = 0.0,
    heading_window: float = 0.45,
    sample_count: int = 72,
    forward_bias_weight: float = 1.2,
    clearance_percentile: float = 0.20,
) -> tuple[float | None, float, float]:
    ranges = scan_ranges(scan_msg)
    if not ranges:
        return None, 0.0, float('-inf')

    step = max(1, len(ranges) // max(sample_count, 1))
    best_angle: float | None = None
    best_clearance = 0.0
    best_score = float('-inf')
    for index in range(0, len(ranges), step):
        angle = float(scan_msg.angle_min + index * scan_msg.angle_increment)
        clearance = sector_clearance(
            scan_msg,
            center_angle=angle,
            window_angle=heading_window,
            clearance_percentile=clearance_percentile,
        )
        heading_error = abs(normalize_angle(angle - preferred_heading))
        score = clearance + forward_bias_weight * math.cos(heading_error)
        if score > best_score:
            best_angle = angle
            best_clearance = clearance
            best_score = score

    return best_angle, best_clearance, best_score


def wall_follow_command(
    *,
    front_clearance: float,
    side_clearance: float,
    diagonal_clearance: float,
    target_distance: float,
    front_stop_distance: float,
    wall_lost_distance: float,
    linear_speed: float,
    max_angular_speed: float,
    side_gain: float,
    diagonal_gain: float,
    follow_side: str,
) -> tuple[float, float]:
    if follow_side not in {'left', 'right'}:
        follow_side = 'right'

    if front_clearance < front_stop_distance:
        return 0.0, max_angular_speed if follow_side == 'right' else -max_angular_speed

    if side_clearance > wall_lost_distance:
        search_turn = -0.65 * max_angular_speed if follow_side == 'right' else 0.65 * max_angular_speed
        return 0.12, search_turn

    sign = 1.0 if follow_side == 'right' else -1.0
    side_error = target_distance - side_clearance
    diagonal_error = target_distance - diagonal_clearance
    angular_z = sign * (side_gain * side_error + diagonal_gain * diagonal_error)
    angular_z = clamp(angular_z, -max_angular_speed, max_angular_speed)
    speed_scale = max(0.30, 1.0 - abs(angular_z) / max(max_angular_speed, 1.0e-6))
    linear_x = linear_speed * speed_scale
    return linear_x, angular_z


def compute_known_ratio(map_msg: OccupancyGrid | None) -> float:
    if map_msg is None or not map_msg.data:
        return 0.0
    known = sum(1 for value in map_msg.data if value != UNKNOWN)
    return known / float(len(map_msg.data))


def bootstrap_ready_for_frontier(
    *,
    has_candidates: bool,
    known_ratio: float,
    known_ratio_threshold: float,
    bootstrap_passes: int,
    minimum_passes: int,
    bootstrap_total_distance_m: float,
    minimum_total_distance_m: float,
) -> bool:
    if not has_candidates or known_ratio < known_ratio_threshold:
        return False
    if bootstrap_passes < minimum_passes:
        return False
    if bootstrap_total_distance_m < minimum_total_distance_m:
        return False
    return True


def build_frontier_candidates(
    map_msg: OccupancyGrid,
    *,
    robot_pose: RobotPose,
    minimum_cluster_size: int,
    minimum_goal_distance_m: float,
    cluster_size_weight: float,
    maximum_distance_score_m: float,
    support_area_weight: float,
    forward_preference_weight: float,
    frontier_standoff_m: float,
    staging_search_radius_m: float,
    staging_support_radius_m: float,
    blacklisted_points: list[tuple[float, float]],
    blacklist_radius_m: float,
    boundary_map: OccupancyGrid | None = None,
) -> list[FrontierCandidate]:
    robot_cell = world_to_map(map_msg, robot_pose.x, robot_pose.y)
    if robot_cell is None:
        return []

    resolution = float(map_msg.info.resolution)
    standoff_cells = max(1, int(round(frontier_standoff_m / resolution)))
    search_radius_cells = max(1, int(round(staging_search_radius_m / resolution)))
    support_radius_cells = max(1, int(round(staging_support_radius_m / resolution)))

    candidates: list[FrontierCandidate] = []
    for cluster in frontier_clusters(map_msg, minimum_cluster_size):
        rep_x, rep_y = max(
            cluster,
            key=lambda cell: (cell[0] - robot_cell[0]) ** 2 + (cell[1] - robot_cell[1]) ** 2,
        )
        staging = find_staging_cell(
            map_msg,
            frontier_cell=(rep_x, rep_y),
            robot_cell=robot_cell,
            standoff_cells=standoff_cells,
            search_radius_cells=search_radius_cells,
            support_radius_cells=support_radius_cells,
        )
        if staging is None:
            continue

        (goal_x, goal_y), support_score = staging
        world_x, world_y = map_to_world(map_msg, goal_x, goal_y)
        if not boundary_allows(boundary_map, world_x, world_y):
            continue
        if is_blacklisted(world_x, world_y, blacklisted_points, blacklist_radius_m):
            continue

        distance_m = math.hypot(world_x - robot_pose.x, world_y - robot_pose.y)
        if distance_m < minimum_goal_distance_m:
            continue

        heading = math.atan2(world_y - robot_pose.y, world_x - robot_pose.x)
        forward_score = (math.cos(normalize_angle(heading - robot_pose.yaw)) + 1.0) * 0.5
        cluster_span_m = len(cluster) * resolution
        score = (
            min(distance_m, maximum_distance_score_m)
            + cluster_size_weight * cluster_span_m
            + support_area_weight * support_score
            + forward_preference_weight * forward_score
        )
        candidates.append(
            FrontierCandidate(
                map_x=goal_x,
                map_y=goal_y,
                world_x=world_x,
                world_y=world_y,
                size=len(cluster),
                distance_m=distance_m,
                score=score,
                support_score=support_score,
                forward_score=forward_score,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.score,
            candidate.support_score,
            candidate.forward_score,
            candidate.distance_m,
        ),
        reverse=True,
    )


def build_coverage_fill_goals(
    map_msg: OccupancyGrid,
    *,
    robot_pose: RobotPose,
    lane_spacing_m: float,
    minimum_segment_length_m: float,
    boundary_map: OccupancyGrid | None = None,
) -> list[CoverageGoal]:
    width = int(map_msg.info.width)
    height = int(map_msg.info.height)
    if width <= 0 or height <= 0:
        return []

    resolution = float(map_msg.info.resolution)
    lane_step = max(1, int(round(lane_spacing_m / resolution)))
    min_segment_cells = max(2, int(round(minimum_segment_length_m / resolution)))
    goals: list[CoverageGoal] = []
    direction = 1

    for y in range(0, height, lane_step):
        segments: list[tuple[int, int]] = []
        segment_start: int | None = None
        for x in range(width):
            value = map_msg.data[map_index(width, x, y)]
            if is_free(value):
                if segment_start is None:
                    segment_start = x
                continue

            if segment_start is not None and x - segment_start >= min_segment_cells:
                segments.append((segment_start, x - 1))
            segment_start = None

        if segment_start is not None and width - segment_start >= min_segment_cells:
            segments.append((segment_start, width - 1))

        if not segments:
            continue

        start_x, end_x = max(segments, key=lambda item: item[1] - item[0])
        target_x = end_x if direction > 0 else start_x
        world_x, world_y = map_to_world(map_msg, target_x, y)
        if not boundary_allows(boundary_map, world_x, world_y):
            direction *= -1
            continue
        heading = 0.0 if direction > 0 else math.pi
        goals.append(CoverageGoal(world_x=world_x, world_y=world_y, heading=heading))
        direction *= -1

    if not goals:
        return []

    closest_index = min(
        range(len(goals)),
        key=lambda idx: math.hypot(goals[idx].world_x - robot_pose.x, goals[idx].world_y - robot_pose.y),
    )
    return goals[closest_index:] + goals[:closest_index]


class FrontierExplorerNode(Node):
    """Supervise bootstrap, boundary follow, frontier explore, recovery, and fill passes."""

    def __init__(self) -> None:
        super().__init__('frontier_explorer')

        self.declare_parameter('map_topic', '/map')
        self.declare_parameter('boundary_map_topic', '/exploration_boundary_map')
        self.declare_parameter('scan_topic', '/agribot/lidar')
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('use_boundary_map', False)
        self.declare_parameter('goal_frame', 'map')
        self.declare_parameter('bootstrap_pose_frame', 'odom')
        self.declare_parameter('robot_base_frame', 'base_link')
        self.declare_parameter('navigate_to_pose_action', 'navigate_to_pose')
        self.declare_parameter('spin_action', 'spin')
        self.declare_parameter('backup_action', 'backup')
        self.declare_parameter('drive_on_heading_action', 'drive_on_heading')
        self.declare_parameter('status_topic', 'mapping_explorer/status')
        self.declare_parameter('start_service', 'mapping_explorer/start')
        self.declare_parameter('stop_service', 'mapping_explorer/stop')
        self.declare_parameter('resume_service', 'mapping_explorer/resume')
        self.declare_parameter('auto_start', True)
        self.declare_parameter('planning_period_sec', 0.15)

        self.declare_parameter('minimum_frontier_cluster_size', 10)
        self.declare_parameter('minimum_goal_distance_m', 1.2)
        self.declare_parameter('cluster_size_weight', 2.5)
        self.declare_parameter('maximum_distance_score_m', 8.0)
        self.declare_parameter('support_area_weight', 0.18)
        self.declare_parameter('forward_preference_weight', 1.5)
        self.declare_parameter('frontier_standoff_m', 0.60)
        self.declare_parameter('staging_search_radius_m', 0.50)
        self.declare_parameter('staging_support_radius_m', 0.35)
        self.declare_parameter('blacklist_radius_m', 1.0)
        self.declare_parameter('blacklist_duration_sec', 45.0)
        self.declare_parameter('progress_timeout_sec', 18.0)
        self.declare_parameter('progress_required_distance_m', 0.35)
        self.declare_parameter('no_frontier_confirmations', 5)
        self.declare_parameter('scan_timeout_sec', 1.0)
        self.declare_parameter('pose_reuse_timeout_sec', 1.0)
        self.declare_parameter('heading_window_rad', 0.45)
        self.declare_parameter('heading_forward_bias_weight', 1.2)
        self.declare_parameter('heading_clearance_percentile', 0.2)
        self.declare_parameter('frontier_completion_known_ratio', 0.92)

        self.declare_parameter('bootstrap_drive_distance_m', 1.25)
        self.declare_parameter('bootstrap_drive_speed_mps', 0.22)
        self.declare_parameter('bootstrap_drive_timeout_sec', 8.0)
        self.declare_parameter('bootstrap_front_clearance_m', 1.4)
        self.declare_parameter('bootstrap_max_passes', 4)
        self.declare_parameter('bootstrap_min_passes_before_frontier', 2)
        self.declare_parameter('bootstrap_min_total_distance_m', 2.4)
        self.declare_parameter('bootstrap_known_ratio_for_frontier', 0.06)

        self.declare_parameter('boundary_follow_target_distance_m', 0.60)
        self.declare_parameter('boundary_follow_front_stop_m', 0.75)
        self.declare_parameter('boundary_follow_wall_lost_m', 1.25)
        self.declare_parameter('boundary_follow_linear_speed_mps', 0.24)
        self.declare_parameter('boundary_follow_max_angular_speed_rps', 0.90)
        self.declare_parameter('boundary_follow_side_gain', 2.6)
        self.declare_parameter('boundary_follow_diagonal_gain', 1.6)
        self.declare_parameter('boundary_follow_min_duration_sec', 8.0)
        self.declare_parameter('boundary_follow_min_distance_m', 3.0)
        self.declare_parameter('boundary_follow_stuck_timeout_sec', 4.0)
        self.declare_parameter('boundary_follow_progress_distance_m', 0.18)

        self.declare_parameter('recovery_backup_distance_m', 0.50)
        self.declare_parameter('recovery_backup_speed_mps', 0.12)
        self.declare_parameter('recovery_drive_distance_m', 0.60)
        self.declare_parameter('recovery_drive_speed_mps', 0.18)
        self.declare_parameter('recovery_default_spin_rad', 3.141592653589793)

        self.declare_parameter('enable_coverage_fill', True)
        self.declare_parameter('coverage_known_ratio_threshold', 0.80)
        self.declare_parameter('coverage_lane_spacing_m', 0.80)
        self.declare_parameter('coverage_min_segment_length_m', 1.2)

        self._map_topic = str(self.get_parameter('map_topic').value)
        self._boundary_map_topic = str(self.get_parameter('boundary_map_topic').value)
        self._scan_topic = str(self.get_parameter('scan_topic').value)
        self._cmd_vel_topic = str(self.get_parameter('cmd_vel_topic').value)
        self._use_boundary_map = bool(self.get_parameter('use_boundary_map').value)
        self._goal_frame = str(self.get_parameter('goal_frame').value)
        self._bootstrap_pose_frame = str(self.get_parameter('bootstrap_pose_frame').value)
        self._robot_base_frame = str(self.get_parameter('robot_base_frame').value)
        self._planning_period_sec = float(self.get_parameter('planning_period_sec').value)
        self._minimum_frontier_cluster_size = int(
            self.get_parameter('minimum_frontier_cluster_size').value
        )
        self._minimum_goal_distance_m = float(self.get_parameter('minimum_goal_distance_m').value)
        self._cluster_size_weight = float(self.get_parameter('cluster_size_weight').value)
        self._maximum_distance_score_m = float(
            self.get_parameter('maximum_distance_score_m').value
        )
        self._support_area_weight = float(self.get_parameter('support_area_weight').value)
        self._forward_preference_weight = float(
            self.get_parameter('forward_preference_weight').value
        )
        self._frontier_standoff_m = float(self.get_parameter('frontier_standoff_m').value)
        self._staging_search_radius_m = float(
            self.get_parameter('staging_search_radius_m').value
        )
        self._staging_support_radius_m = float(
            self.get_parameter('staging_support_radius_m').value
        )
        self._blacklist_radius_m = float(self.get_parameter('blacklist_radius_m').value)
        self._blacklist_duration = Duration(
            seconds=float(self.get_parameter('blacklist_duration_sec').value)
        )
        self._progress_timeout = Duration(
            seconds=float(self.get_parameter('progress_timeout_sec').value)
        )
        self._progress_required_distance_m = float(
            self.get_parameter('progress_required_distance_m').value
        )
        self._no_frontier_confirmations = int(
            self.get_parameter('no_frontier_confirmations').value
        )
        self._scan_timeout = Duration(seconds=float(self.get_parameter('scan_timeout_sec').value))
        self._pose_reuse_timeout = Duration(
            seconds=float(self.get_parameter('pose_reuse_timeout_sec').value)
        )
        self._heading_window = float(self.get_parameter('heading_window_rad').value)
        self._heading_forward_bias_weight = float(
            self.get_parameter('heading_forward_bias_weight').value
        )
        self._heading_clearance_percentile = float(
            self.get_parameter('heading_clearance_percentile').value
        )
        self._frontier_completion_known_ratio = float(
            self.get_parameter('frontier_completion_known_ratio').value
        )

        self._bootstrap_drive_distance_m = float(
            self.get_parameter('bootstrap_drive_distance_m').value
        )
        self._bootstrap_drive_speed_mps = float(
            self.get_parameter('bootstrap_drive_speed_mps').value
        )
        self._bootstrap_drive_timeout = Duration(
            seconds=float(self.get_parameter('bootstrap_drive_timeout_sec').value)
        )
        self._bootstrap_front_clearance_m = float(
            self.get_parameter('bootstrap_front_clearance_m').value
        )
        self._bootstrap_max_passes = int(self.get_parameter('bootstrap_max_passes').value)
        self._bootstrap_min_passes_before_frontier = int(
            self.get_parameter('bootstrap_min_passes_before_frontier').value
        )
        self._bootstrap_min_total_distance_m = float(
            self.get_parameter('bootstrap_min_total_distance_m').value
        )
        self._bootstrap_known_ratio_for_frontier = float(
            self.get_parameter('bootstrap_known_ratio_for_frontier').value
        )

        self._boundary_follow_target_distance_m = float(
            self.get_parameter('boundary_follow_target_distance_m').value
        )
        self._boundary_follow_front_stop_m = float(
            self.get_parameter('boundary_follow_front_stop_m').value
        )
        self._boundary_follow_wall_lost_m = float(
            self.get_parameter('boundary_follow_wall_lost_m').value
        )
        self._boundary_follow_linear_speed_mps = float(
            self.get_parameter('boundary_follow_linear_speed_mps').value
        )
        self._boundary_follow_max_angular_speed_rps = float(
            self.get_parameter('boundary_follow_max_angular_speed_rps').value
        )
        self._boundary_follow_side_gain = float(
            self.get_parameter('boundary_follow_side_gain').value
        )
        self._boundary_follow_diagonal_gain = float(
            self.get_parameter('boundary_follow_diagonal_gain').value
        )
        self._boundary_follow_min_duration = Duration(
            seconds=float(self.get_parameter('boundary_follow_min_duration_sec').value)
        )
        self._boundary_follow_min_distance_m = float(
            self.get_parameter('boundary_follow_min_distance_m').value
        )
        self._boundary_follow_stuck_timeout = Duration(
            seconds=float(self.get_parameter('boundary_follow_stuck_timeout_sec').value)
        )
        self._boundary_follow_progress_distance_m = float(
            self.get_parameter('boundary_follow_progress_distance_m').value
        )

        self._recovery_backup_distance_m = float(
            self.get_parameter('recovery_backup_distance_m').value
        )
        self._recovery_backup_speed_mps = float(
            self.get_parameter('recovery_backup_speed_mps').value
        )
        self._recovery_drive_distance_m = float(
            self.get_parameter('recovery_drive_distance_m').value
        )
        self._recovery_drive_speed_mps = float(
            self.get_parameter('recovery_drive_speed_mps').value
        )
        self._recovery_default_spin_rad = float(
            self.get_parameter('recovery_default_spin_rad').value
        )

        self._enable_coverage_fill = bool(self.get_parameter('enable_coverage_fill').value)
        self._coverage_known_ratio_threshold = float(
            self.get_parameter('coverage_known_ratio_threshold').value
        )
        self._coverage_lane_spacing_m = float(self.get_parameter('coverage_lane_spacing_m').value)
        self._coverage_min_segment_length_m = float(
            self.get_parameter('coverage_min_segment_length_m').value
        )

        action_name = str(self.get_parameter('navigate_to_pose_action').value)
        self._spin_action_name = str(self.get_parameter('spin_action').value)
        self._backup_action_name = str(self.get_parameter('backup_action').value)
        self._drive_action_name = str(self.get_parameter('drive_on_heading_action').value)
        status_topic = str(self.get_parameter('status_topic').value)
        start_service = str(self.get_parameter('start_service').value)
        stop_service = str(self.get_parameter('stop_service').value)
        resume_service = str(self.get_parameter('resume_service').value)

        now = self.get_clock().now()
        self._map: OccupancyGrid | None = None
        self._boundary_map: OccupancyGrid | None = None
        self._latest_scan: LaserScan | None = None
        self._latest_scan_time = now
        self._last_robot_pose: RobotPose | None = None
        self._last_robot_pose_time = now
        self._active = bool(self.get_parameter('auto_start').value)
        self._mode = MODE_BOOTSTRAP if self._active else MODE_IDLE
        self._state_message = (
            'Hybrid exploration auto-started.' if self._active else 'Explorer is idle.'
        )
        self._last_error_message = ''
        self._last_distance_remaining_m: float | None = None
        self._last_progress_distance_remaining_m: float | None = None
        self._last_progress_time = now
        self._blacklisted_regions: list[BlacklistRegion] = []
        self._no_frontier_counter = 0
        self._bootstrap_passes = 0
        self._bootstrap_total_distance_m = 0.0
        self._bootstrap_drive_active = False
        self._bootstrap_drive_start_pose: RobotPose | None = None
        self._bootstrap_drive_started_at = now
        self._boundary_side = 'right'
        self._boundary_started_at = now
        self._boundary_last_pose: RobotPose | None = None
        self._boundary_distance_m = 0.0
        self._boundary_last_progress_time = now
        self._coverage_goals: list[CoverageGoal] = []
        self._coverage_goal_index = 0

        self._goal_send_future = None
        self._goal_result_future = None
        self._goal_cancel_future = None
        self._active_goal_handle = None
        self._active_goal_source = ''
        self._active_goal_point: tuple[float, float] | None = None
        self._active_goal_pose: PoseStamped | None = None
        self._cancel_reason = ''

        self._behavior_send_future = None
        self._behavior_result_future = None
        self._behavior_cancel_future = None
        self._active_behavior_handle = None
        self._active_behavior_command: RecoveryCommand | None = None
        self._behavior_queue: list[RecoveryCommand] = []
        self._behavior_context = ''
        self._behavior_return_mode = MODE_FRONTIER

        self._tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._navigate_client = ActionClient(self, NavigateToPose, action_name)
        self._spin_client = ActionClient(self, Spin, self._spin_action_name)
        self._backup_client = ActionClient(self, BackUp, self._backup_action_name)
        self._drive_client = ActionClient(self, DriveOnHeading, self._drive_action_name)

        self._map_subscription = self.create_subscription(
            OccupancyGrid,
            self._map_topic,
            self._handle_map,
            10,
        )
        self._boundary_subscription = None
        if self._use_boundary_map:
            self._boundary_subscription = self.create_subscription(
                OccupancyGrid,
                self._boundary_map_topic,
                self._handle_boundary_map,
                10,
            )
        self._scan_subscription = self.create_subscription(
            LaserScan,
            self._scan_topic,
            self._handle_scan,
            10,
        )

        self._cmd_vel_publisher = self.create_publisher(Twist, self._cmd_vel_topic, 10)
        self._status_publisher = self.create_publisher(String, status_topic, 10)
        self._start_service = self.create_service(Trigger, start_service, self._handle_start)
        self._stop_service = self.create_service(Trigger, stop_service, self._handle_stop)
        self._resume_service = self.create_service(Trigger, resume_service, self._handle_resume)
        self._status_timer = self.create_timer(1.0, self._publish_status)
        self._planning_timer = self.create_timer(self._planning_period_sec, self._plan_once)

        self._publish_status()

    def _handle_map(self, msg: OccupancyGrid) -> None:
        self._map = msg

    def _handle_boundary_map(self, msg: OccupancyGrid) -> None:
        self._boundary_map = msg

    def _handle_scan(self, msg: LaserScan) -> None:
        self._latest_scan = msg
        self._latest_scan_time = self.get_clock().now()

    def _handle_start(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        if self._active:
            response.success = False
            response.message = f'Explorer is already active in mode {self._mode}.'
            return response

        self._reset_for_restart()
        self._active = True
        self._set_mode(MODE_BOOTSTRAP, 'Hybrid exploration start requested.')
        response.success = True
        response.message = self._state_message
        return response

    def _handle_stop(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        if not self._active and self._mode in {MODE_IDLE, MODE_STOPPED, MODE_COMPLETED}:
            response.success = False
            response.message = f'Explorer is not running. Current mode: {self._mode}.'
            return response

        self._active = False
        self._stop_boundary_follow()
        self._behavior_queue.clear()
        self._cancel_reason = 'stop'
        if self._active_goal_handle is not None:
            self._request_goal_cancel()
            self._set_mode(MODE_STOPPING, 'Stopping exploration after goal cancel.')
        elif self._active_behavior_handle is not None:
            self._request_behavior_cancel()
            self._set_mode(MODE_STOPPING, 'Stopping exploration after behavior cancel.')
        else:
            self._set_mode(MODE_STOPPED, 'Hybrid exploration stopped.')

        response.success = True
        response.message = self._state_message
        return response

    def _handle_resume(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        if self._active:
            response.success = False
            response.message = 'Explorer is already active.'
            return response

        self._active = True
        if self._mode in {MODE_STOPPED, MODE_IDLE, MODE_COMPLETED}:
            self._set_mode(MODE_BOOTSTRAP, 'Hybrid exploration resumed.')
        else:
            self._set_mode(MODE_FRONTIER, 'Hybrid exploration resumed.')
        response.success = True
        response.message = self._state_message
        return response

    def _reset_for_restart(self) -> None:
        now = self.get_clock().now()
        self._last_error_message = ''
        self._no_frontier_counter = 0
        self._bootstrap_passes = 0
        self._bootstrap_total_distance_m = 0.0
        self._bootstrap_drive_active = False
        self._bootstrap_drive_start_pose = None
        self._bootstrap_drive_started_at = now
        self._blacklisted_regions.clear()
        self._coverage_goals.clear()
        self._coverage_goal_index = 0
        self._boundary_distance_m = 0.0
        self._boundary_started_at = now
        self._boundary_last_progress_time = now
        self._boundary_last_pose = None
        self._last_progress_time = now
        self._last_progress_distance_remaining_m = None

    def _plan_once(self) -> None:
        self._prune_blacklist()
        if not self._active:
            return
        if self._fresh_scan() is None:
            self._set_mode(MODE_STARTING, f'Waiting for LiDAR scan on {self._scan_topic}.')
            return

        pose_frame = (
            self._bootstrap_pose_frame
            if self._mode in {MODE_BOOTSTRAP, MODE_BOUNDARY}
            else self._goal_frame
        )
        robot_pose = self._lookup_robot_pose(frame_id=pose_frame)
        if robot_pose is None:
            self._set_mode(
                MODE_STARTING,
                f'Waiting for transform {pose_frame} -> {self._robot_base_frame}.',
            )
            return
        if self._mode not in {MODE_BOOTSTRAP, MODE_BOUNDARY} and self._map is None:
            self._set_mode(MODE_STARTING, f'Waiting for map data on {self._map_topic}.')
            return
        if (
            self._mode not in {MODE_BOOTSTRAP, MODE_BOUNDARY}
            and self._use_boundary_map
            and self._boundary_map is None
        ):
            self._set_mode(MODE_STARTING, f'Waiting for boundary map on {self._boundary_map_topic}.')
            return

        if self._active_goal_handle is not None:
            self._check_progress_timeout()
            return
        if self._goal_send_future is not None or self._goal_cancel_future is not None:
            return
        if self._active_behavior_handle is not None or self._behavior_send_future is not None:
            return
        if self._behavior_cancel_future is not None:
            return
        if self._behavior_queue:
            self._start_next_behavior_command()
            return

        if self._mode == MODE_BOOTSTRAP:
            self._step_bootstrap(robot_pose)
        elif self._mode == MODE_BOUNDARY:
            self._step_boundary_follow(robot_pose)
        elif self._mode == MODE_RECOVERY:
            self._step_recovery(robot_pose)
        elif self._mode == MODE_COVERAGE:
            self._step_coverage_fill(robot_pose)
        else:
            self._step_frontier_explore(robot_pose)

    def _fresh_scan(self) -> LaserScan | None:
        if self._latest_scan is None:
            return None
        if self.get_clock().now() - self._latest_scan_time > self._scan_timeout:
            return None
        return self._latest_scan

    def _lookup_robot_pose(self, *, frame_id: str | None = None) -> RobotPose | None:
        target_frame = frame_id or self._goal_frame
        try:
            transform = self._tf_buffer.lookup_transform(
                target_frame,
                self._robot_base_frame,
                rclpy.time.Time(),
                timeout=Duration(seconds=0.08),
            )
        except TransformException:
            if self._last_robot_pose is None:
                return None
            if self.get_clock().now() - self._last_robot_pose_time > self._pose_reuse_timeout:
                return None
            return self._last_robot_pose

        q = transform.transform.rotation
        yaw = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z),
        )
        pose = RobotPose(
            x=float(transform.transform.translation.x),
            y=float(transform.transform.translation.y),
            yaw=float(yaw),
        )
        self._last_robot_pose = pose
        self._last_robot_pose_time = self.get_clock().now()
        return pose

    def _known_ratio(self) -> float:
        return compute_known_ratio(self._map)

    def _candidate_points(self, robot_pose: RobotPose) -> list[FrontierCandidate]:
        if self._map is None:
            return []
        return build_frontier_candidates(
            self._map,
            robot_pose=robot_pose,
            minimum_cluster_size=self._minimum_frontier_cluster_size,
            minimum_goal_distance_m=self._minimum_goal_distance_m,
            cluster_size_weight=self._cluster_size_weight,
            maximum_distance_score_m=self._maximum_distance_score_m,
            support_area_weight=self._support_area_weight,
            forward_preference_weight=self._forward_preference_weight,
            frontier_standoff_m=self._frontier_standoff_m,
            staging_search_radius_m=self._staging_search_radius_m,
            staging_support_radius_m=self._staging_support_radius_m,
            blacklisted_points=self._blacklisted_points(),
            blacklist_radius_m=self._blacklist_radius_m,
            boundary_map=self._boundary_map if self._use_boundary_map else None,
        )

    def _blacklisted_points(self) -> list[tuple[float, float]]:
        return [(region.x, region.y) for region in self._blacklisted_regions]

    def _step_bootstrap(self, robot_pose: RobotPose) -> None:
        scan = self._fresh_scan()
        if scan is None:
            return

        if self._bootstrap_drive_active:
            self._continue_bootstrap_drive(robot_pose, scan)
            return

        known_ratio = self._known_ratio()
        candidates = self._candidate_points(robot_pose)
        if bootstrap_ready_for_frontier(
            has_candidates=bool(candidates),
            known_ratio=known_ratio,
            known_ratio_threshold=self._bootstrap_known_ratio_for_frontier,
            bootstrap_passes=self._bootstrap_passes,
            minimum_passes=self._bootstrap_min_passes_before_frontier,
            bootstrap_total_distance_m=self._bootstrap_total_distance_m,
            minimum_total_distance_m=self._bootstrap_min_total_distance_m,
        ):
            self._stop_boundary_follow()
            self._set_mode(MODE_FRONTIER, 'Bootstrap finished; switching to frontier exploration.')
            return

        front_clearance = sector_clearance(
            scan,
            center_angle=0.0,
            window_angle=self._heading_window,
            clearance_percentile=self._heading_clearance_percentile,
        )
        left_clearance = sector_clearance(
            scan,
            center_angle=math.pi / 2.0,
            window_angle=0.22,
            clearance_percentile=0.35,
        )
        right_clearance = sector_clearance(
            scan,
            center_angle=-math.pi / 2.0,
            window_angle=0.22,
            clearance_percentile=0.35,
        )

        if front_clearance >= self._bootstrap_front_clearance_m and self._bootstrap_passes < self._bootstrap_max_passes:
            self._bootstrap_passes += 1
            self._bootstrap_drive_active = True
            self._bootstrap_drive_start_pose = robot_pose
            self._bootstrap_drive_started_at = self.get_clock().now()
            self._set_mode(
                MODE_BOOTSTRAP,
                'Bootstrap straight drive started to find a stable wall or frontier.',
            )
            return

        self._boundary_side = 'right' if right_clearance <= left_clearance else 'left'
        self._boundary_started_at = self.get_clock().now()
        self._boundary_last_progress_time = self.get_clock().now()
        self._boundary_last_pose = robot_pose
        self._boundary_distance_m = 0.0
        self._set_mode(
            MODE_BOUNDARY,
            f'Bootstrap complete; following the {self._boundary_side} boundary to stabilize the map.',
        )

    def _continue_bootstrap_drive(self, robot_pose: RobotPose, scan: LaserScan) -> None:
        front_clearance = sector_clearance(
            scan,
            center_angle=0.0,
            window_angle=self._heading_window,
            clearance_percentile=self._heading_clearance_percentile,
        )
        distance_traveled = 0.0
        if self._bootstrap_drive_start_pose is not None:
            distance_traveled = math.hypot(
                robot_pose.x - self._bootstrap_drive_start_pose.x,
                robot_pose.y - self._bootstrap_drive_start_pose.y,
            )

        elapsed = self.get_clock().now() - self._bootstrap_drive_started_at
        reached_distance = distance_traveled >= self._bootstrap_drive_distance_m
        front_blocked = front_clearance < self._bootstrap_front_clearance_m
        timed_out = elapsed > self._bootstrap_drive_timeout
        if reached_distance or front_blocked or timed_out:
            self._bootstrap_total_distance_m += distance_traveled
            self._stop_bootstrap_drive()
            reason = 'distance limit' if reached_distance else 'front obstacle' if front_blocked else 'timeout'
            self._set_mode(
                MODE_BOOTSTRAP,
                f'Bootstrap straight drive finished due to {reason}; re-evaluating mode.',
            )
            return

        twist = Twist()
        twist.linear.x = self._bootstrap_drive_speed_mps
        self._cmd_vel_publisher.publish(twist)
        self._state_message = (
            f'Bootstrap straight drive active: {distance_traveled:.2f}/'
            f'{self._bootstrap_drive_distance_m:.2f} m, front={front_clearance:.2f} m.'
        )
        self._publish_status()

    def _stop_bootstrap_drive(self) -> None:
        if not self._bootstrap_drive_active:
            return
        self._bootstrap_drive_active = False
        self._bootstrap_drive_start_pose = None
        self._cmd_vel_publisher.publish(Twist())

    def _step_boundary_follow(self, robot_pose: RobotPose) -> None:
        scan = self._fresh_scan()
        if scan is None:
            self._queue_recovery('Boundary follow lost LiDAR data.')
            return

        front_clearance = sector_clearance(
            scan,
            center_angle=0.0,
            window_angle=0.28,
            clearance_percentile=self._heading_clearance_percentile,
        )
        side_center = -math.pi / 2.0 if self._boundary_side == 'right' else math.pi / 2.0
        diagonal_center = -0.90 if self._boundary_side == 'right' else 0.90
        side_clearance = sector_clearance(
            scan,
            center_angle=side_center,
            window_angle=0.18,
            clearance_percentile=0.35,
        )
        diagonal_clearance = sector_clearance(
            scan,
            center_angle=diagonal_center,
            window_angle=0.18,
            clearance_percentile=0.30,
        )

        if self._boundary_last_pose is not None:
            delta = math.hypot(
                robot_pose.x - self._boundary_last_pose.x,
                robot_pose.y - self._boundary_last_pose.y,
            )
            self._boundary_distance_m += delta
            if delta >= self._boundary_follow_progress_distance_m:
                self._boundary_last_progress_time = self.get_clock().now()
        self._boundary_last_pose = robot_pose

        candidates = self._candidate_points(robot_pose)
        boundary_elapsed = self.get_clock().now() - self._boundary_started_at
        if (
            candidates
            and boundary_elapsed >= self._boundary_follow_min_duration
            and self._boundary_distance_m >= self._boundary_follow_min_distance_m
        ):
            self._stop_boundary_follow()
            self._set_mode(
                MODE_FRONTIER,
                'Boundary outline established; switching to frontier exploration.',
            )
            return

        if self.get_clock().now() - self._boundary_last_progress_time > self._boundary_follow_stuck_timeout:
            self._stop_boundary_follow()
            self._queue_recovery('Boundary follow stalled; switching to recovery escape.')
            return

        linear_x, angular_z = wall_follow_command(
            front_clearance=front_clearance,
            side_clearance=side_clearance,
            diagonal_clearance=diagonal_clearance,
            target_distance=self._boundary_follow_target_distance_m,
            front_stop_distance=self._boundary_follow_front_stop_m,
            wall_lost_distance=self._boundary_follow_wall_lost_m,
            linear_speed=self._boundary_follow_linear_speed_mps,
            max_angular_speed=self._boundary_follow_max_angular_speed_rps,
            side_gain=self._boundary_follow_side_gain,
            diagonal_gain=self._boundary_follow_diagonal_gain,
            follow_side=self._boundary_side,
        )
        twist = Twist()
        twist.linear.x = linear_x
        twist.angular.z = angular_z
        self._cmd_vel_publisher.publish(twist)
        self._state_message = (
            f'Boundary follow ({self._boundary_side}) front={front_clearance:.2f} '
            f'side={side_clearance:.2f} dist={self._boundary_distance_m:.2f} m.'
        )
        self._publish_status()

    def _stop_boundary_follow(self) -> None:
        self._stop_bootstrap_drive()
        self._cmd_vel_publisher.publish(Twist())

    def _step_frontier_explore(self, robot_pose: RobotPose) -> None:
        if not self._navigate_client.wait_for_server(timeout_sec=0.05):
            self._set_mode(MODE_STARTING, 'Waiting for NavigateToPose action server.')
            return

        candidates = self._candidate_points(robot_pose)
        if not candidates:
            self._no_frontier_counter += 1
            known_ratio = self._known_ratio()
            if self._enable_coverage_fill and known_ratio >= self._coverage_known_ratio_threshold:
                self._prepare_coverage_fill(robot_pose)
                return
            if self._no_frontier_counter >= self._no_frontier_confirmations:
                if known_ratio >= self._frontier_completion_known_ratio:
                    self._active = False
                    self._set_mode(MODE_COMPLETED, 'No remaining frontier candidates; mapping completed.')
                else:
                    self._set_mode(
                        MODE_BOOTSTRAP,
                        'No frontier candidates available; returning to bootstrap wall finding.',
                    )
            else:
                self._set_mode(
                    MODE_FRONTIER,
                    'No valid frontier candidates yet; waiting for more map updates.',
                )
            return

        self._no_frontier_counter = 0
        self._send_navigation_goal(candidates[0], source='frontier', robot_pose=robot_pose)

    def _prepare_coverage_fill(self, robot_pose: RobotPose) -> None:
        if not self._enable_coverage_fill or self._map is None:
            self._active = False
            self._set_mode(MODE_COMPLETED, 'Frontier exploration completed without coverage fill.')
            return

        goals = build_coverage_fill_goals(
            self._map,
            robot_pose=robot_pose,
            lane_spacing_m=self._coverage_lane_spacing_m,
            minimum_segment_length_m=self._coverage_min_segment_length_m,
            boundary_map=self._boundary_map if self._use_boundary_map else None,
        )
        if not goals:
            self._active = False
            self._set_mode(MODE_COMPLETED, 'No coverage fill lanes available; mapping completed.')
            return

        self._coverage_goals = goals
        self._coverage_goal_index = 0
        self._set_mode(
            MODE_COVERAGE,
            f'Frontiers exhausted; executing {len(goals)} structured coverage fill goals.',
        )

    def _step_coverage_fill(self, robot_pose: RobotPose) -> None:
        candidates = self._candidate_points(robot_pose)
        if candidates:
            self._set_mode(MODE_FRONTIER, 'Frontiers reappeared; resuming frontier exploration.')
            return
        if self._coverage_goal_index >= len(self._coverage_goals):
            self._active = False
            self._set_mode(MODE_COMPLETED, 'Coverage fill finished; mapping completed.')
            return
        if not self._navigate_client.wait_for_server(timeout_sec=0.05):
            self._set_mode(MODE_STARTING, 'Waiting for NavigateToPose action server.')
            return

        goal = self._coverage_goals[self._coverage_goal_index]
        self._send_navigation_goal(goal, source='coverage', robot_pose=robot_pose)

    def _step_recovery(self, robot_pose: RobotPose) -> None:
        del robot_pose
        self._start_next_behavior_command()

    def _send_navigation_goal(
        self,
        target: FrontierCandidate | CoverageGoal,
        *,
        source: str,
        robot_pose: RobotPose,
    ) -> None:
        if isinstance(target, FrontierCandidate):
            goal_x = target.world_x
            goal_y = target.world_y
            yaw = math.atan2(goal_y - robot_pose.y, goal_x - robot_pose.x)
            message = (
                f'Navigating to frontier goal ({goal_x:.2f}, {goal_y:.2f}) '
                f'size={target.size} score={target.score:.2f}.'
            )
        else:
            goal_x = target.world_x
            goal_y = target.world_y
            yaw = target.heading
            message = (
                f'Navigating to coverage fill goal {self._coverage_goal_index + 1}/'
                f'{len(self._coverage_goals)} at ({goal_x:.2f}, {goal_y:.2f}).'
            )

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.header.frame_id = self._goal_frame
        goal.pose.pose.position.x = goal_x
        goal.pose.pose.position.y = goal_y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

        self._active_goal_source = source
        self._active_goal_pose = goal.pose
        self._active_goal_point = (goal_x, goal_y)
        self._last_distance_remaining_m = None
        self._last_progress_distance_remaining_m = None
        self._last_progress_time = self.get_clock().now()

        self._goal_send_future = self._navigate_client.send_goal_async(
            goal,
            feedback_callback=self._handle_goal_feedback,
        )
        self._goal_send_future.add_done_callback(self._handle_goal_response)
        self._set_mode(
            MODE_FRONTIER if source == 'frontier' else MODE_COVERAGE,
            message,
        )

    def _handle_goal_feedback(self, feedback_msg: Any) -> None:
        distance_remaining = float(feedback_msg.feedback.distance_remaining)
        self._last_distance_remaining_m = distance_remaining
        if (
            self._last_progress_distance_remaining_m is None
            or self._last_progress_distance_remaining_m - distance_remaining
            >= self._progress_required_distance_m
        ):
            self._last_progress_distance_remaining_m = distance_remaining
            self._last_progress_time = self.get_clock().now()
        self._publish_status()

    def _handle_goal_response(self, future: Any) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._goal_send_future = None
            self._set_error(f'Failed to send navigation goal: {exc}')
            return

        self._goal_send_future = None
        if not goal_handle.accepted:
            self._blacklist_active_goal('NavigateToPose rejected the exploration goal.')
            self._queue_recovery('Goal was rejected by NavigateToPose.')
            return

        self._active_goal_handle = goal_handle
        self._goal_result_future = goal_handle.get_result_async()
        self._goal_result_future.add_done_callback(self._handle_goal_result)

    def _handle_goal_result(self, future: Any) -> None:
        self._active_goal_handle = None
        self._goal_result_future = None
        self._last_distance_remaining_m = None

        try:
            result = future.result()
        except Exception as exc:
            self._blacklist_active_goal(f'Failed to receive goal result: {exc}')
            self._queue_recovery('Goal result retrieval failed.')
            return

        status = result.status
        nav_result = result.result

        if status == GoalStatus.STATUS_SUCCEEDED:
            self._active_goal_point = None
            self._active_goal_pose = None
            if self._active_goal_source == 'coverage':
                self._coverage_goal_index += 1
                self._set_mode(MODE_COVERAGE, 'Coverage fill goal reached; selecting the next lane.')
            else:
                self._set_mode(MODE_FRONTIER, 'Frontier goal reached; selecting the next frontier.')
            self._active_goal_source = ''
            return

        if status == GoalStatus.STATUS_CANCELED:
            if self._cancel_reason == 'stop':
                self._active_goal_point = None
                self._active_goal_pose = None
                self._active_goal_source = ''
                self._cancel_reason = ''
                self._set_mode(MODE_STOPPED, 'Hybrid exploration stopped.')
                return
            self._blacklist_active_goal('Canceled the current exploration goal and selecting a new one.')
            self._queue_recovery('Goal was canceled before completion.')
            return

        error_msg = nav_result.error_msg if nav_result.error_msg else 'Exploration goal failed.'
        self._blacklist_active_goal(error_msg)
        self._queue_recovery(error_msg)

    def _check_progress_timeout(self) -> None:
        if self._active_goal_handle is None:
            return
        if self.get_clock().now() - self._last_progress_time <= self._progress_timeout:
            return
        self._cancel_reason = 'stalled'
        self._request_goal_cancel()
        self.get_logger().warning(
            f'Exploration goal stalled; canceling and blacklisting {self._describe_active_goal()}.'
        )

    def _request_goal_cancel(self) -> None:
        if self._active_goal_handle is None or self._goal_cancel_future is not None:
            return
        self._goal_cancel_future = self._active_goal_handle.cancel_goal_async()
        self._goal_cancel_future.add_done_callback(self._handle_goal_cancel_response)

    def _handle_goal_cancel_response(self, future: Any) -> None:
        try:
            cancel_response = future.result()
        except Exception as exc:
            self._goal_cancel_future = None
            self._set_error(f'Failed to cancel goal: {exc}')
            return

        self._goal_cancel_future = None
        if not cancel_response.goals_canceling and self._cancel_reason != 'stop':
            self._blacklist_active_goal('Cancel request was rejected; goal blacklisted for retry.')
            self._queue_recovery('Goal cancel request was rejected.')

    def _queue_recovery(self, reason: str) -> None:
        scan = self._fresh_scan()
        self._stop_boundary_follow()

        front_clearance = (
            sector_clearance(
                scan,
                center_angle=0.0,
                window_angle=self._heading_window,
                clearance_percentile=self._heading_clearance_percentile,
            )
            if scan is not None
            else 0.0
        )
        best_heading, best_clearance, _ = (
            choose_open_heading(
                scan,
                preferred_heading=0.0,
                heading_window=self._heading_window,
                forward_bias_weight=self._heading_forward_bias_weight,
                clearance_percentile=self._heading_clearance_percentile,
            )
            if scan is not None
            else (None, 0.0, float('-inf'))
        )

        commands: list[RecoveryCommand] = [
            RecoveryCommand(
                kind='backup',
                distance_or_yaw=self._recovery_backup_distance_m,
                speed=self._recovery_backup_speed_mps,
                time_allowance_sec=8.0,
                description='recovery backup',
            )
        ]
        if best_heading is not None:
            spin_angle = best_heading
            if best_clearance <= front_clearance + 0.20 and abs(spin_angle) < 2.2:
                spin_angle = math.copysign(self._recovery_default_spin_rad, spin_angle or 1.0)
        else:
            spin_angle = self._recovery_default_spin_rad

        commands.append(
            RecoveryCommand(
                kind='spin',
                distance_or_yaw=spin_angle,
                speed=0.0,
                time_allowance_sec=10.0,
                description='recovery spin to escape stuck loop',
            )
        )
        if best_clearance >= 0.8 or front_clearance >= 0.8:
            commands.append(
                RecoveryCommand(
                    kind='drive',
                    distance_or_yaw=self._recovery_drive_distance_m,
                    speed=self._recovery_drive_speed_mps,
                    time_allowance_sec=8.0,
                    description='recovery drive on heading',
                )
            )

        self._queue_behavior_commands(
            commands,
            context='recovery',
            return_mode=MODE_FRONTIER,
            message=reason,
        )

    def _queue_behavior_commands(
        self,
        commands: list[RecoveryCommand],
        *,
        context: str,
        return_mode: str,
        message: str,
    ) -> None:
        if not commands:
            return
        self._behavior_queue = list(commands)
        self._behavior_context = context
        self._behavior_return_mode = return_mode
        self._set_mode(
            MODE_RECOVERY if context == 'recovery' else self._mode,
            f'{message} Queued {len(commands)} {context} behavior command(s).',
        )

    def _start_next_behavior_command(self) -> None:
        if not self._behavior_queue or self._active_behavior_handle is not None:
            return
        if self._behavior_send_future is not None:
            return

        command = self._behavior_queue.pop(0)
        self._active_behavior_command = command
        if command.kind == 'spin':
            if not self._spin_client.wait_for_server(timeout_sec=0.05):
                self._behavior_queue.insert(0, command)
                self._set_mode(MODE_STARTING, f'Waiting for {self._spin_action_name} action server.')
                return
            goal = Spin.Goal()
            goal.target_yaw = float(command.distance_or_yaw)
            goal.time_allowance = Duration(seconds=float(command.time_allowance_sec)).to_msg()
            self._behavior_send_future = self._spin_client.send_goal_async(goal)
        elif command.kind == 'backup':
            if not self._backup_client.wait_for_server(timeout_sec=0.05):
                self._behavior_queue.insert(0, command)
                self._set_mode(MODE_STARTING, f'Waiting for {self._backup_action_name} action server.')
                return
            goal = BackUp.Goal()
            goal.target = Point(x=float(command.distance_or_yaw))
            goal.speed = float(command.speed)
            goal.time_allowance = Duration(seconds=float(command.time_allowance_sec)).to_msg()
            self._behavior_send_future = self._backup_client.send_goal_async(goal)
        else:
            if not self._drive_client.wait_for_server(timeout_sec=0.05):
                self._behavior_queue.insert(0, command)
                self._set_mode(MODE_STARTING, f'Waiting for {self._drive_action_name} action server.')
                return
            goal = DriveOnHeading.Goal()
            goal.target = Point(x=float(command.distance_or_yaw))
            goal.speed = float(command.speed)
            goal.time_allowance = Duration(seconds=float(command.time_allowance_sec)).to_msg()
            self._behavior_send_future = self._drive_client.send_goal_async(goal)

        self._behavior_send_future.add_done_callback(self._handle_behavior_goal_response)
        self._set_mode(
            MODE_RECOVERY if self._behavior_context == 'recovery' else self._mode,
            f'Executing {self._behavior_context} behavior: {command.description}.',
        )

    def _handle_behavior_goal_response(self, future: Any) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._behavior_send_future = None
            self._set_error(f'Failed to send behavior goal: {exc}')
            return

        self._behavior_send_future = None
        if not goal_handle.accepted:
            failed_command = self._active_behavior_command
            self._active_behavior_command = None
            self._behavior_queue.clear()
            if self._behavior_context == 'bootstrap':
                self._set_mode(MODE_BOUNDARY, 'Bootstrap drive was rejected; switching to boundary follow.')
            else:
                self._set_mode(MODE_FRONTIER, f'Behavior request rejected: {failed_command}.')
            return

        self._active_behavior_handle = goal_handle
        self._behavior_result_future = goal_handle.get_result_async()
        self._behavior_result_future.add_done_callback(self._handle_behavior_result)

    def _handle_behavior_result(self, future: Any) -> None:
        self._active_behavior_handle = None
        self._behavior_result_future = None
        command = self._active_behavior_command
        self._active_behavior_command = None

        try:
            result = future.result()
        except Exception as exc:
            self._behavior_queue.clear()
            self._set_error(f'Failed to receive behavior result: {exc}')
            return

        if result.status == GoalStatus.STATUS_CANCELED and self._cancel_reason == 'stop':
            self._cancel_reason = ''
            self._set_mode(MODE_STOPPED, 'Hybrid exploration stopped.')
            return

        if result.status != GoalStatus.STATUS_SUCCEEDED:
            self._behavior_queue.clear()
            if self._behavior_context == 'bootstrap':
                self._set_mode(
                    MODE_BOUNDARY,
                    f'Bootstrap behavior failed ({command.description if command else "unknown"}); '
                    'switching to boundary follow.',
                )
            else:
                self._set_mode(
                    MODE_FRONTIER,
                    f'Recovery behavior failed ({command.description if command else "unknown"}); '
                    'retrying frontier exploration.',
                )
            return

        if self._behavior_queue:
            self._start_next_behavior_command()
            return

        if self._behavior_context == 'recovery':
            self._set_mode(self._behavior_return_mode, 'Recovery sequence finished; resuming exploration.')
        elif self._behavior_context == 'bootstrap':
            self._set_mode(MODE_BOOTSTRAP, 'Bootstrap drive finished; re-evaluating exploration mode.')

    def _request_behavior_cancel(self) -> None:
        if self._active_behavior_handle is None or self._behavior_cancel_future is not None:
            return
        self._behavior_cancel_future = self._active_behavior_handle.cancel_goal_async()
        self._behavior_cancel_future.add_done_callback(self._handle_behavior_cancel_response)

    def _handle_behavior_cancel_response(self, future: Any) -> None:
        try:
            future.result()
        except Exception as exc:
            self._behavior_cancel_future = None
            self._set_error(f'Failed to cancel behavior action: {exc}')
            return
        self._behavior_cancel_future = None

    def _blacklist_active_goal(self, message: str) -> None:
        if self._active_goal_point is not None:
            self._blacklisted_regions.append(
                BlacklistRegion(
                    x=self._active_goal_point[0],
                    y=self._active_goal_point[1],
                    expires_at_ns=(self.get_clock().now() + self._blacklist_duration).nanoseconds,
                )
            )
        self._active_goal_point = None
        self._active_goal_pose = None
        self._active_goal_source = ''
        self._cancel_reason = ''
        self.get_logger().warning(message)
        self._publish_status()

    def _prune_blacklist(self) -> None:
        now_ns = self.get_clock().now().nanoseconds
        self._blacklisted_regions = [
            region for region in self._blacklisted_regions if region.expires_at_ns > now_ns
        ]

    def _describe_active_goal(self) -> str:
        if self._active_goal_point is None:
            return 'n/a'
        return f'({self._active_goal_point[0]:.2f}, {self._active_goal_point[1]:.2f})'

    def _set_mode(self, mode: str, message: str) -> None:
        if mode == self._mode and message == self._state_message:
            return
        self._mode = mode
        self._state_message = message
        self.get_logger().info(message)
        self._publish_status()

    def _set_error(self, message: str) -> None:
        self._last_error_message = message
        self._mode = MODE_ERROR
        self._state_message = message
        self.get_logger().error(message)
        self._publish_status()

    def _publish_status(self) -> None:
        payload = {
            'mode': self._mode,
            'message': self._state_message,
            'frame_id': self._goal_frame,
            'bootstrap_pose_frame': self._bootstrap_pose_frame,
            'map_topic': self._map_topic,
            'scan_topic': self._scan_topic,
            'use_boundary_map': self._use_boundary_map,
            'active_goal': self._active_goal_point,
            'active_goal_source': self._active_goal_source or None,
            'distance_remaining_m': self._last_distance_remaining_m,
            'known_ratio': round(self._known_ratio(), 4),
            'bootstrap_passes': self._bootstrap_passes,
            'bootstrap_total_distance_m': round(self._bootstrap_total_distance_m, 3),
            'boundary_side': self._boundary_side,
            'boundary_distance_m': round(self._boundary_distance_m, 3),
            'coverage_goal_index': self._coverage_goal_index,
            'coverage_goal_count': len(self._coverage_goals),
            'blacklisted_goal_count': len(self._blacklisted_regions),
            'active_behavior': (
                self._active_behavior_command.description if self._active_behavior_command else None
            ),
            'error': self._last_error_message or None,
        }
        self._status_publisher.publish(String(data=json.dumps(payload, sort_keys=True)))

    def destroy_node(self) -> bool:
        self._cmd_vel_publisher.publish(Twist())
        self._navigate_client.destroy()
        self._spin_client.destroy()
        self._backup_client.destroy()
        self._drive_client.destroy()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = FrontierExplorerNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
