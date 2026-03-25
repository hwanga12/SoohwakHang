"""Run a waypoint patrol with start, stop, resume, and optional hybrid handoff."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateThroughPoses, NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.timer import Timer
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .nav_goal_utils import build_latest_pose_stamped
from .patrol_config import (
    PatrolPlan,
    Pose2D,
    Waypoint,
    get_default_patrol_waypoints_path,
    load_patrol_plan,
)


def collect_batch_goal_end_index(
    waypoint_ids: tuple[str, ...],
    waypoints: dict[str, Waypoint],
    start_index: int,
    *,
    observe_on_waypoints: bool,
    inspect_dwell_sec: float,
    max_batch_path_length_m: float = 0.0,
) -> int:
    """Return the last consecutive waypoint index that can be sent as one batch goal."""
    if start_index >= len(waypoint_ids):
        return start_index

    def should_observe(waypoint: Waypoint) -> bool:
        return observe_on_waypoints and waypoint.observe_here and inspect_dwell_sec > 0.0

    current = waypoints[waypoint_ids[start_index]]
    if should_observe(current) or not current.batchable or not current.lane_id:
        return start_index

    end_index = start_index
    cumulative_path_length_m = 0.0
    previous_waypoint = current
    for index in range(start_index + 1, len(waypoint_ids)):
        waypoint = waypoints[waypoint_ids[index]]
        if (
            should_observe(waypoint)
            or not waypoint.batchable
            or waypoint.lane_id != current.lane_id
        ):
            break
        leg_length_m = math.hypot(
            waypoint.pose.x - previous_waypoint.pose.x,
            waypoint.pose.y - previous_waypoint.pose.y,
        )
        if (
            max_batch_path_length_m > 0.0
            and cumulative_path_length_m + leg_length_m > max_batch_path_length_m
        ):
            break
        cumulative_path_length_m += leg_length_m
        end_index = index
        previous_waypoint = waypoint
    return end_index


def build_intermediate_segment_poses(
    start_pose: Pose2D,
    end_pose: Pose2D,
    *,
    max_segment_length_m: float,
) -> tuple[Pose2D, ...]:
    """Split long lane travel into shorter synthetic goals."""
    if max_segment_length_m <= 0.0:
        return ()

    delta_x = end_pose.x - start_pose.x
    delta_y = end_pose.y - start_pose.y
    delta_z = end_pose.z - start_pose.z
    distance = math.hypot(delta_x, delta_y)
    if distance <= max_segment_length_m:
        return ()

    segment_count = int(math.ceil(distance / max_segment_length_m))
    travel_yaw = math.atan2(delta_y, delta_x) if distance > 1.0e-6 else end_pose.yaw
    return tuple(
        Pose2D(
            x=start_pose.x + (delta_x * index / segment_count),
            y=start_pose.y + (delta_y * index / segment_count),
            z=start_pose.z + (delta_z * index / segment_count),
            yaw=travel_yaw,
        )
        for index in range(1, segment_count)
    )


def resolve_effective_waypoint_pose(
    waypoint_ids: tuple[str, ...],
    waypoints: dict[str, Waypoint],
    waypoint_index: int,
    *,
    prefer_lane_heading_on_inspect_waypoints: bool,
) -> Pose2D:
    """Optionally keep inspect waypoints aligned with lane travel during mapping patrol."""
    waypoint = waypoints[waypoint_ids[waypoint_index]]
    if (
        not prefer_lane_heading_on_inspect_waypoints
        or waypoint_index <= 0
        or waypoint.purpose != 'inspect'
        or not waypoint.lane_id
    ):
        return waypoint.pose

    previous_waypoint = waypoints[waypoint_ids[waypoint_index - 1]]
    if previous_waypoint.lane_id != waypoint.lane_id:
        return waypoint.pose

    delta_x = waypoint.pose.x - previous_waypoint.pose.x
    delta_y = waypoint.pose.y - previous_waypoint.pose.y
    if math.hypot(delta_x, delta_y) <= 1.0e-6:
        return waypoint.pose

    return Pose2D(
        x=waypoint.pose.x,
        y=waypoint.pose.y,
        z=waypoint.pose.z,
        yaw=math.atan2(delta_y, delta_x),
    )


def is_pose_within_xy_tolerance(
    current_pose: Pose2D | None,
    target_pose: Pose2D,
    *,
    xy_tolerance_m: float,
) -> bool:
    """Return True when the current pose is already close enough to the target pose."""
    if current_pose is None or xy_tolerance_m <= 0.0:
        return False

    return math.hypot(
        target_pose.x - current_pose.x,
        target_pose.y - current_pose.y,
    ) <= xy_tolerance_m


def should_treat_soft_completed_navigation_as_success(
    current_pose: Pose2D | None,
    target_pose: Pose2D | None,
    *,
    goal_soft_completed: bool,
    xy_tolerance_m: float,
) -> bool:
    """Accept a soft-complete result only while the robot is still near the target."""
    if not goal_soft_completed or target_pose is None:
        return False

    return is_pose_within_xy_tolerance(
        current_pose,
        target_pose,
        xy_tolerance_m=xy_tolerance_m,
    )


class PatrolNode(Node):
    """Visit the configured waypoint list in order and expose patrol controls."""

    def __init__(self) -> None:
        super().__init__('patrol_node')

        self.declare_parameter(
            'patrol_waypoints_file',
            str(get_default_patrol_waypoints_path()),
        )
        self.declare_parameter('navigate_to_pose_action', 'navigate_to_pose')
        self.declare_parameter('navigate_through_poses_action', 'navigate_through_poses')
        self.declare_parameter('status_topic', 'patrol/status')
        self.declare_parameter('start_service', 'patrol/start')
        self.declare_parameter('stop_service', 'patrol/stop')
        self.declare_parameter('resume_service', 'patrol/resume')
        self.declare_parameter('observe_on_inspect_waypoints', True)
        self.declare_parameter('inspect_dwell_sec', 0.0)
        self.declare_parameter('nav_server_wait_sec', 5.0)
        self.declare_parameter('auto_start', False)
        self.declare_parameter('goal_reject_retry_sec', 0.0)
        self.declare_parameter('goal_reject_retry_limit', 0)
        self.declare_parameter('enable_batch_navigation', True)
        self.declare_parameter('max_batch_path_length_m', 0.0)
        self.declare_parameter('max_lane_segment_length_m', 24.0)
        self.declare_parameter('prefer_lane_heading_on_inspect_waypoints', False)
        self.declare_parameter('already_reached_xy_tolerance_m', 0.45)
        self.declare_parameter('robot_pose_topic', '/odometry/filtered')
        self.declare_parameter('completion_action', 'none')
        self.declare_parameter('completion_start_service', 'mapping_explorer/start')
        self.declare_parameter('completion_service_wait_sec', 2.0)

        self._plan = self._load_plan()
        self._waypoint_ids = self._plan.default_patrol_sequence
        self._nav_server_wait_sec = float(self.get_parameter('nav_server_wait_sec').value)
        self._goal_reject_retry_sec = float(self.get_parameter('goal_reject_retry_sec').value)
        self._goal_reject_retry_limit = int(self.get_parameter('goal_reject_retry_limit').value)
        self._observe_on_inspect_waypoints = bool(
            self.get_parameter('observe_on_inspect_waypoints').value
        )
        self._enable_batch_navigation = bool(
            self.get_parameter('enable_batch_navigation').value
        )
        self._max_batch_path_length_m = max(
            0.0,
            float(self.get_parameter('max_batch_path_length_m').value),
        )
        self._max_lane_segment_length_m = max(
            0.0,
            float(self.get_parameter('max_lane_segment_length_m').value),
        )
        self._prefer_lane_heading_on_inspect_waypoints = bool(
            self.get_parameter('prefer_lane_heading_on_inspect_waypoints').value
        )
        self._already_reached_xy_tolerance_m = max(
            0.0,
            float(self.get_parameter('already_reached_xy_tolerance_m').value),
        )
        configured_dwell_sec = float(self.get_parameter('inspect_dwell_sec').value)
        if configured_dwell_sec > 0.0:
            self._inspect_dwell_sec = configured_dwell_sec
        else:
            self._inspect_dwell_sec = self._plan.recommended_observation_dwell_sec

        navigate_to_pose_action = str(self.get_parameter('navigate_to_pose_action').value)
        navigate_through_poses_action = str(
            self.get_parameter('navigate_through_poses_action').value
        )
        status_topic = str(self.get_parameter('status_topic').value)
        start_service = str(self.get_parameter('start_service').value)
        stop_service = str(self.get_parameter('stop_service').value)
        resume_service = str(self.get_parameter('resume_service').value)
        robot_pose_topic = str(self.get_parameter('robot_pose_topic').value)
        self._completion_action = str(self.get_parameter('completion_action').value).strip()
        self._completion_start_service = str(
            self.get_parameter('completion_start_service').value
        ).strip()
        self._completion_service_wait_sec = float(
            self.get_parameter('completion_service_wait_sec').value
        )

        self._action_name = navigate_to_pose_action
        self._batch_action_name = navigate_through_poses_action
        self._navigate_client = ActionClient(self, NavigateToPose, navigate_to_pose_action)
        self._navigate_through_client = ActionClient(
            self,
            NavigateThroughPoses,
            navigate_through_poses_action,
        )
        self._status_publisher = self.create_publisher(String, status_topic, 10)
        self._odom_subscription = self.create_subscription(
            Odometry,
            robot_pose_topic,
            self._handle_odom,
            10,
        )
        self._start_service = self.create_service(Trigger, start_service, self._handle_start)
        self._stop_service = self.create_service(Trigger, stop_service, self._handle_stop)
        self._resume_service = self.create_service(Trigger, resume_service, self._handle_resume)
        self._status_timer = self.create_timer(1.0, self._publish_status)
        self._completion_client = None
        if self._completion_start_service:
            self._completion_client = self.create_client(Trigger, self._completion_start_service)

        self._state = 'idle'
        self._state_message = 'Patrol node is ready.'
        self._active_goal_handle = None
        self._goal_send_future = None
        self._goal_result_future = None
        self._cancel_future = None
        self._dwell_timer: Timer | None = None
        self._goal_retry_timer: Timer | None = None
        self._auto_start_timer: Timer | None = None
        self._completion_future = None
        self._completion_requested = False
        self._stop_requested = False
        self._current_waypoint_index: int | None = None
        self._next_waypoint_index = 0
        self._goal_reject_retry_count = 0
        self._last_distance_remaining_m: float | None = None
        self._last_error_message = ''
        self._latest_robot_pose: Pose2D | None = None
        self._active_navigation_kind = 'single'
        self._active_batch_end_index: int | None = None
        self._active_target_pose: Pose2D | None = None
        self._active_goal_soft_completed = False
        self._segment_goal_queue: list[PoseStamped] = []
        self._segment_total_goal_count = 0
        self._segment_target_waypoint_index: int | None = None

        self.get_logger().info(
            'Loaded patrol plan with '
            f'{len(self._plan.waypoints)} waypoints and '
            f'{len(self._waypoint_ids)} patrol steps from {self._plan_path}.'
        )
        self._publish_status()

        if bool(self.get_parameter('auto_start').value):
            self._auto_start_timer = self.create_timer(0.1, self._auto_start_once)

    def _load_plan(self) -> PatrolPlan:
        self._plan_path = Path(str(self.get_parameter('patrol_waypoints_file').value)).expanduser()
        if not self._plan_path.is_absolute():
            self._plan_path = get_default_patrol_waypoints_path().parent.parent / self._plan_path
        return load_patrol_plan(self._plan_path)

    def _auto_start_once(self) -> None:
        if self._state != 'idle':
            if self._auto_start_timer is not None:
                self._auto_start_timer.cancel()
                self.destroy_timer(self._auto_start_timer)
                self._auto_start_timer = None
            return

        if self._latest_robot_pose is None:
            return

        if self._auto_start_timer is not None:
            self._auto_start_timer.cancel()
            self.destroy_timer(self._auto_start_timer)
            self._auto_start_timer = None

        if self._start_patrol(reset_progress=True):
            self.get_logger().info('Auto-started patrol sequence.')

    def _handle_start(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request

        if self._state in {'starting', 'running', 'stopping', 'observing'}:
            response.success = False
            response.message = f'Patrol cannot start while state is {self._state}.'
            return response

        if self._start_patrol(reset_progress=True):
            response.success = True
            response.message = 'Patrol start requested from the first waypoint.'
        else:
            response.success = False
            response.message = self._state_message
        return response

    def _handle_stop(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request

        if self._state in {'idle', 'stopped', 'completed'}:
            response.success = False
            response.message = f'Patrol is not running. Current state: {self._state}.'
            return response

        if self._state == 'error':
            self._cancel_dwell_timer()
            self._set_state('stopped', 'Patrol stopped from the error state.')
            response.success = True
            response.message = self._state_message
            return response

        self._stop_requested = True

        if self._dwell_timer is not None:
            self._cancel_dwell_timer()
            self._set_state(
                'stopped',
                f'Patrol paused before waypoint {self._describe_waypoint(self._next_waypoint_index)}.',
            )
            response.success = True
            response.message = self._state_message
            return response

        if self._active_goal_handle is None:
            self._set_state('stopping', 'Patrol stop requested while navigation goal is starting.')
            response.success = True
            response.message = self._state_message
            return response

        self._set_state(
            'stopping',
            f'Patrol stop requested at {self._describe_active_target()}.',
        )
        self._request_goal_cancel()
        response.success = True
        response.message = self._state_message
        return response

    def _handle_resume(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        del request

        if self._state != 'stopped':
            response.success = False
            response.message = f'Patrol can only resume from the stopped state, not {self._state}.'
            return response

        if self._next_waypoint_index >= len(self._waypoint_ids):
            response.success = False
            response.message = 'Patrol sequence is already complete.'
            return response

        if self._start_patrol(reset_progress=False):
            response.success = True
            response.message = (
                'Patrol resume requested from waypoint '
                f'{self._describe_waypoint(self._next_waypoint_index)}.'
            )
        else:
            response.success = False
            response.message = self._state_message
        return response

    def _start_patrol(self, *, reset_progress: bool) -> bool:
        if reset_progress:
            self._next_waypoint_index = 0
            self._goal_reject_retry_count = 0
            self._last_error_message = ''
            self._completion_requested = False
            self._completion_future = None

        if self._next_waypoint_index >= len(self._waypoint_ids):
            self._set_state('completed', 'Patrol sequence is already complete.')
            return False

        if not self._navigate_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self._set_state(
                'error',
                f'NavigateToPose action server not available on {self._action_name}.',
            )
            return False

        self._cancel_dwell_timer()
        self._cancel_goal_retry_timer()
        self._stop_requested = False
        self._last_distance_remaining_m = None
        self._send_goal_for_index(self._next_waypoint_index)
        return True

    def _send_goal_for_index(self, waypoint_index: int) -> None:
        if self._is_waypoint_already_reached(waypoint_index):
            self._clear_segment_goal_sequence()
            self._set_state(
                'running',
                f'Skipping navigation because waypoint {self._describe_waypoint(waypoint_index)} is already within tolerance.',
            )
            self._handle_successful_waypoint(waypoint_index)
            return

        if self._prepare_segment_goal_sequence(waypoint_index):
            return

        batch_end_index = collect_batch_goal_end_index(
            self._waypoint_ids,
            self._plan.waypoints,
            waypoint_index,
            observe_on_waypoints=self._observe_on_inspect_waypoints,
            inspect_dwell_sec=self._inspect_dwell_sec,
            max_batch_path_length_m=self._max_batch_path_length_m,
        )
        if (
            self._enable_batch_navigation
            and batch_end_index > waypoint_index
            and self._navigate_through_client.wait_for_server(timeout_sec=0.25)
        ):
            self._send_batch_goal(waypoint_index, batch_end_index)
            return

        self._send_single_goal(waypoint_index)

    def _prepare_segment_goal_sequence(self, waypoint_index: int) -> bool:
        segment_goals = self._build_segment_goal_queue(waypoint_index)
        if not segment_goals:
            self._clear_segment_goal_sequence()
            return False

        self._segment_goal_queue = segment_goals
        self._segment_total_goal_count = len(segment_goals)
        self._segment_target_waypoint_index = waypoint_index
        self._dispatch_next_segment_goal()
        return True

    def _build_segment_goal_queue(self, waypoint_index: int) -> list[PoseStamped]:
        if waypoint_index <= 0 or self._max_lane_segment_length_m <= 0.0:
            return []

        previous_waypoint = self._waypoint_for_index(waypoint_index - 1)
        target_waypoint = self._waypoint_for_index(waypoint_index)
        if (
            not previous_waypoint.lane_id
            or previous_waypoint.lane_id != target_waypoint.lane_id
        ):
            return []

        intermediate_poses = build_intermediate_segment_poses(
            previous_waypoint.pose,
            target_waypoint.pose,
            max_segment_length_m=self._max_lane_segment_length_m,
        )
        if not intermediate_poses:
            return []

        goal_queue = [
            self._build_pose_stamped_from_pose(pose)
            for pose in intermediate_poses
        ]
        goal_queue.append(self._build_pose_stamped_for_index(waypoint_index))
        return goal_queue

    def _dispatch_next_segment_goal(self) -> None:
        if not self._segment_goal_queue or self._segment_target_waypoint_index is None:
            self._clear_segment_goal_sequence()
            return

        while self._segment_goal_queue and self._is_pose_already_reached(
            self._pose_2d_from_stamped(self._segment_goal_queue[0])
        ):
            self._segment_goal_queue.pop(0)

        if not self._segment_goal_queue:
            final_waypoint_index = self._segment_target_waypoint_index
            self._clear_segment_goal_sequence()
            self._handle_successful_waypoint(final_waypoint_index)
            return

        goal = NavigateToPose.Goal()
        goal.pose = self._segment_goal_queue[0]
        goal.behavior_tree = ''
        self._active_target_pose = self._pose_2d_from_stamped(goal.pose)
        self._active_goal_soft_completed = False

        step_index = self._segment_total_goal_count - len(self._segment_goal_queue) + 1
        waypoint_index = self._segment_target_waypoint_index

        self._active_navigation_kind = 'segment'
        self._active_batch_end_index = None
        self._current_waypoint_index = waypoint_index
        self._next_waypoint_index = waypoint_index
        self._goal_send_future = self._navigate_client.send_goal_async(
            goal,
            feedback_callback=self._handle_navigation_feedback,
        )
        self._goal_send_future.add_done_callback(
            lambda future, start=waypoint_index: self._handle_goal_response(
                future,
                start,
                start,
                'segment',
            )
        )
        self._set_state(
            'starting',
            'Starting segmented navigation '
            f'({step_index}/{self._segment_total_goal_count}) to waypoint '
            f'{self._describe_waypoint(waypoint_index)}.',
        )

    def _send_single_goal(self, waypoint_index: int) -> None:
        self._clear_segment_goal_sequence()
        waypoint = self._waypoint_for_index(waypoint_index)
        goal = NavigateToPose.Goal()
        goal.pose = self._build_pose_stamped_for_index(waypoint_index)
        goal.behavior_tree = ''
        self._active_target_pose = self._effective_waypoint_pose(waypoint_index)
        self._active_goal_soft_completed = False

        self._active_navigation_kind = 'single'
        self._active_batch_end_index = None
        self._current_waypoint_index = waypoint_index
        self._next_waypoint_index = waypoint_index
        self._goal_send_future = self._navigate_client.send_goal_async(
            goal,
            feedback_callback=self._handle_navigation_feedback,
        )
        self._goal_send_future.add_done_callback(
            lambda future, start=waypoint_index: self._handle_goal_response(
                future,
                start,
                start,
                'single',
            )
        )
        self._set_state(
            'starting',
            f'Starting navigation to waypoint {self._describe_waypoint(waypoint_index)}.',
        )

    def _send_batch_goal(self, start_index: int, end_index: int) -> None:
        self._clear_segment_goal_sequence()
        goal = NavigateThroughPoses.Goal()
        goal.poses = [
            self._build_pose_stamped_for_index(index)
            for index in range(start_index, end_index + 1)
        ]
        goal.behavior_tree = ''
        self._active_target_pose = None
        self._active_goal_soft_completed = False

        self._active_navigation_kind = 'batch'
        self._active_batch_end_index = end_index
        self._current_waypoint_index = start_index
        self._next_waypoint_index = start_index
        self._goal_send_future = self._navigate_through_client.send_goal_async(
            goal,
            feedback_callback=self._handle_navigation_feedback,
        )
        self._goal_send_future.add_done_callback(
            lambda future, start=start_index, end=end_index: self._handle_goal_response(
                future,
                start,
                end,
                'batch',
            )
        )
        self._set_state(
            'starting',
            'Starting batched navigation through '
            f'{end_index - start_index + 1} waypoints ending at {self._describe_waypoint(end_index)}.',
        )

    def _handle_goal_response(
        self,
        future: Any,
        start_index: int,
        end_index: int,
        kind: str,
    ) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._set_error(
                f'Failed to send navigation goal for {self._describe_goal_target(start_index, end_index, kind)}: {exc}'
            )
            return

        self._goal_send_future = None

        if not goal_handle.accepted:
            if kind == 'segment':
                self._clear_segment_goal_sequence()
            if self._stop_requested:
                self._stop_requested = False
                self._set_state('stopped', 'Patrol stop completed before goal acceptance.')
                return
            if self._schedule_goal_reject_retry(start_index, end_index, kind):
                return
            self._set_error(
                'Navigation goal was rejected for '
                f'{self._describe_goal_target(start_index, end_index, kind)}.'
            )
            return

        self._active_goal_handle = goal_handle
        self._goal_reject_retry_count = 0
        self._goal_result_future = goal_handle.get_result_async()
        self._goal_result_future.add_done_callback(
            lambda result_future, start=start_index, end=end_index, goal_kind=kind: self._handle_navigation_result(
                result_future,
                start,
                end,
                goal_kind,
            )
        )

        if self._stop_requested:
            self._set_state(
                'stopping',
                f'Patrol stop requested at {self._describe_goal_target(start_index, end_index, kind)}.',
            )
            self._request_goal_cancel()
            return

        if kind == 'batch':
            self._set_state(
                'running',
                f'Navigating through batched waypoints ending at {self._describe_waypoint(end_index)}.',
            )
        else:
            self._set_state('running', f'Navigating to waypoint {self._describe_waypoint(end_index)}.')

    def _handle_navigation_feedback(self, feedback_msg: Any) -> None:
        self._last_distance_remaining_m = float(feedback_msg.feedback.distance_remaining)
        if (
            not self._active_goal_soft_completed
            and self._active_navigation_kind in {'single', 'segment'}
            and self._active_target_pose is not None
            and self._is_pose_already_reached(self._active_target_pose)
        ):
            self._active_goal_soft_completed = True
        self._publish_status()

    def _handle_odom(self, message: Odometry) -> None:
        orientation = message.pose.pose.orientation
        self._latest_robot_pose = Pose2D(
            x=float(message.pose.pose.position.x),
            y=float(message.pose.pose.position.y),
            z=float(message.pose.pose.position.z),
            yaw=math.atan2(
                2.0 * orientation.w * orientation.z,
                1.0 - 2.0 * orientation.z * orientation.z,
            ),
        )

    def _handle_navigation_result(
        self,
        future: Any,
        start_index: int,
        end_index: int,
        kind: str,
    ) -> None:
        self._active_goal_handle = None
        self._goal_result_future = None
        self._last_distance_remaining_m = None
        self._active_batch_end_index = None
        active_target_pose = self._active_target_pose
        active_goal_soft_completed = self._active_goal_soft_completed
        self._active_target_pose = None
        self._active_goal_soft_completed = False

        try:
            result = future.result()
        except Exception as exc:
            self._set_error(
                'Failed to receive navigation result for '
                f'{self._describe_goal_target(start_index, end_index, kind)}: {exc}'
            )
            return

        status = result.status
        nav_result = result.result

        if status == GoalStatus.STATUS_SUCCEEDED:
            if kind == 'segment':
                self._handle_successful_segment_goal()
                return
            self._handle_successful_waypoint(end_index)
            return

        if kind in {'single', 'segment'} and should_treat_soft_completed_navigation_as_success(
            self._latest_robot_pose,
            active_target_pose,
            goal_soft_completed=active_goal_soft_completed,
            xy_tolerance_m=self._already_reached_xy_tolerance_m,
        ):
            self.get_logger().warning(
                'Treating near-complete navigation as success for '
                f'{self._describe_goal_target(start_index, end_index, kind)}.'
            )
            if kind == 'segment':
                self._handle_successful_segment_goal()
            else:
                self._handle_successful_waypoint(end_index)
            return

        if status == GoalStatus.STATUS_CANCELED:
            if kind == 'segment':
                self._clear_segment_goal_sequence()
            self._stop_requested = False
            self._set_state(
                'stopped',
                f'Patrol paused at {self._describe_goal_target(start_index, end_index, kind)}.',
            )
            return

        if kind == 'segment':
            self._clear_segment_goal_sequence()
        error_msg = nav_result.error_msg if nav_result.error_msg else 'Navigation goal failed.'
        if nav_result.error_code != NavigateToPose.Result.NONE:
            error_msg = f'{error_msg} (error_code={nav_result.error_code})'
        self._set_error(
            f'Navigation to {self._describe_goal_target(start_index, end_index, kind)} failed: {error_msg}'
        )

    def _handle_successful_segment_goal(self) -> None:
        if self._segment_target_waypoint_index is None or not self._segment_goal_queue:
            self._clear_segment_goal_sequence()
            self._set_error('Segmented patrol goal state became inconsistent.')
            return

        self._segment_goal_queue.pop(0)
        final_waypoint_index = self._segment_target_waypoint_index
        if self._segment_goal_queue:
            self._dispatch_next_segment_goal()
            return

        self._clear_segment_goal_sequence()
        self._handle_successful_waypoint(final_waypoint_index)

    def _handle_successful_waypoint(self, waypoint_index: int) -> None:
        self._current_waypoint_index = None
        self._next_waypoint_index = waypoint_index + 1

        if self._next_waypoint_index >= len(self._waypoint_ids):
            self._set_state('completed', 'Patrol completed the configured waypoint sequence.')
            self._request_completion_action()
            return

        waypoint = self._waypoint_for_index(waypoint_index)
        if self._should_observe(waypoint):
            self._set_state(
                'observing',
                f'Observing at waypoint {waypoint.display_name} for {self._inspect_dwell_sec:.1f}s.',
            )
            self._schedule_dwell()
            return

        self._send_goal_for_index(self._next_waypoint_index)

    def _schedule_dwell(self) -> None:
        self._cancel_dwell_timer()
        if self._inspect_dwell_sec <= 0.0:
            self._send_goal_for_index(self._next_waypoint_index)
            return

        self._dwell_timer = self.create_timer(self._inspect_dwell_sec, self._finish_dwell)

    def _finish_dwell(self) -> None:
        self._cancel_dwell_timer()
        if self._state != 'observing':
            return
        self._send_goal_for_index(self._next_waypoint_index)

    def _request_goal_cancel(self) -> None:
        if self._active_goal_handle is None or self._cancel_future is not None:
            return
        self._cancel_future = self._active_goal_handle.cancel_goal_async()
        self._cancel_future.add_done_callback(self._handle_cancel_response)

    def _handle_cancel_response(self, future: Any) -> None:
        try:
            cancel_response = future.result()
        except Exception as exc:
            self._set_error(f'Failed to cancel navigation goal: {exc}')
            return

        self._cancel_future = None

        if not cancel_response.goals_canceling:
            self._stop_requested = False
            self._set_error('Navigation goal rejected the patrol stop request.')

    def _cancel_dwell_timer(self) -> None:
        if self._dwell_timer is None:
            return
        self._dwell_timer.cancel()
        self.destroy_timer(self._dwell_timer)
        self._dwell_timer = None

    def _schedule_goal_reject_retry(self, start_index: int, end_index: int, kind: str) -> bool:
        if self._goal_reject_retry_sec <= 0.0:
            return False
        if self._goal_reject_retry_count >= self._goal_reject_retry_limit:
            return False

        self._goal_reject_retry_count += 1
        self._cancel_goal_retry_timer()
        retry_message = (
            'Navigation goal was rejected for '
            f'{self._describe_goal_target(start_index, end_index, kind)}; retrying in '
            f'{self._goal_reject_retry_sec:.1f}s '
            f'({self._goal_reject_retry_count}/{self._goal_reject_retry_limit}).'
        )
        self._state = 'starting'
        self._state_message = retry_message
        self.get_logger().warning(retry_message)
        self._publish_status()
        self._goal_retry_timer = self.create_timer(
            self._goal_reject_retry_sec,
            lambda idx=start_index: self._retry_goal_after_rejection(idx),
        )
        return True

    def _retry_goal_after_rejection(self, waypoint_index: int) -> None:
        self._cancel_goal_retry_timer()
        if self._state == 'error':
            return
        self._send_goal_for_index(waypoint_index)

    def _cancel_goal_retry_timer(self) -> None:
        if self._goal_retry_timer is None:
            return
        self._goal_retry_timer.cancel()
        self.destroy_timer(self._goal_retry_timer)
        self._goal_retry_timer = None

    def _request_completion_action(self) -> None:
        if self._completion_requested or self._completion_action == 'none':
            return
        if self._completion_action != 'start_frontier_explorer':
            self.get_logger().warning(
                f'Unsupported completion_action {self._completion_action!r}; skipping.'
            )
            return
        if self._completion_client is None:
            self.get_logger().warning('Completion action requested but no service client is configured.')
            return
        if not self._completion_client.wait_for_service(timeout_sec=self._completion_service_wait_sec):
            self.get_logger().warning(
                f'Completion service {self._completion_start_service} is not available.'
            )
            return

        self._completion_requested = True
        self._completion_future = self._completion_client.call_async(Trigger.Request())
        self._completion_future.add_done_callback(self._handle_completion_action_response)
        self._set_state(
            'completed',
            'Patrol completed; requesting frontier hole-fill exploration.',
        )

    def _handle_completion_action_response(self, future: Any) -> None:
        try:
            response = future.result()
        except Exception as exc:
            self.get_logger().warning(
                f'Failed to trigger completion action {self._completion_action!r}: {exc}'
            )
            self._set_state(
                'completed',
                'Patrol completed, but frontier hole-fill request failed.',
            )
            return

        if response.success:
            self._set_state(
                'completed',
                'Patrol completed and frontier hole-fill was requested successfully.',
            )
            return

        self.get_logger().warning(
            'Completion action responded unsuccessfully: '
            f'{response.message or self._completion_action}'
        )
        self._set_state(
            'completed',
            'Patrol completed, but frontier hole-fill was not accepted.',
        )

    def _should_observe(self, waypoint: Waypoint) -> bool:
        return (
            self._observe_on_inspect_waypoints
            and waypoint.observe_here
            and self._inspect_dwell_sec > 0.0
        )

    def _build_pose_stamped(self, waypoint: Waypoint) -> PoseStamped:
        return self._build_pose_stamped_from_pose(waypoint.pose)

    def _build_pose_stamped_for_index(self, waypoint_index: int) -> PoseStamped:
        return self._build_pose_stamped_from_pose(self._effective_waypoint_pose(waypoint_index))

    def _build_pose_stamped_from_pose(self, pose_2d: Pose2D) -> PoseStamped:
        return build_latest_pose_stamped(
            frame_id=self._plan.frame_id,
            x_value=pose_2d.x,
            y_value=pose_2d.y,
            z_value=pose_2d.z,
            yaw_value=pose_2d.yaw,
        )

    def _pose_2d_from_stamped(self, pose: PoseStamped) -> Pose2D:
        orientation = pose.pose.orientation
        return Pose2D(
            x=float(pose.pose.position.x),
            y=float(pose.pose.position.y),
            z=float(pose.pose.position.z),
            yaw=math.atan2(
                2.0 * orientation.w * orientation.z,
                1.0 - 2.0 * orientation.z * orientation.z,
            ),
        )

    def _is_pose_already_reached(self, target_pose: Pose2D) -> bool:
        return is_pose_within_xy_tolerance(
            self._latest_robot_pose,
            target_pose,
            xy_tolerance_m=self._already_reached_xy_tolerance_m,
        )

    def _is_waypoint_already_reached(self, waypoint_index: int) -> bool:
        return self._is_pose_already_reached(self._effective_waypoint_pose(waypoint_index))

    def _effective_waypoint_pose(self, waypoint_index: int) -> Pose2D:
        return resolve_effective_waypoint_pose(
            self._waypoint_ids,
            self._plan.waypoints,
            waypoint_index,
            prefer_lane_heading_on_inspect_waypoints=self._prefer_lane_heading_on_inspect_waypoints,
        )

    def _waypoint_for_index(self, waypoint_index: int) -> Waypoint:
        return self._plan.waypoints[self._waypoint_ids[waypoint_index]]

    def _describe_waypoint(self, waypoint_index: int | None) -> str:
        if waypoint_index is None or waypoint_index >= len(self._waypoint_ids):
            return 'n/a'
        waypoint_id = self._waypoint_ids[waypoint_index]
        waypoint = self._plan.waypoints[waypoint_id]
        return f'{waypoint.display_name} ({waypoint_id})'

    def _describe_goal_target(self, start_index: int, end_index: int, kind: str) -> str:
        if kind == 'batch' and end_index > start_index:
            return (
                f'batched route from {self._describe_waypoint(start_index)} '
                f'to {self._describe_waypoint(end_index)}'
            )
        if kind == 'segment':
            return f'segmented route toward {self._describe_waypoint(end_index)}'
        return f'waypoint {self._describe_waypoint(end_index)}'

    def _describe_active_target(self) -> str:
        if self._current_waypoint_index is None:
            return 'n/a'
        return self._describe_goal_target(
            self._current_waypoint_index,
            self._active_batch_end_index
            if self._active_navigation_kind == 'batch' and self._active_batch_end_index is not None
            else self._current_waypoint_index,
            self._active_navigation_kind,
        )

    def _set_state(self, state: str, message: str) -> None:
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
        current_waypoint_id = None
        if self._current_waypoint_index is not None and self._current_waypoint_index < len(
            self._waypoint_ids
        ):
            current_waypoint_id = self._waypoint_ids[self._current_waypoint_index]

        next_waypoint_id = None
        if self._next_waypoint_index < len(self._waypoint_ids):
            next_waypoint_id = self._waypoint_ids[self._next_waypoint_index]

        active_batch_end_waypoint_id = None
        if self._active_batch_end_index is not None and self._active_batch_end_index < len(
            self._waypoint_ids
        ):
            active_batch_end_waypoint_id = self._waypoint_ids[self._active_batch_end_index]

        payload = {
            'state': self._state,
            'message': self._state_message,
            'zone_id': self._plan.zone_id,
            'frame_id': self._plan.frame_id,
            'current_waypoint_index': self._current_waypoint_index,
            'current_waypoint_id': current_waypoint_id,
            'next_waypoint_index': self._next_waypoint_index,
            'next_waypoint_id': next_waypoint_id,
            'total_waypoints': len(self._waypoint_ids),
            'distance_remaining_m': self._last_distance_remaining_m,
            'active_navigation_kind': self._active_navigation_kind,
            'active_batch_end_index': self._active_batch_end_index,
            'active_batch_end_waypoint_id': active_batch_end_waypoint_id,
            'segment_target_waypoint_id': (
                self._waypoint_ids[self._segment_target_waypoint_index]
                if self._segment_target_waypoint_index is not None
                and self._segment_target_waypoint_index < len(self._waypoint_ids)
                else None
            ),
            'segment_steps_remaining': len(self._segment_goal_queue),
            'segment_total_steps': self._segment_total_goal_count,
            'completion_action': self._completion_action,
            'error': self._last_error_message or None,
        }
        self._status_publisher.publish(String(data=json.dumps(payload, sort_keys=True)))

    def _clear_segment_goal_sequence(self) -> None:
        self._segment_goal_queue = []
        self._segment_total_goal_count = 0
        self._segment_target_waypoint_index = None

    def destroy_node(self) -> bool:
        self._cancel_dwell_timer()
        self._cancel_goal_retry_timer()
        self._navigate_client.destroy()
        self._navigate_through_client.destroy()
        if self._completion_client is not None:
            self.destroy_client(self._completion_client)
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = PatrolNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
