"""Pause patrol, approach a harvest target, and return home or back to patrol."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from action_msgs.msg import GoalStatus
from agribot_interfaces.msg import CropStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.timer import Timer
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .harvest_routing import (
    CropCatalog,
    HarvestRoutePlan,
    compute_harvest_route,
    get_default_crop_instances_path,
    load_crop_catalog,
)
from .nav_goal_utils import build_latest_pose_stamped
from .patrol_config import Pose2D, PatrolPlan, get_default_patrol_waypoints_path, load_patrol_plan


def _normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


class HarvestRouteNode(Node):
    """Coordinate harvest approach and return motions around the patrol node."""

    def __init__(self) -> None:
        super().__init__('harvest_route_node')

        self.declare_parameter('patrol_waypoints_file', str(get_default_patrol_waypoints_path()))
        self.declare_parameter('crop_instances_file', str(get_default_crop_instances_path()))
        self.declare_parameter('navigate_to_pose_action', 'navigate_to_pose')
        self.declare_parameter('crop_status_topic', 'crop_status')
        self.declare_parameter('harvest_request_topic', 'harvest/request')
        self.declare_parameter('patrol_status_topic', 'patrol/status')
        self.declare_parameter('status_topic', 'harvest_route/status')
        self.declare_parameter('patrol_stop_service', 'patrol/stop')
        self.declare_parameter('patrol_resume_service', 'patrol/resume')
        self.declare_parameter('nav_server_wait_sec', 5.0)
        self.declare_parameter('patrol_service_wait_sec', 1.0)
        self.declare_parameter('patrol_pause_timeout_sec', 8.0)
        self.declare_parameter('alignment_settle_sec', 0.75)
        self.declare_parameter('harvest_dwell_sec', 2.0)
        self.declare_parameter('return_mode_override', '')
        self.declare_parameter('auto_resume_patrol', True)
        self.declare_parameter('ignore_duplicate_targets', True)

        self._plan = self._load_patrol_plan()
        self._catalog = self._load_crop_catalog()
        self._nav_server_wait_sec = float(self.get_parameter('nav_server_wait_sec').value)
        self._patrol_service_wait_sec = float(self.get_parameter('patrol_service_wait_sec').value)
        self._patrol_pause_timeout_sec = float(self.get_parameter('patrol_pause_timeout_sec').value)
        self._alignment_settle_sec = float(self.get_parameter('alignment_settle_sec').value)
        self._harvest_dwell_sec = float(self.get_parameter('harvest_dwell_sec').value)
        self._return_mode_override = str(self.get_parameter('return_mode_override').value).strip()
        self._auto_resume_patrol = bool(self.get_parameter('auto_resume_patrol').value)
        self._ignore_duplicate_targets = bool(self.get_parameter('ignore_duplicate_targets').value)
        self._action_name = str(self.get_parameter('navigate_to_pose_action').value)

        crop_status_topic = str(self.get_parameter('crop_status_topic').value)
        harvest_request_topic = str(self.get_parameter('harvest_request_topic').value)
        patrol_status_topic = str(self.get_parameter('patrol_status_topic').value)
        status_topic = str(self.get_parameter('status_topic').value)
        patrol_stop_service = str(self.get_parameter('patrol_stop_service').value)
        patrol_resume_service = str(self.get_parameter('patrol_resume_service').value)

        self._navigate_client = ActionClient(self, NavigateToPose, self._action_name)
        self._patrol_stop_client = self.create_client(Trigger, patrol_stop_service)
        self._patrol_resume_client = self.create_client(Trigger, patrol_resume_service)
        self._crop_status_sub = self.create_subscription(
            CropStatus,
            crop_status_topic,
            self._handle_crop_status,
            10,
        )
        self._harvest_request_sub = self.create_subscription(
            String,
            harvest_request_topic,
            self._handle_harvest_request,
            10,
        )
        self._patrol_status_sub = self.create_subscription(
            String,
            patrol_status_topic,
            self._handle_patrol_status,
            10,
        )
        self._status_pub = self.create_publisher(String, status_topic, 10)
        self._status_timer = self.create_timer(1.0, self._on_status_timer)

        self._sequence_state = 'idle'
        self._sequence_message = 'Harvest route node is ready.'
        self._active_plan: HarvestRoutePlan | None = None
        self._active_goal_handle = None
        self._goal_send_future = None
        self._goal_result_future = None
        self._alignment_timer: Timer | None = None
        self._harvest_timer: Timer | None = None
        self._current_navigation_phase: str | None = None
        self._current_return_waypoint_id: str | None = None
        self._used_return_fallback = False
        self._resume_patrol_after_return = False
        self._completed_tomato_ids: set[str] = set()
        self._last_patrol_status: dict[str, Any] = {}
        self._last_distance_remaining_m: float | None = None
        self._last_error_message = ''
        self._patrol_pause_deadline_ns: int | None = None

        self.get_logger().info(
            'Loaded harvest routing metadata with '
            f'{len(self._catalog.tomatoes)} tomatoes from {self._crop_catalog_path}.'
        )
        self._publish_status()

    def _load_patrol_plan(self) -> PatrolPlan:
        self._patrol_plan_path = Path(
            str(self.get_parameter('patrol_waypoints_file').value)
        ).expanduser()
        if not self._patrol_plan_path.is_absolute():
            self._patrol_plan_path = get_default_patrol_waypoints_path().parent.parent / self._patrol_plan_path
        return load_patrol_plan(self._patrol_plan_path)

    def _load_crop_catalog(self) -> CropCatalog:
        self._crop_catalog_path = Path(
            str(self.get_parameter('crop_instances_file').value)
        ).expanduser()
        if not self._crop_catalog_path.is_absolute():
            self._crop_catalog_path = get_default_crop_instances_path().parent.parent / self._crop_catalog_path
        return load_crop_catalog(self._crop_catalog_path)

    def _handle_crop_status(self, msg: CropStatus) -> None:
        if not msg.ready_to_harvest:
            return

        tomato_id = msg.tomato_id.strip()
        if not tomato_id and msg.crop_type == 'tomato_fruit':
            tomato_id = msg.crop_id.strip()
        if not tomato_id:
            return

        self._begin_harvest_sequence(tomato_id, trigger='crop_status')

    def _handle_harvest_request(self, msg: String) -> None:
        tomato_id = msg.data.strip()
        if not tomato_id:
            return
        self._begin_harvest_sequence(tomato_id, trigger='manual_request')

    def _handle_patrol_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError as exc:
            self.get_logger().warning(f'Ignoring invalid patrol status payload: {exc}')
            return

        if not isinstance(payload, dict):
            self.get_logger().warning('Ignoring patrol status payload that is not a JSON object.')
            return

        self._last_patrol_status = payload
        if self._sequence_state == 'waiting_for_patrol_pause' and self._patrol_is_quiescent():
            self._patrol_pause_deadline_ns = None
            self._start_approach_navigation()

    def _begin_harvest_sequence(self, tomato_id: str, *, trigger: str) -> None:
        if self._sequence_state not in {'idle', 'completed'}:
            self.get_logger().warning(
                f'Ignoring harvest target {tomato_id} because sequence_state={self._sequence_state}.'
            )
            return

        if self._ignore_duplicate_targets and tomato_id in self._completed_tomato_ids:
            self.get_logger().info(f'Ignoring duplicate harvest target that already completed: {tomato_id}')
            return

        preferred_return_waypoint_id = self._preferred_return_waypoint_id()
        return_mode = self._return_mode_override or None
        try:
            self._active_plan = compute_harvest_route(
                self._plan,
                self._catalog,
                tomato_id,
                return_mode=return_mode,
                preferred_return_waypoint_id=preferred_return_waypoint_id,
            )
        except ValueError as exc:
            self._set_error(f'Failed to plan harvest route for {tomato_id}: {exc}')
            return

        self._used_return_fallback = False
        self._resume_patrol_after_return = False
        self._last_error_message = ''
        self.get_logger().info(
            f'Harvest route planned for {tomato_id} via {self._active_plan.inspect_waypoint_id} '
            f'(trigger={trigger}).'
        )

        if not self._navigate_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            self._set_error(
                f'NavigateToPose action server not available on {self._action_name}.'
            )
            return

        if self._patrol_is_active():
            self._request_patrol_stop()
            return

        self._start_approach_navigation()

    def _preferred_return_waypoint_id(self) -> str | None:
        current_waypoint_id = self._last_patrol_status.get('current_waypoint_id')
        if isinstance(current_waypoint_id, str) and current_waypoint_id in self._plan.waypoints:
            return current_waypoint_id
        return None

    def _patrol_is_active(self) -> bool:
        state = str(self._last_patrol_status.get('state', '')).strip()
        return state in {'starting', 'running', 'observing', 'stopping'}

    def _patrol_is_quiescent(self) -> bool:
        state = str(self._last_patrol_status.get('state', '')).strip()
        return state in {'', 'idle', 'stopped', 'completed', 'error'}

    def _request_patrol_stop(self) -> None:
        if not self._patrol_stop_client.wait_for_service(timeout_sec=self._patrol_service_wait_sec):
            self._set_error('Patrol stop service is unavailable while patrol is active.')
            return

        future = self._patrol_stop_client.call_async(Trigger.Request())
        future.add_done_callback(self._handle_patrol_stop_response)
        self._set_state(
            'waiting_for_patrol_pause',
            f'Waiting for patrol pause before approaching {self._active_plan.tomato_id}.',
        )
        self._patrol_pause_deadline_ns = (
            self.get_clock().now().nanoseconds
            + int(self._patrol_pause_timeout_sec * 1_000_000_000)
        )

    def _handle_patrol_stop_response(self, future: Any) -> None:
        try:
            response = future.result()
        except Exception as exc:
            self._set_error(f'Failed to call patrol stop service: {exc}')
            return

        if not response.success and not self._patrol_is_quiescent():
            self._set_error(f'Patrol stop request failed: {response.message}')
            return

        if self._active_plan is None:
            return

        self._resume_patrol_after_return = (
            self._active_plan.return_mode == 'resume_patrol' and self._auto_resume_patrol
        )
        if self._patrol_is_quiescent():
            self._patrol_pause_deadline_ns = None
            self._start_approach_navigation()

    def _start_approach_navigation(self) -> None:
        if self._active_plan is None:
            self._set_error('Cannot start approach navigation without an active harvest plan.')
            return

        self._start_navigation(
            self._active_plan.approach_pose,
            phase='approaching',
            message=(
                f'Approaching {self._active_plan.tomato_id} from '
                f'{self._active_plan.inspect_waypoint_name}.'
            ),
        )

    def _start_alignment_navigation(self) -> None:
        if self._active_plan is None:
            self._set_error('Cannot start harvest alignment without an active harvest plan.')
            return

        self._start_navigation(
            self._active_plan.align_pose,
            phase='aligning',
            message=(
                f'Aligning harvest posture for {self._active_plan.tomato_id} '
                f'near {self._active_plan.inspect_waypoint_name}.'
            ),
        )

    def _start_return_navigation(self, *, use_fallback: bool) -> None:
        if self._active_plan is None:
            self._set_error('Cannot start return navigation without an active harvest plan.')
            return

        waypoint_id = (
            self._active_plan.fallback_return_waypoint_id
            if use_fallback
            else self._active_plan.return_waypoint_id
        )
        self._used_return_fallback = use_fallback
        self._current_return_waypoint_id = waypoint_id
        fallback_note = ' using fallback return target' if use_fallback else ''
        self._start_navigation(
            self._plan.waypoints[waypoint_id].pose,
            phase='returning',
            message=(
                f'Returning from harvest toward {waypoint_id}{fallback_note}.'
            ),
        )

    def _start_navigation(self, pose: Pose2D, *, phase: str, message: str) -> None:
        goal = NavigateToPose.Goal()
        goal.pose = self._build_pose_stamped(pose)
        goal.behavior_tree = ''

        self._current_navigation_phase = phase
        self._goal_send_future = self._navigate_client.send_goal_async(
            goal,
            feedback_callback=self._handle_navigation_feedback,
        )
        self._goal_send_future.add_done_callback(
            lambda future, nav_phase=phase: self._handle_goal_response(future, nav_phase)
        )
        self._set_state(phase, message)

    def _handle_goal_response(self, future: Any, phase: str) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._set_error(f'Failed to send {phase} goal: {exc}')
            return

        self._goal_send_future = None

        if not goal_handle.accepted:
            self._set_error(f'NavigateToPose rejected the {phase} goal.')
            return

        self._active_goal_handle = goal_handle
        self._goal_result_future = goal_handle.get_result_async()
        self._goal_result_future.add_done_callback(
            lambda result_future, nav_phase=phase: self._handle_navigation_result(
                result_future,
                nav_phase,
            )
        )

    def _handle_navigation_feedback(self, feedback_msg: Any) -> None:
        self._last_distance_remaining_m = float(feedback_msg.feedback.distance_remaining)
        self._publish_status()

    def _handle_navigation_result(self, future: Any, phase: str) -> None:
        self._active_goal_handle = None
        self._goal_result_future = None
        self._last_distance_remaining_m = None
        self._current_navigation_phase = None

        try:
            result = future.result()
        except Exception as exc:
            self._set_error(f'Failed to receive {phase} result: {exc}')
            return

        status = result.status
        nav_result = result.result

        if status == GoalStatus.STATUS_SUCCEEDED:
            if phase == 'approaching':
                if self._alignment_required():
                    self._start_alignment_navigation()
                    return
                self._start_harvest_dwell()
                return
            if phase == 'aligning':
                self._start_alignment_settle()
                return
            if phase == 'returning':
                self._finish_sequence_after_return()
                return

        if status == GoalStatus.STATUS_CANCELED:
            self._set_error(f'The {phase} goal was canceled before completion.')
            return

        error_msg = nav_result.error_msg if nav_result.error_msg else f'{phase} navigation failed.'
        if nav_result.error_code != NavigateToPose.Result.NONE:
            error_msg = f'{error_msg} (error_code={nav_result.error_code})'

        if phase == 'returning' and not self._used_return_fallback and self._active_plan is not None:
            if self._active_plan.fallback_return_waypoint_id != self._active_plan.return_waypoint_id:
                self.get_logger().warning(
                    f'Return navigation failed, retrying fallback target: {error_msg}'
                )
                self._start_return_navigation(use_fallback=True)
                return

        self._set_error(error_msg)

    def _alignment_required(self) -> bool:
        if self._active_plan is None:
            return False

        distance = math.hypot(
            self._active_plan.align_pose.x - self._active_plan.approach_pose.x,
            self._active_plan.align_pose.y - self._active_plan.approach_pose.y,
        )
        yaw_delta = abs(
            _normalize_angle(self._active_plan.align_pose.yaw - self._active_plan.approach_pose.yaw)
        )
        return distance > 0.05 or yaw_delta > math.radians(5.0)

    def _start_alignment_settle(self) -> None:
        if self._active_plan is None:
            self._set_error('Harvest alignment finished without an active harvest plan.')
            return

        self._set_state(
            'aligned',
            f'Holding aligned harvest stance for {self._active_plan.tomato_id} '
            f'for {self._alignment_settle_sec:.1f}s.',
        )
        if self._alignment_settle_sec <= 0.0:
            self._finish_alignment_settle()
            return

        self._cancel_alignment_timer()
        self._alignment_timer = self.create_timer(
            self._alignment_settle_sec,
            self._finish_alignment_settle,
        )

    def _finish_alignment_settle(self) -> None:
        self._cancel_alignment_timer()
        self._start_harvest_dwell()

    def _cancel_alignment_timer(self) -> None:
        if self._alignment_timer is None:
            return
        self._alignment_timer.cancel()
        self.destroy_timer(self._alignment_timer)
        self._alignment_timer = None

    def _start_harvest_dwell(self) -> None:
        if self._active_plan is None:
            self._set_error('Harvest dwell started without an active harvest plan.')
            return

        self._set_state(
            'harvesting',
            f'Simulating harvest for {self._active_plan.tomato_id} for {self._harvest_dwell_sec:.1f}s.',
        )
        if self._harvest_dwell_sec <= 0.0:
            self._finish_harvest_dwell()
            return

        self._cancel_harvest_timer()
        self._harvest_timer = self.create_timer(self._harvest_dwell_sec, self._finish_harvest_dwell)

    def _finish_harvest_dwell(self) -> None:
        self._cancel_harvest_timer()
        self._start_return_navigation(use_fallback=False)

    def _finish_sequence_after_return(self) -> None:
        if self._active_plan is None:
            self._set_error('Return completed without an active harvest plan.')
            return

        if self._resume_patrol_after_return:
            self._request_patrol_resume()
            return

        completed_tomato_id = self._active_plan.tomato_id
        return_waypoint_id = self._current_return_waypoint_id
        self._complete_sequence(
            f'Harvest route completed for {completed_tomato_id}; robot returned to {return_waypoint_id}.'
        )

    def _request_patrol_resume(self) -> None:
        if not self._patrol_resume_client.wait_for_service(timeout_sec=self._patrol_service_wait_sec):
            self._set_error('Patrol resume service is unavailable after harvest return.')
            return

        future = self._patrol_resume_client.call_async(Trigger.Request())
        future.add_done_callback(self._handle_patrol_resume_response)
        self._set_state(
            'resuming_patrol',
            f'Resuming patrol after returning to {self._current_return_waypoint_id}.',
        )

    def _handle_patrol_resume_response(self, future: Any) -> None:
        try:
            response = future.result()
        except Exception as exc:
            self._set_error(f'Failed to call patrol resume service: {exc}')
            return

        if not response.success:
            self._set_error(f'Patrol resume request failed: {response.message}')
            return

        if self._active_plan is None:
            self._set_error('Patrol resume completed without an active harvest plan.')
            return

        self._complete_sequence(
            f'Harvest route completed for {self._active_plan.tomato_id}; patrol resumed successfully.'
        )

    def _cancel_harvest_timer(self) -> None:
        if self._harvest_timer is None:
            return
        self._harvest_timer.cancel()
        self.destroy_timer(self._harvest_timer)
        self._harvest_timer = None

    def _build_pose_stamped(self, pose: Pose2D) -> PoseStamped:
        return build_latest_pose_stamped(
            frame_id=self._plan.frame_id,
            x_value=pose.x,
            y_value=pose.y,
            z_value=pose.z,
            yaw_value=pose.yaw,
        )

    def _complete_sequence(self, message: str) -> None:
        self._cancel_alignment_timer()
        self._cancel_harvest_timer()
        if self._active_plan is not None:
            self._completed_tomato_ids.add(self._active_plan.tomato_id)
        self._resume_patrol_after_return = False
        self._patrol_pause_deadline_ns = None
        self._current_return_waypoint_id = None
        self._current_navigation_phase = None
        self._active_plan = None
        self._set_state('completed', message)

    def _set_state(self, state: str, message: str) -> None:
        self._sequence_state = state
        self._sequence_message = message
        self.get_logger().info(message)
        self._publish_status()

    def _set_error(self, message: str) -> None:
        self._cancel_alignment_timer()
        self._cancel_harvest_timer()
        self._last_error_message = message
        self._sequence_state = 'error'
        self._sequence_message = message
        self._current_navigation_phase = None
        self.get_logger().error(message)
        self._publish_status()

    def _on_status_timer(self) -> None:
        if (
            self._sequence_state == 'waiting_for_patrol_pause'
            and self._patrol_pause_deadline_ns is not None
            and self.get_clock().now().nanoseconds > self._patrol_pause_deadline_ns
        ):
            self._set_error('Timed out while waiting for patrol to pause before harvest approach.')
            self._patrol_pause_deadline_ns = None
            return

        self._publish_status()

    def _publish_status(self) -> None:
        active_tomato_id = self._active_plan.tomato_id if self._active_plan is not None else None
        payload = {
            'state': self._sequence_state,
            'message': self._sequence_message,
            'zone_id': self._plan.zone_id,
            'frame_id': self._plan.frame_id,
            'active_tomato_id': active_tomato_id,
            'route_id': self._active_plan.route_id if self._active_plan is not None else None,
            'inspect_waypoint_id': (
                self._active_plan.inspect_waypoint_id if self._active_plan is not None else None
            ),
            'return_mode': self._active_plan.return_mode if self._active_plan is not None else None,
            'current_return_waypoint_id': self._current_return_waypoint_id,
            'navigation_phase': self._current_navigation_phase,
            'distance_remaining_m': self._last_distance_remaining_m,
            'error': self._last_error_message or None,
        }
        self._status_pub.publish(String(data=json.dumps(payload, sort_keys=True)))

    def destroy_node(self) -> bool:
        self._cancel_alignment_timer()
        self._cancel_harvest_timer()
        self._navigate_client.destroy()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = HarvestRouteNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
