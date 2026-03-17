"""Run a waypoint patrol with start, stop, and resume controls."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.timer import Timer
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .patrol_config import PatrolPlan, Waypoint, get_default_patrol_waypoints_path, load_patrol_plan


class PatrolNode(Node):
    """Visit the configured waypoint list in order and expose patrol controls."""

    def __init__(self) -> None:
        super().__init__('patrol_node')

        self.declare_parameter(
            'patrol_waypoints_file',
            str(get_default_patrol_waypoints_path()),
        )
        self.declare_parameter('navigate_to_pose_action', 'navigate_to_pose')
        self.declare_parameter('status_topic', 'patrol/status')
        self.declare_parameter('start_service', 'patrol/start')
        self.declare_parameter('stop_service', 'patrol/stop')
        self.declare_parameter('resume_service', 'patrol/resume')
        self.declare_parameter('observe_on_inspect_waypoints', True)
        self.declare_parameter('inspect_dwell_sec', 0.0)
        self.declare_parameter('nav_server_wait_sec', 5.0)
        self.declare_parameter('auto_start', False)

        self._plan = self._load_plan()
        self._waypoint_ids = self._plan.default_patrol_sequence
        self._nav_server_wait_sec = float(self.get_parameter('nav_server_wait_sec').value)
        self._observe_on_inspect_waypoints = bool(
            self.get_parameter('observe_on_inspect_waypoints').value
        )
        configured_dwell_sec = float(self.get_parameter('inspect_dwell_sec').value)
        if configured_dwell_sec > 0.0:
            self._inspect_dwell_sec = configured_dwell_sec
        else:
            self._inspect_dwell_sec = self._plan.recommended_observation_dwell_sec

        action_name = str(self.get_parameter('navigate_to_pose_action').value)
        self._action_name = action_name
        status_topic = str(self.get_parameter('status_topic').value)
        start_service = str(self.get_parameter('start_service').value)
        stop_service = str(self.get_parameter('stop_service').value)
        resume_service = str(self.get_parameter('resume_service').value)

        self._navigate_client = ActionClient(self, NavigateToPose, action_name)
        self._status_publisher = self.create_publisher(String, status_topic, 10)
        self._start_service = self.create_service(Trigger, start_service, self._handle_start)
        self._stop_service = self.create_service(Trigger, stop_service, self._handle_stop)
        self._resume_service = self.create_service(Trigger, resume_service, self._handle_resume)
        self._status_timer = self.create_timer(1.0, self._publish_status)

        self._state = 'idle'
        self._state_message = 'Patrol node is ready.'
        self._active_goal_handle = None
        self._goal_send_future = None
        self._goal_result_future = None
        self._cancel_future = None
        self._dwell_timer: Timer | None = None
        self._auto_start_timer: Timer | None = None
        self._stop_requested = False
        self._current_waypoint_index: int | None = None
        self._next_waypoint_index = 0
        self._last_distance_remaining_m: float | None = None
        self._last_error_message = ''

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
        if self._auto_start_timer is not None:
            self._auto_start_timer.cancel()
            self.destroy_timer(self._auto_start_timer)
            self._auto_start_timer = None

        if self._state != 'idle':
            return

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
            f'Patrol stop requested at waypoint {self._describe_waypoint(self._current_waypoint_index)}.',
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
            self._last_error_message = ''

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
        self._stop_requested = False
        self._last_distance_remaining_m = None
        self._send_goal_for_index(self._next_waypoint_index)
        return True

    def _send_goal_for_index(self, waypoint_index: int) -> None:
        waypoint = self._waypoint_for_index(waypoint_index)
        goal = NavigateToPose.Goal()
        goal.pose = self._build_pose_stamped(waypoint)
        goal.behavior_tree = ''

        self._current_waypoint_index = waypoint_index
        self._next_waypoint_index = waypoint_index
        self._goal_send_future = self._navigate_client.send_goal_async(
            goal,
            feedback_callback=self._handle_navigation_feedback,
        )
        self._goal_send_future.add_done_callback(
            lambda future, idx=waypoint_index: self._handle_goal_response(future, idx)
        )
        self._set_state('starting', f'Starting navigation to waypoint {self._describe_waypoint(waypoint_index)}.')

    def _handle_goal_response(self, future: Any, waypoint_index: int) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._set_error(
                f'Failed to send NavigateToPose goal for {self._describe_waypoint(waypoint_index)}: {exc}'
            )
            return

        self._goal_send_future = None

        if not goal_handle.accepted:
            if self._stop_requested:
                self._stop_requested = False
                self._set_state('stopped', 'Patrol stop completed before goal acceptance.')
                return
            self._set_error(
                f'NavigateToPose rejected waypoint {self._describe_waypoint(waypoint_index)}.'
            )
            return

        self._active_goal_handle = goal_handle
        self._goal_result_future = goal_handle.get_result_async()
        self._goal_result_future.add_done_callback(
            lambda result_future, idx=waypoint_index: self._handle_navigation_result(
                result_future,
                idx,
            )
        )

        if self._stop_requested:
            self._set_state(
                'stopping',
                f'Patrol stop requested at waypoint {self._describe_waypoint(waypoint_index)}.',
            )
            self._request_goal_cancel()
            return

        self._set_state('running', f'Navigating to waypoint {self._describe_waypoint(waypoint_index)}.')

    def _handle_navigation_feedback(self, feedback_msg: Any) -> None:
        self._last_distance_remaining_m = float(feedback_msg.feedback.distance_remaining)
        self._publish_status()

    def _handle_navigation_result(self, future: Any, waypoint_index: int) -> None:
        self._active_goal_handle = None
        self._goal_result_future = None
        self._last_distance_remaining_m = None

        try:
            result = future.result()
        except Exception as exc:
            self._set_error(
                f'Failed to receive NavigateToPose result for {self._describe_waypoint(waypoint_index)}: {exc}'
            )
            return

        status = result.status
        nav_result = result.result

        if status == GoalStatus.STATUS_SUCCEEDED:
            self._handle_successful_waypoint(waypoint_index)
            return

        if status == GoalStatus.STATUS_CANCELED:
            self._stop_requested = False
            self._set_state(
                'stopped',
                f'Patrol paused at waypoint {self._describe_waypoint(waypoint_index)}.',
            )
            return

        error_msg = nav_result.error_msg if nav_result.error_msg else 'Navigation goal failed.'
        if nav_result.error_code != NavigateToPose.Result.NONE:
            error_msg = f'{error_msg} (error_code={nav_result.error_code})'
        self._set_error(
            f'Navigation to waypoint {self._describe_waypoint(waypoint_index)} failed: {error_msg}'
        )

    def _handle_successful_waypoint(self, waypoint_index: int) -> None:
        self._current_waypoint_index = None
        self._next_waypoint_index = waypoint_index + 1

        if self._next_waypoint_index >= len(self._waypoint_ids):
            self._set_state('completed', 'Patrol completed the configured waypoint sequence.')
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
            self._set_error(f'Failed to cancel NavigateToPose goal: {exc}')
            return

        self._cancel_future = None

        if not cancel_response.goals_canceling:
            self._stop_requested = False
            self._set_error('NavigateToPose goal rejected the patrol stop request.')

    def _cancel_dwell_timer(self) -> None:
        if self._dwell_timer is None:
            return
        self._dwell_timer.cancel()
        self.destroy_timer(self._dwell_timer)
        self._dwell_timer = None

    def _should_observe(self, waypoint: Waypoint) -> bool:
        return (
            self._observe_on_inspect_waypoints
            and waypoint.purpose == 'inspect'
            and self._inspect_dwell_sec > 0.0
        )

    def _build_pose_stamped(self, waypoint: Waypoint) -> PoseStamped:
        pose = PoseStamped()
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.header.frame_id = self._plan.frame_id
        pose.pose.position.x = waypoint.pose.x
        pose.pose.position.y = waypoint.pose.y
        pose.pose.position.z = waypoint.pose.z
        pose.pose.orientation.z = math.sin(waypoint.pose.yaw / 2.0)
        pose.pose.orientation.w = math.cos(waypoint.pose.yaw / 2.0)
        return pose

    def _waypoint_for_index(self, waypoint_index: int) -> Waypoint:
        return self._plan.waypoints[self._waypoint_ids[waypoint_index]]

    def _describe_waypoint(self, waypoint_index: int | None) -> str:
        if waypoint_index is None:
            return 'n/a'
        waypoint_id = self._waypoint_ids[waypoint_index]
        waypoint = self._plan.waypoints[waypoint_id]
        return f'{waypoint.display_name} ({waypoint_id})'

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
            'error': self._last_error_message or None,
        }
        self._status_publisher.publish(String(data=json.dumps(payload, sort_keys=True)))

    def destroy_node(self) -> bool:
        self._cancel_dwell_timer()
        self._navigate_client.destroy()
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
