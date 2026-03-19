"""Frontier-based autonomous exploration for SLAM mapping sessions."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
from typing import Any

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
import rclpy
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformException, TransformListener


UNKNOWN = -1
FREE_THRESHOLD = 20
OCCUPIED_THRESHOLD = 50


@dataclass(frozen=True)
class FrontierCandidate:
    map_x: int
    map_y: int
    world_x: float
    world_y: float
    size: int
    distance_m: float
    score: float


def map_index(width: int, x: int, y: int) -> int:
    return y * width + x


def is_free(value: int) -> bool:
    return 0 <= value <= FREE_THRESHOLD


def is_unknown(value: int) -> bool:
    return value == UNKNOWN


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


def representative_cell(cluster: list[tuple[int, int]]) -> tuple[int, int]:
    centroid_x = sum(cell[0] for cell in cluster) / len(cluster)
    centroid_y = sum(cell[1] for cell in cluster) / len(cluster)
    return min(
        cluster,
        key=lambda cell: (cell[0] - centroid_x) ** 2 + (cell[1] - centroid_y) ** 2,
    )


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


def build_frontier_candidates(
    map_msg: OccupancyGrid,
    *,
    robot_x: float,
    robot_y: float,
    minimum_cluster_size: int,
    minimum_goal_distance_m: float,
    cluster_size_weight: float,
    maximum_distance_score_m: float,
    blacklisted_points: list[tuple[float, float]],
    blacklist_radius_m: float,
    boundary_map: OccupancyGrid | None = None,
) -> list[FrontierCandidate]:
    candidates: list[FrontierCandidate] = []
    for cluster in frontier_clusters(map_msg, minimum_cluster_size):
        rep_x, rep_y = max(
            cluster,
            key=lambda cell: (
                map_to_world(map_msg, cell[0], cell[1])[0] - robot_x
            ) ** 2
            + (
                map_to_world(map_msg, cell[0], cell[1])[1] - robot_y
            ) ** 2,
        )
        world_x, world_y = map_to_world(map_msg, rep_x, rep_y)
        if not boundary_allows(boundary_map, world_x, world_y):
            continue
        if is_blacklisted(world_x, world_y, blacklisted_points, blacklist_radius_m):
            continue
        distance_m = math.hypot(world_x - robot_x, world_y - robot_y)
        if distance_m < minimum_goal_distance_m:
            continue

        cluster_span_m = len(cluster) * float(map_msg.info.resolution)
        score = min(distance_m, maximum_distance_score_m) + cluster_size_weight * cluster_span_m
        candidates.append(
            FrontierCandidate(
                map_x=rep_x,
                map_y=rep_y,
                world_x=world_x,
                world_y=world_y,
                size=len(cluster),
                distance_m=distance_m,
                score=score,
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (candidate.score, candidate.size, candidate.distance_m),
        reverse=True,
    )


class FrontierExplorerNode(Node):
    """Select frontier goals from the live SLAM map and feed them to Nav2."""

    def __init__(self) -> None:
        super().__init__('frontier_explorer')

        self.declare_parameter('map_topic', '/map')
        self.declare_parameter('boundary_map_topic', '/exploration_boundary_map')
        self.declare_parameter('use_boundary_map', False)
        self.declare_parameter('goal_frame', 'map')
        self.declare_parameter('robot_base_frame', 'base_link')
        self.declare_parameter('navigate_to_pose_action', 'navigate_to_pose')
        self.declare_parameter('status_topic', 'mapping_explorer/status')
        self.declare_parameter('start_service', 'mapping_explorer/start')
        self.declare_parameter('stop_service', 'mapping_explorer/stop')
        self.declare_parameter('resume_service', 'mapping_explorer/resume')
        self.declare_parameter('auto_start', True)
        self.declare_parameter('planning_period_sec', 2.0)
        self.declare_parameter('minimum_frontier_cluster_size', 12)
        self.declare_parameter('minimum_goal_distance_m', 1.5)
        self.declare_parameter('cluster_size_weight', 2.5)
        self.declare_parameter('maximum_distance_score_m', 8.0)
        self.declare_parameter('blacklist_radius_m', 1.5)
        self.declare_parameter('progress_timeout_sec', 20.0)
        self.declare_parameter('progress_required_distance_m', 0.5)
        self.declare_parameter('no_frontier_confirmations', 4)

        self._map_topic = str(self.get_parameter('map_topic').value)
        self._boundary_map_topic = str(self.get_parameter('boundary_map_topic').value)
        self._use_boundary_map = bool(self.get_parameter('use_boundary_map').value)
        self._goal_frame = str(self.get_parameter('goal_frame').value)
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
        self._blacklist_radius_m = float(self.get_parameter('blacklist_radius_m').value)
        self._progress_timeout = Duration(
            seconds=float(self.get_parameter('progress_timeout_sec').value)
        )
        self._progress_required_distance_m = float(
            self.get_parameter('progress_required_distance_m').value
        )
        self._no_frontier_confirmations = int(
            self.get_parameter('no_frontier_confirmations').value
        )

        action_name = str(self.get_parameter('navigate_to_pose_action').value)
        status_topic = str(self.get_parameter('status_topic').value)
        start_service = str(self.get_parameter('start_service').value)
        stop_service = str(self.get_parameter('stop_service').value)
        resume_service = str(self.get_parameter('resume_service').value)

        self._map: OccupancyGrid | None = None
        self._boundary_map: OccupancyGrid | None = None
        self._active = bool(self.get_parameter('auto_start').value)
        self._state = 'starting' if self._active else 'idle'
        self._state_message = (
            'Frontier exploration auto-started.' if self._active else 'Frontier explorer is idle.'
        )
        self._last_error_message = ''
        self._last_distance_remaining_m: float | None = None
        self._goal_send_future = None
        self._goal_result_future = None
        self._cancel_future = None
        self._active_goal_handle = None
        self._active_goal_pose: PoseStamped | None = None
        self._active_goal_point: tuple[float, float] | None = None
        self._cancel_reason = ''
        self._no_frontier_counter = 0
        self._blacklisted_points: list[tuple[float, float]] = []
        self._last_progress_time = self.get_clock().now()
        self._last_progress_distance_remaining_m: float | None = None

        self._tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self._tf_listener = TransformListener(self._tf_buffer, self)
        self._navigate_client = ActionClient(self, NavigateToPose, action_name)

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

    def _handle_start(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        if self._active:
            response.success = False
            response.message = f'Explorer is already active in state {self._state}.'
            return response

        self._active = True
        self._no_frontier_counter = 0
        self._last_error_message = ''
        self._set_state('starting', 'Frontier exploration start requested.')
        response.success = True
        response.message = self._state_message
        return response

    def _handle_stop(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request
        if not self._active and self._state in {'idle', 'stopped', 'completed'}:
            response.success = False
            response.message = f'Explorer is not running. Current state: {self._state}.'
            return response

        self._active = False
        if self._active_goal_handle is not None:
            self._cancel_reason = 'stop'
            self._request_goal_cancel()
            self._set_state('stopping', 'Stopping frontier exploration after current goal cancel.')
        else:
            self._set_state('stopped', 'Frontier exploration stopped.')

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
        self._no_frontier_counter = 0
        self._set_state('starting', 'Frontier exploration resumed.')
        response.success = True
        response.message = self._state_message
        return response

    def _plan_once(self) -> None:
        if self._active_goal_handle is not None:
            self._check_progress_timeout()
            return
        if self._goal_send_future is not None or self._cancel_future is not None:
            return
        if not self._active:
            return
        if self._map is None:
            self._set_state('starting', f'Waiting for map data on {self._map_topic}.')
            return
        if self._use_boundary_map and self._boundary_map is None:
            self._set_state(
                'starting',
                f'Waiting for boundary map data on {self._boundary_map_topic}.',
            )
            return
        if not self._navigate_client.wait_for_server(timeout_sec=0.1):
            self._set_state('starting', 'Waiting for NavigateToPose action server.')
            return

        robot_pose = self._lookup_robot_pose()
        if robot_pose is None:
            self._set_state(
                'starting',
                f'Waiting for transform {self._goal_frame} -> {self._robot_base_frame}.',
            )
            return

        robot_x, robot_y = robot_pose
        candidates = build_frontier_candidates(
            self._map,
            robot_x=robot_x,
            robot_y=robot_y,
            minimum_cluster_size=self._minimum_frontier_cluster_size,
            minimum_goal_distance_m=self._minimum_goal_distance_m,
            cluster_size_weight=self._cluster_size_weight,
            maximum_distance_score_m=self._maximum_distance_score_m,
            blacklisted_points=self._blacklisted_points,
            blacklist_radius_m=self._blacklist_radius_m,
            boundary_map=self._boundary_map if self._use_boundary_map else None,
        )

        if not candidates:
            self._no_frontier_counter += 1
            if self._no_frontier_counter >= self._no_frontier_confirmations:
                self._active = False
                self._set_state('completed', 'No remaining frontier candidates; exploration completed.')
            else:
                self._set_state(
                    'starting',
                    'No valid frontier candidates yet; waiting for more map updates.',
                )
            return

        self._no_frontier_counter = 0
        self._send_goal(candidates[0], robot_x=robot_x, robot_y=robot_y)

    def _lookup_robot_pose(self) -> tuple[float, float] | None:
        try:
            transform = self._tf_buffer.lookup_transform(
                self._goal_frame,
                self._robot_base_frame,
                rclpy.time.Time(),
                timeout=Duration(seconds=0.1),
            )
        except TransformException:
            return None
        return (
            float(transform.transform.translation.x),
            float(transform.transform.translation.y),
        )

    def _send_goal(self, candidate: FrontierCandidate, *, robot_x: float, robot_y: float) -> None:
        yaw = math.atan2(candidate.world_y - robot_y, candidate.world_x - robot_x)
        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.header.frame_id = self._goal_frame
        goal.pose.pose.position.x = candidate.world_x
        goal.pose.pose.position.y = candidate.world_y
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

        self._active_goal_pose = goal.pose
        self._active_goal_point = (candidate.world_x, candidate.world_y)
        self._last_distance_remaining_m = None
        self._last_progress_distance_remaining_m = None
        self._last_progress_time = self.get_clock().now()

        self._goal_send_future = self._navigate_client.send_goal_async(
            goal,
            feedback_callback=self._handle_feedback,
        )
        self._goal_send_future.add_done_callback(self._handle_goal_response)
        self._set_state(
            'starting',
            'Navigating to frontier goal '
            f'({candidate.world_x:.2f}, {candidate.world_y:.2f}) '
            f'size={candidate.size} score={candidate.score:.2f}.',
        )

    def _handle_goal_response(self, future: Any) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._goal_send_future = None
            self._set_error(f'Failed to send frontier goal: {exc}')
            return

        self._goal_send_future = None
        if not goal_handle.accepted:
            self._blacklist_active_goal('NavigateToPose rejected the frontier goal.')
            return

        self._active_goal_handle = goal_handle
        self._goal_result_future = goal_handle.get_result_async()
        self._goal_result_future.add_done_callback(self._handle_goal_result)
        self._set_state('exploring', f'Exploring toward frontier goal {self._describe_active_goal()}.')

    def _handle_feedback(self, feedback_msg: Any) -> None:
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

    def _handle_goal_result(self, future: Any) -> None:
        self._active_goal_handle = None
        self._goal_result_future = None
        self._last_distance_remaining_m = None

        try:
            result = future.result()
        except Exception as exc:
            self._blacklist_active_goal(f'Failed to receive frontier goal result: {exc}')
            return

        status = result.status
        nav_result = result.result
        self._active_goal_pose = None

        if status == GoalStatus.STATUS_SUCCEEDED:
            self._active_goal_point = None
            self._set_state('exploring', 'Frontier goal reached; selecting the next frontier.')
            return

        if status == GoalStatus.STATUS_CANCELED:
            if self._cancel_reason == 'stop':
                self._active_goal_point = None
                self._cancel_reason = ''
                self._set_state('stopped', 'Frontier exploration stopped.')
                return
            self._blacklist_active_goal('Canceled the current frontier goal and selecting a new one.')
            return

        error_msg = nav_result.error_msg if nav_result.error_msg else 'Frontier goal failed.'
        self._blacklist_active_goal(error_msg)

    def _check_progress_timeout(self) -> None:
        if self._active_goal_handle is None:
            return
        if self.get_clock().now() - self._last_progress_time <= self._progress_timeout:
            return
        self._cancel_reason = 'stalled'
        self._request_goal_cancel()
        self.get_logger().warning(
            'Frontier goal stalled; canceling and blacklisting '
            f'{self._describe_active_goal()}.'
        )

    def _request_goal_cancel(self) -> None:
        if self._active_goal_handle is None or self._cancel_future is not None:
            return
        self._cancel_future = self._active_goal_handle.cancel_goal_async()
        self._cancel_future.add_done_callback(self._handle_cancel_response)

    def _handle_cancel_response(self, future: Any) -> None:
        try:
            cancel_response = future.result()
        except Exception as exc:
            self._cancel_future = None
            self._set_error(f'Failed to cancel frontier goal: {exc}')
            return

        self._cancel_future = None
        if not cancel_response.goals_canceling and self._cancel_reason != 'stop':
            self._blacklist_active_goal('Cancel request was rejected; goal blacklisted for retry.')

    def _blacklist_active_goal(self, message: str) -> None:
        if self._active_goal_point is not None:
            self._blacklisted_points.append(self._active_goal_point)
        self._active_goal_point = None
        self._active_goal_pose = None
        self._cancel_reason = ''
        self._state = 'exploring'
        self._state_message = message
        self.get_logger().warning(message)
        self._publish_status()

    def _describe_active_goal(self) -> str:
        if self._active_goal_point is None:
            return 'n/a'
        return f'({self._active_goal_point[0]:.2f}, {self._active_goal_point[1]:.2f})'

    def _set_state(self, state: str, message: str) -> None:
        if state == self._state and message == self._state_message:
            return
        self._state = state
        self._state_message = message
        self.get_logger().info(message)
        self._publish_status()

    def _set_error(self, message: str) -> None:
        self._last_error_message = message
        self._state = 'error'
        self._state_message = message
        self.get_logger().error(message)
        self._publish_status()

    def _publish_status(self) -> None:
        payload = {
            'state': self._state,
            'message': self._state_message,
            'frame_id': self._goal_frame,
            'map_topic': self._map_topic,
            'use_boundary_map': self._use_boundary_map,
            'active_goal': self._active_goal_point,
            'distance_remaining_m': self._last_distance_remaining_m,
            'blacklisted_goal_count': len(self._blacklisted_points),
            'error': self._last_error_message or None,
        }
        self._status_publisher.publish(String(data=json.dumps(payload, sort_keys=True)))

    def destroy_node(self) -> bool:
        self._navigate_client.destroy()
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
