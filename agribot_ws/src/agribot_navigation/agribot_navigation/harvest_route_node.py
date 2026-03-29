"""Pause patrol, approach a harvest target, and return home or back to patrol."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Any
import uuid

from action_msgs.msg import GoalStatus
from agribot_interfaces.msg import CropStatus
from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.timer import Timer
from std_msgs.msg import Float64, String
from std_srvs.srv import Trigger

from .harvest_action_support import (
    build_basket_state,
    build_basket_state_payload,
    build_failure_alert_payload,
    build_harvest_event,
    build_harvest_event_payload,
    build_mission_status,
    build_mission_status_payload,
    PHASE_PROGRESS_PCT,
)
from .harvest_route_contract import HarvestRouteRequest, parse_harvest_route_request
from .harvest_simulation import (
    HarvestAnimationConfig,
    WorldPose,
    build_gz_pose_request,
    compute_basket_pose,
    compute_carry_pose,
    compute_grasp_pose,
    compute_hidden_pose,
)
from .harvest_runtime_store import (
    harvest_action_status_path,
    harvest_action_status_record_path,
    harvest_basket_state_path,
    harvest_event_record_path,
    harvest_failure_alert_path,
    harvest_latest_event_path,
    reset_harvest_runtime_session,
    runtime_dir_from_env,
    write_json_atomic,
)
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


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _poses_are_effectively_same(
    left_pose: Pose2D,
    right_pose: Pose2D,
    *,
    distance_tolerance_m: float = 0.05,
    yaw_tolerance_rad: float = math.radians(5.0),
) -> bool:
    return (
        math.hypot(left_pose.x - right_pose.x, left_pose.y - right_pose.y) <= distance_tolerance_m
        and abs(_normalize_angle(left_pose.yaw - right_pose.yaw)) <= yaw_tolerance_rad
    )


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
        self.declare_parameter('robot_pose_topic', '/odom')
        self.declare_parameter('harvest_animation_enabled', True)
        self.declare_parameter('harvest_arm_command_topic', '/agribot/harvest_arm_joint/cmd_pos')
        self.declare_parameter('gazebo_world_name', 'farm_world')
        self.declare_parameter('gazebo_partition', os.environ.get('GZ_PARTITION', 'agribot_sim'))
        self.declare_parameter('gazebo_command_timeout_ms', 3000)
        self.declare_parameter('gz_executable', 'gz')
        self.declare_parameter('harvest_arm_ready_position', 0.0)
        self.declare_parameter('harvest_arm_reach_position', 0.48)
        self.declare_parameter('harvest_arm_lift_position', -0.35)
        self.declare_parameter('harvest_reach_sec', 0.55)
        self.declare_parameter('harvest_grasp_sec', 0.18)
        self.declare_parameter('harvest_lift_sec', 0.55)
        self.declare_parameter('harvest_stow_sec', 1.2)
        self.declare_parameter('harvest_grasp_forward_m', -0.31)
        self.declare_parameter('harvest_grasp_lateral_m', 0.0)
        self.declare_parameter('harvest_grasp_z_m', 0.54)
        self.declare_parameter('harvest_carry_forward_m', -0.24)
        self.declare_parameter('harvest_carry_lateral_m', 0.0)
        self.declare_parameter('harvest_carry_z_m', 0.46)
        self.declare_parameter('harvest_basket_forward_m', -0.14)
        self.declare_parameter('harvest_basket_lateral_m', 0.0)
        self.declare_parameter('harvest_basket_z_m', 0.26)
        self.declare_parameter('harvest_visual_basket_slot_count', 2)
        self.declare_parameter('harvest_basket_slot_lateral_spacing_m', 0.05)
        self.declare_parameter('harvest_basket_slot_forward_spacing_m', 0.0)
        self.declare_parameter('harvest_basket_overflow_stack_z_m', 0.035)
        self.declare_parameter('harvest_hidden_x_m', 999.0)
        self.declare_parameter('harvest_hidden_y_m', 999.0)
        self.declare_parameter('harvest_hidden_z_m', -10.0)
        self.declare_parameter('harvest_inspect_waypoint_fallback_enabled', True)
        self.declare_parameter('harvest_demo_recovery_enabled', False)
        self.declare_parameter('harvest_navigation_target_mode', 'inspect_waypoint')
        self.declare_parameter('harvest_goal_soft_tolerance_m', 0.4)

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
        self._harvest_animation_enabled = bool(
            self.get_parameter('harvest_animation_enabled').value
        )
        self._gazebo_world_name = str(self.get_parameter('gazebo_world_name').value).strip()
        self._gazebo_partition = str(self.get_parameter('gazebo_partition').value).strip()
        self._gazebo_command_timeout_ms = int(
            self.get_parameter('gazebo_command_timeout_ms').value
        )
        self._gz_executable = str(self.get_parameter('gz_executable').value).strip() or 'gz'
        self._harvest_arm_ready_position = float(
            self.get_parameter('harvest_arm_ready_position').value
        )
        self._harvest_arm_reach_position = float(
            self.get_parameter('harvest_arm_reach_position').value
        )
        self._harvest_arm_lift_position = float(
            self.get_parameter('harvest_arm_lift_position').value
        )
        self._harvest_reach_sec = max(0.0, float(self.get_parameter('harvest_reach_sec').value))
        self._harvest_grasp_sec = max(0.0, float(self.get_parameter('harvest_grasp_sec').value))
        self._harvest_lift_sec = max(0.0, float(self.get_parameter('harvest_lift_sec').value))
        self._harvest_stow_sec = max(0.0, float(self.get_parameter('harvest_stow_sec').value))
        self._harvest_inspect_waypoint_fallback_enabled = bool(
            self.get_parameter('harvest_inspect_waypoint_fallback_enabled').value
        )
        self._harvest_demo_recovery_enabled = bool(
            self.get_parameter('harvest_demo_recovery_enabled').value
        )
        self._harvest_navigation_target_mode = str(
            self.get_parameter('harvest_navigation_target_mode').value
        ).strip() or 'inspect_waypoint'
        self._harvest_goal_soft_tolerance_m = max(
            0.05,
            float(self.get_parameter('harvest_goal_soft_tolerance_m').value),
        )
        self._animation_config = HarvestAnimationConfig(
            grasp_forward_m=float(self.get_parameter('harvest_grasp_forward_m').value),
            grasp_lateral_m=float(self.get_parameter('harvest_grasp_lateral_m').value),
            grasp_z_m=float(self.get_parameter('harvest_grasp_z_m').value),
            carry_forward_m=float(self.get_parameter('harvest_carry_forward_m').value),
            carry_lateral_m=float(self.get_parameter('harvest_carry_lateral_m').value),
            carry_z_m=float(self.get_parameter('harvest_carry_z_m').value),
            basket_forward_m=float(self.get_parameter('harvest_basket_forward_m').value),
            basket_lateral_m=float(self.get_parameter('harvest_basket_lateral_m').value),
            basket_z_m=float(self.get_parameter('harvest_basket_z_m').value),
            basket_slot_count=int(self.get_parameter('harvest_visual_basket_slot_count').value),
            basket_slot_lateral_spacing_m=float(
                self.get_parameter('harvest_basket_slot_lateral_spacing_m').value
            ),
            basket_slot_forward_spacing_m=float(
                self.get_parameter('harvest_basket_slot_forward_spacing_m').value
            ),
            basket_overflow_stack_z_m=float(
                self.get_parameter('harvest_basket_overflow_stack_z_m').value
            ),
            hidden_x_m=float(self.get_parameter('harvest_hidden_x_m').value),
            hidden_y_m=float(self.get_parameter('harvest_hidden_y_m').value),
            hidden_z_m=float(self.get_parameter('harvest_hidden_z_m').value),
        )

        crop_status_topic = str(self.get_parameter('crop_status_topic').value)
        harvest_request_topic = str(self.get_parameter('harvest_request_topic').value)
        patrol_status_topic = str(self.get_parameter('patrol_status_topic').value)
        status_topic = str(self.get_parameter('status_topic').value)
        patrol_stop_service = str(self.get_parameter('patrol_stop_service').value)
        patrol_resume_service = str(self.get_parameter('patrol_resume_service').value)
        robot_pose_topic = str(self.get_parameter('robot_pose_topic').value)
        harvest_arm_command_topic = str(self.get_parameter('harvest_arm_command_topic').value)

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
        self._robot_pose_sub = self.create_subscription(
            Odometry,
            robot_pose_topic,
            self._handle_robot_pose,
            10,
        )
        self._status_pub = self.create_publisher(String, status_topic, 10)
        self._arm_command_pub = self.create_publisher(Float64, harvest_arm_command_topic, 10)
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
        self._latest_robot_pose: Pose2D | None = None
        self._active_request: HarvestRouteRequest | None = None
        self._current_runtime_phase = ''
        self._runtime_dir = runtime_dir_from_env()
        self._loaded_tomato_ids: list[str] = []
        self._last_success_event_id = ''
        self._last_harvested_tomato_id = ''
        self._using_inspect_waypoint_approach = False
        self._using_demo_harvest_recovery = False
        self._ready_tomato_ids = {
            tomato.tomato_id
            for tomato in self._catalog.tomatoes.values()
            if tomato.ready_to_harvest
        }

        self.get_logger().info(
            'Loaded harvest routing metadata with '
            f'{len(self._catalog.tomatoes)} tomatoes from {self._crop_catalog_path}.'
        )
        reset_harvest_runtime_session(self._runtime_dir)
        self.get_logger().info(
            f'이전 harvest runtime session 흔적을 정리했습니다: {self._runtime_dir}'
        )
        self._publish_basket_state()
        self._write_idle_execution_status()
        self._publish_status()

    def _handle_robot_pose(self, msg: Odometry) -> None:
        orientation = msg.pose.pose.orientation
        yaw = math.atan2(
            2.0 * ((orientation.w * orientation.z) + (orientation.x * orientation.y)),
            1.0 - (2.0 * ((orientation.y * orientation.y) + (orientation.z * orientation.z))),
        )
        self._latest_robot_pose = Pose2D(
            x=float(msg.pose.pose.position.x),
            y=float(msg.pose.pose.position.y),
            z=float(msg.pose.pose.position.z),
            yaw=yaw,
        )

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

        self._begin_harvest_sequence(
            HarvestRouteRequest(
                tomato_id=tomato_id,
                plant_id=msg.plant_id.strip(),
                trigger='crop_status',
            )
        )

    def _handle_harvest_request(self, msg: String) -> None:
        request = parse_harvest_route_request(msg.data, default_trigger='manual_request')
        if request is None:
            self.get_logger().warning('Ignoring invalid harvest request payload.')
            return
        self._begin_harvest_sequence(request)

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

    def _begin_harvest_sequence(self, request: HarvestRouteRequest) -> None:
        tomato_id = request.tomato_id
        if self._sequence_state not in {'idle', 'completed', 'error'}:
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
                current_pose=self._latest_robot_pose,
            )
        except ValueError as exc:
            self._set_error(f'Failed to plan harvest route for {tomato_id}: {exc}')
            return

        self._used_return_fallback = False
        self._resume_patrol_after_return = False
        self._last_error_message = ''
        self._current_runtime_phase = ''
        self._using_inspect_waypoint_approach = False
        self._using_demo_harvest_recovery = False
        self._active_request = HarvestRouteRequest(
            tomato_id=tomato_id,
            plant_id=request.plant_id or self._active_plan.plant_id,
            mission_id=request.mission_id or f'harvest-route-{uuid.uuid4()}',
            requested_by=request.requested_by,
            trigger=request.trigger,
        )
        self.get_logger().info(
            f'Harvest route planned for {tomato_id} via {self._active_plan.inspect_waypoint_id} '
            f'(trigger={self._active_request.trigger}).'
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
        self._publish_execution_status(
            current_phase='WAITING_FOR_PATROL_PAUSE',
            detail_message=self._sequence_message,
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

        pose = self._approach_navigation_pose()
        message = (
            f'Approaching {self._active_plan.tomato_id} from '
            f'{self._active_plan.inspect_waypoint_name}.'
        )
        if self._should_use_inspect_waypoint_navigation():
            message = (
                f'Navigating to the safe harvest observation waypoint for '
                f'{self._active_plan.tomato_id} via '
                f'{self._active_plan.inspect_waypoint_name}.'
            )
        if self._using_inspect_waypoint_approach:
            message = (
                f'Approach pose was blocked, retrying {self._active_plan.tomato_id} via '
                f'{self._active_plan.inspect_waypoint_name}.'
            )
        if self._latest_pose_is_near(pose):
            self.get_logger().info(
                f'Already near the harvest navigation target for {self._active_plan.tomato_id}; '
                'starting the harvest sequence without an extra navigation goal.'
            )
            self._start_harvest_dwell()
            return

        self._start_navigation(
            pose,
            phase='approaching',
            message=message,
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
        target_pose = self._plan.waypoints[waypoint_id].pose
        if self._latest_pose_is_near(target_pose):
            fallback_note = ' using fallback return target' if use_fallback else ''
            self.get_logger().info(
                f'Return target {waypoint_id}{fallback_note} is already within the safe tolerance; '
                'finishing the harvest sequence without another navigation goal.'
            )
            self._finish_sequence_after_return()
            return
        fallback_note = ' using fallback return target' if use_fallback else ''
        self._start_navigation(
            target_pose,
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
        self._publish_execution_status(
            current_phase=self._runtime_phase_for_navigation(phase),
            detail_message=message,
        )

    def _runtime_phase_for_navigation(self, phase: str) -> str:
        return {
            'approaching': 'APPROACHING',
            'aligning': 'ALIGNING',
            'returning': 'RETURN_HOME',
        }.get(phase, phase.strip().upper())

    def _handle_goal_response(self, future: Any, phase: str) -> None:
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._set_error(f'Failed to send {phase} goal: {exc}')
            return

        self._goal_send_future = None

        if not goal_handle.accepted:
            error_message = f'NavigateToPose rejected the {phase} goal.'
            if phase == 'approaching' and self._recover_from_failed_approach(error_message):
                return
            if phase == 'aligning' and self._recover_from_failed_alignment(error_message):
                return
            if phase == 'returning' and not self._used_return_fallback and self._active_plan is not None:
                if self._active_plan.fallback_return_waypoint_id != self._active_plan.return_waypoint_id:
                    self.get_logger().warning(
                        'Return goal was rejected, retrying the fallback return waypoint: '
                        f'{error_message}'
                    )
                    self._start_return_navigation(use_fallback=True)
                    return
            self._set_error(error_message)
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
                if self._using_inspect_waypoint_approach or self._using_demo_harvest_recovery:
                    self._start_harvest_dwell()
                    return
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

        if self._navigation_phase_is_effectively_complete(phase):
            if phase == 'approaching':
                self.get_logger().warning(
                    f'{phase} navigation reported failure, but the robot is already near the safe '
                    f'observation target for {self._active_plan.tomato_id}; continuing with harvest.'
                )
                self._start_harvest_dwell()
                return
            if phase == 'aligning':
                self.get_logger().warning(
                    f'{phase} navigation reported failure, but the robot is already near the alignment '
                    f'target for {self._active_plan.tomato_id}; continuing with settle.'
                )
                self._start_alignment_settle()
                return
            if phase == 'returning':
                self.get_logger().warning(
                    f'{phase} navigation reported failure, but the robot is already near '
                    f'{self._current_return_waypoint_id}; completing the return stage.'
                )
                self._finish_sequence_after_return()
                return

        error_msg = nav_result.error_msg if nav_result.error_msg else f'{phase} navigation failed.'
        if nav_result.error_code != NavigateToPose.Result.NONE:
            error_msg = f'{error_msg} (error_code={nav_result.error_code})'

        if phase == 'approaching' and self._recover_from_failed_approach(error_msg):
            return
        if phase == 'aligning' and self._recover_from_failed_alignment(error_msg):
            return

        if phase == 'returning' and not self._used_return_fallback and self._active_plan is not None:
            if self._active_plan.fallback_return_waypoint_id != self._active_plan.return_waypoint_id:
                self.get_logger().warning(
                    f'Return navigation failed, retrying fallback target: {error_msg}'
                )
                self._start_return_navigation(use_fallback=True)
                return

        self._set_error(error_msg)

    def _inspect_waypoint_pose(self) -> Pose2D | None:
        if self._active_plan is None:
            return None
        waypoint = self._plan.waypoints.get(self._active_plan.inspect_waypoint_id)
        if waypoint is None:
            return None
        return waypoint.pose

    def _recover_from_failed_approach(self, error_msg: str) -> bool:
        if self._active_plan is None:
            return False

        inspect_pose = self._inspect_waypoint_pose()
        if (
            self._harvest_inspect_waypoint_fallback_enabled
            and not self._should_use_inspect_waypoint_navigation()
            and not self._using_inspect_waypoint_approach
            and inspect_pose is not None
            and not _poses_are_effectively_same(self._active_plan.approach_pose, inspect_pose)
        ):
            self._using_inspect_waypoint_approach = True
            self.get_logger().warning(
                'Approach navigation failed for '
                f'{self._active_plan.tomato_id}; retrying the inspect waypoint fallback: {error_msg}'
            )
            self._start_approach_navigation()
            return True

        if not self._harvest_demo_recovery_enabled:
            return False

        self._using_demo_harvest_recovery = True
        self.get_logger().warning(
            'Approach navigation failed for '
            f'{self._active_plan.tomato_id}; continuing with demo harvest recovery: {error_msg}'
        )
        self._start_harvest_dwell()
        return True

    def _recover_from_failed_alignment(self, error_msg: str) -> bool:
        if self._active_plan is None or not self._harvest_demo_recovery_enabled:
            return False

        self._using_demo_harvest_recovery = True
        self.get_logger().warning(
            'Alignment navigation failed for '
            f'{self._active_plan.tomato_id}; continuing with demo harvest recovery: {error_msg}'
        )
        self._start_alignment_settle()
        return True

    def _alignment_required(self) -> bool:
        if self._active_plan is None:
            return False

        if (
            self._should_use_inspect_waypoint_navigation()
            or self._using_inspect_waypoint_approach
            or self._using_demo_harvest_recovery
        ):
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
        self._publish_execution_status(
            current_phase='ALIGNING',
            detail_message=self._sequence_message,
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

        if self._using_demo_harvest_recovery:
            message = (
                f'Navigation fallback active; simulating harvest for '
                f'{self._active_plan.tomato_id} for {self._harvest_dwell_sec:.1f}s.'
            )
        elif self._using_inspect_waypoint_approach:
            message = (
                f'Executing harvest demo from inspect waypoint for '
                f'{self._active_plan.tomato_id} for {self._harvest_dwell_sec:.1f}s.'
            )
        else:
            message = (
                f'Simulating harvest for {self._active_plan.tomato_id} '
                f'for {self._harvest_dwell_sec:.1f}s.'
            )
        self._set_state(
            'harvesting',
            message,
        )
        self._publish_execution_status(
            current_phase='PICKING',
            detail_message=self._sequence_message,
        )
        if self._harvest_animation_enabled:
            self._publish_arm_position(self._harvest_arm_reach_position)
            if self._harvest_reach_sec <= 0.0:
                self._continue_harvest_to_grasp()
                return
            self._schedule_harvest_timer(self._harvest_reach_sec, self._continue_harvest_to_grasp)
            return

        if self._harvest_dwell_sec <= 0.0:
            self._finish_harvest_dwell()
            return

        self._schedule_harvest_timer(self._harvest_dwell_sec, self._finish_harvest_dwell)

    def _continue_harvest_to_grasp(self) -> None:
        self._cancel_harvest_timer()
        if self._active_plan is None:
            return
        tomato = self._catalog.tomatoes.get(self._active_plan.tomato_id)
        if tomato is None:
            self.get_logger().warning(
                f'No tomato metadata found for animation target {self._active_plan.tomato_id}.'
            )
            self._finish_harvest_dwell()
            return

        reference_pose = self._resolve_animation_reference_pose()
        if reference_pose is not None:
            grasp_pose = compute_grasp_pose(reference_pose, self._animation_config)
            self._set_gazebo_entity_pose(tomato.world_model_name, grasp_pose)

        self._set_state(
            'harvesting',
            f'{self._active_plan.tomato_id}를 그리퍼 가까이 고정했습니다.',
        )
        self._publish_execution_status(
            current_phase='PICKING',
            detail_message=self._sequence_message,
        )
        if self._harvest_grasp_sec <= 0.0:
            self._continue_harvest_to_carry()
            return
        self._schedule_harvest_timer(self._harvest_grasp_sec, self._continue_harvest_to_carry)

    def _continue_harvest_to_carry(self) -> None:
        self._cancel_harvest_timer()
        if self._active_plan is None:
            return
        tomato = self._catalog.tomatoes.get(self._active_plan.tomato_id)
        if tomato is None:
            self.get_logger().warning(
                f'No tomato metadata found for animation target {self._active_plan.tomato_id}.'
            )
            self._finish_harvest_dwell()
            return

        reference_pose = self._resolve_animation_reference_pose()
        if reference_pose is not None:
            carry_pose = compute_carry_pose(reference_pose, self._animation_config)
            self._set_gazebo_entity_pose(tomato.world_model_name, carry_pose)

        self._publish_arm_position(self._harvest_arm_lift_position)
        self._set_state(
            'harvesting',
            f'Picking {self._active_plan.tomato_id} and lifting it toward the basket.',
        )
        self._publish_execution_status(
            current_phase='PICKING',
            detail_message=self._sequence_message,
        )
        if self._harvest_lift_sec <= 0.0:
            self._continue_harvest_to_basket()
            return
        self._schedule_harvest_timer(self._harvest_lift_sec, self._continue_harvest_to_basket)

    def _continue_harvest_to_basket(self) -> None:
        self._cancel_harvest_timer()
        if self._active_plan is None:
            return
        tomato = self._catalog.tomatoes.get(self._active_plan.tomato_id)
        if tomato is None:
            self.get_logger().warning(
                f'No tomato metadata found for animation target {self._active_plan.tomato_id}.'
            )
            self._finish_harvest_dwell()
            return

        reference_pose = self._resolve_animation_reference_pose()
        if reference_pose is not None:
            basket_pose = compute_basket_pose(
                reference_pose,
                self._animation_config,
                basket_slot_index=len(self._completed_tomato_ids),
            )
            self._set_gazebo_entity_pose(tomato.world_model_name, basket_pose)

        self._publish_arm_position(self._harvest_arm_ready_position)
        self._set_state(
            'harvesting',
            f'Loading {self._active_plan.tomato_id} into the rear basket.',
        )
        self._publish_execution_status(
            current_phase='STOWING',
            detail_message=self._sequence_message,
        )
        if self._harvest_stow_sec <= 0.0:
            self._finish_harvest_dwell()
            return
        self._schedule_harvest_timer(self._harvest_stow_sec, self._finish_harvest_dwell)

    def _finish_harvest_dwell(self) -> None:
        self._cancel_harvest_timer()
        self._publish_arm_position(self._harvest_arm_ready_position)
        self._hide_harvested_tomato_visual()
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
        self._publish_execution_status(
            current_phase='RESUME',
            detail_message=self._sequence_message,
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

    def _schedule_harvest_timer(self, duration_sec: float, callback) -> None:
        self._cancel_harvest_timer()
        self._harvest_timer = self.create_timer(duration_sec, callback)

    def _resolve_animation_reference_pose(self) -> Pose2D | None:
        if self._latest_robot_pose is not None:
            return self._latest_robot_pose
        if self._active_plan is None:
            return None
        if self._alignment_required():
            return self._active_plan.align_pose
        return self._approach_navigation_pose()

    def _should_use_inspect_waypoint_navigation(self) -> bool:
        return self._harvest_navigation_target_mode == 'inspect_waypoint'

    def _approach_navigation_pose(self) -> Pose2D:
        if self._active_plan is None:
            raise RuntimeError('Active harvest plan is required to resolve the approach pose.')

        inspect_pose = self._inspect_waypoint_pose()
        if (
            inspect_pose is not None
            and (
                self._should_use_inspect_waypoint_navigation()
                or self._using_inspect_waypoint_approach
            )
        ):
            return inspect_pose
        return self._active_plan.approach_pose

    def _latest_pose_is_near(self, target_pose: Pose2D) -> bool:
        if self._latest_robot_pose is None:
            return False
        return (
            math.hypot(
                self._latest_robot_pose.x - target_pose.x,
                self._latest_robot_pose.y - target_pose.y,
            )
            <= self._harvest_goal_soft_tolerance_m
        )

    def _navigation_phase_is_effectively_complete(self, phase: str) -> bool:
        if self._active_plan is None:
            return False
        if phase == 'approaching':
            return self._latest_pose_is_near(self._approach_navigation_pose())
        if phase == 'aligning':
            return self._latest_pose_is_near(self._active_plan.align_pose)
        if phase == 'returning' and self._current_return_waypoint_id:
            waypoint = self._plan.waypoints.get(self._current_return_waypoint_id)
            if waypoint is None:
                return False
            return self._latest_pose_is_near(waypoint.pose)
        return False

    def _publish_arm_position(self, position: float) -> None:
        self._arm_command_pub.publish(Float64(data=float(position)))

    def _hide_harvested_tomato_visual(self) -> None:
        if self._active_plan is None:
            return

        tomato = self._catalog.tomatoes.get(self._active_plan.tomato_id)
        if tomato is None:
            self.get_logger().warning(
                f'No tomato metadata found while hiding harvested target {self._active_plan.tomato_id}.'
            )
            return

        self._set_gazebo_entity_pose(
            tomato.world_model_name,
            compute_hidden_pose(tomato.pose, self._animation_config),
        )

    def _set_gazebo_entity_pose(self, entity_name: str, pose: WorldPose) -> bool:
        command_env = os.environ.copy()
        if self._gazebo_partition:
            command_env['GZ_PARTITION'] = self._gazebo_partition

        service_candidates = (
            f'/world/{self._gazebo_world_name}/set_pose/blocking',
            f'/world/{self._gazebo_world_name}/set_pose',
        )
        last_error = ''
        for service_name in service_candidates:
            try:
                completed = subprocess.run(
                    [
                        self._gz_executable,
                        'service',
                        '-s',
                        service_name,
                        '--reqtype',
                        'gz.msgs.Pose',
                        '--reptype',
                        'gz.msgs.Boolean',
                        '--timeout',
                        str(self._gazebo_command_timeout_ms),
                        '--req',
                        build_gz_pose_request(entity_name, pose),
                    ],
                    check=False,
                    capture_output=True,
                    env=command_env,
                    text=True,
                )
            except FileNotFoundError:
                self.get_logger().warning(
                    f'Gazebo CLI "{self._gz_executable}" was not found; skipping harvest animation pose update.'
                )
                return False

            combined_output = f'{completed.stdout}\n{completed.stderr}'.strip()
            if completed.returncode == 0 and 'data: false' not in combined_output.lower():
                return True
            last_error = combined_output or str(completed.returncode)

        self.get_logger().warning(
            f'Failed to move Gazebo entity {entity_name}: {last_error}'
        )
        return False

    def _reset_visual_harvest_state(self) -> None:
        self._publish_arm_position(self._harvest_arm_ready_position)
        if self._active_plan is None:
            return

        tomato = self._catalog.tomatoes.get(self._active_plan.tomato_id)
        if tomato is None:
            return

        self._set_gazebo_entity_pose(
            tomato.world_model_name,
            WorldPose(
                x=tomato.pose.x,
                y=tomato.pose.y,
                z=tomato.pose.z,
            ),
        )

    def _publish_basket_state(self) -> None:
        state = build_basket_state(
            zone_id=self._plan.zone_id,
            frame_id=self._plan.frame_id,
            basket_count=len(self._loaded_tomato_ids),
            harvested_count=len(self._completed_tomato_ids),
            remaining_ready_count=max(0, len(self._ready_tomato_ids - self._completed_tomato_ids)),
            last_event_id=self._last_success_event_id,
            last_harvested_fruit_id=self._last_harvested_tomato_id,
            loaded_fruit_ids=self._loaded_tomato_ids,
        )
        state.header.stamp = self.get_clock().now().to_msg()
        payload = build_basket_state_payload(state, updated_at=_iso_now())
        write_json_atomic(harvest_basket_state_path(self._runtime_dir), payload)

    def _publish_execution_status(
        self,
        *,
        current_phase: str,
        detail_message: str,
        state: str = 'RUNNING',
        target_id: str = '',
        progress_pct: float | None = None,
        retry_count: int = 0,
    ) -> None:
        mission_id = self._active_request.mission_id if self._active_request is not None else ''
        if not mission_id:
            return

        self._current_runtime_phase = current_phase
        status = build_mission_status(
            mission_id=mission_id,
            mission_type='HARVEST',
            state=state,
            current_phase=current_phase,
            zone_id=self._plan.zone_id,
            target_id=target_id or (self._active_plan.tomato_id if self._active_plan is not None else ''),
            progress_pct=(
                PHASE_PROGRESS_PCT.get(current_phase, 0.0)
                if progress_pct is None
                else progress_pct
            ),
            retry_count=retry_count,
            detail_message=detail_message,
        )
        status.header.stamp = self.get_clock().now().to_msg()
        status.header.frame_id = self._plan.frame_id
        payload = build_mission_status_payload(status, updated_at=_iso_now())
        write_json_atomic(harvest_action_status_path(self._runtime_dir), payload)
        write_json_atomic(
            harvest_action_status_record_path(mission_id, self._runtime_dir),
            payload,
        )

    def _write_idle_execution_status(self) -> None:
        payload = {
            'mission_id': '',
            'mission_type': 'HARVEST',
            'state': 'IDLE',
            'status': 'idle',
            'current_phase': '',
            'zone_id': self._plan.zone_id,
            'target_id': '',
            'progress_pct': 0.0,
            'retry_count': 0,
            'detail_message': 'Harvest route node is idle.',
            'frame_id': self._plan.frame_id,
            'stamp': {'sec': 0, 'nanosec': 0},
            'updated_at': _iso_now(),
        }
        write_json_atomic(harvest_action_status_path(self._runtime_dir), payload)

    def _publish_harvest_event(self, *, success: bool, failure_reason: str = '') -> None:
        if self._active_plan is None or self._active_request is None:
            return

        event = build_harvest_event(
            event_id=f'{self._active_request.mission_id}-{uuid.uuid4().hex[:8]}',
            mission_id=self._active_request.mission_id,
            zone_id=self._plan.zone_id,
            plant_id=self._active_request.plant_id or self._active_plan.plant_id,
            fruit_id=self._active_plan.tomato_id,
            frame_id=self._plan.frame_id,
            basket_count=len(self._loaded_tomato_ids),
            success=success,
            failure_reason=failure_reason,
        )
        event.header.stamp = self.get_clock().now().to_msg()
        payload = build_harvest_event_payload(event, occurred_at=_iso_now())
        write_json_atomic(harvest_latest_event_path(self._runtime_dir), payload)
        write_json_atomic(harvest_event_record_path(event.event_id, self._runtime_dir), payload)
        if success:
            self._last_success_event_id = event.event_id

    def _publish_failure_alert(self, failure_reason: str) -> None:
        if self._active_request is None:
            return

        payload = json.loads(
            build_failure_alert_payload(
                mission_id=self._active_request.mission_id,
                zone_id=self._plan.zone_id,
                fruit_id=self._active_request.tomato_id,
                current_phase=self._current_runtime_phase or 'FAILED',
                failure_reason=failure_reason,
                retry_count=0,
                safety_stop_requested=False,
                safety_stop_completed=False,
                harvest_completed=False,
            )
        )
        payload['updated_at'] = _iso_now()
        write_json_atomic(harvest_failure_alert_path(self._runtime_dir), payload)

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
        self._publish_arm_position(self._harvest_arm_ready_position)
        self._using_inspect_waypoint_approach = False
        self._using_demo_harvest_recovery = False
        if self._active_plan is not None:
            self._completed_tomato_ids.add(self._active_plan.tomato_id)
            if self._active_plan.tomato_id not in self._loaded_tomato_ids:
                self._loaded_tomato_ids.append(self._active_plan.tomato_id)
            self._last_harvested_tomato_id = self._active_plan.tomato_id
        self._publish_harvest_event(success=True)
        self._publish_basket_state()
        self._publish_execution_status(
            current_phase='COMPLETED',
            detail_message=message,
            state='COMPLETED',
            progress_pct=100.0,
        )
        self._resume_patrol_after_return = False
        self._patrol_pause_deadline_ns = None
        self._current_return_waypoint_id = None
        self._current_navigation_phase = None
        self._current_runtime_phase = 'COMPLETED'
        self._active_plan = None
        self._active_request = None
        self._set_state('completed', message)

    def _set_state(self, state: str, message: str) -> None:
        self._sequence_state = state
        self._sequence_message = message
        self.get_logger().info(message)
        self._publish_status()

    def _set_error(self, message: str) -> None:
        self._cancel_alignment_timer()
        self._cancel_harvest_timer()
        self._reset_visual_harvest_state()
        active_tomato_id = (
            self._active_request.tomato_id
            if self._active_request is not None
            else (self._active_plan.tomato_id if self._active_plan is not None else '')
        )
        self._last_error_message = message
        self._sequence_state = 'error'
        self._sequence_message = message
        self._current_navigation_phase = None
        if active_tomato_id:
            if active_tomato_id not in message:
                self._sequence_message = f'{active_tomato_id}: {message}'
            self._publish_harvest_event(success=False, failure_reason=message)
            self._publish_failure_alert(message)
            self._publish_basket_state()
            self._publish_execution_status(
                current_phase=self._current_runtime_phase or 'FAILED',
                detail_message=message,
                state='FAILED',
            )
        self._resume_patrol_after_return = False
        self._patrol_pause_deadline_ns = None
        self._current_return_waypoint_id = None
        self._using_inspect_waypoint_approach = False
        self._using_demo_harvest_recovery = False
        self.get_logger().error(message)
        self._active_plan = None
        self._active_request = None
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
        active_tomato_id = (
            self._active_request.tomato_id
            if self._active_request is not None
            else (self._active_plan.tomato_id if self._active_plan is not None else None)
        )
        active_plant_id = (
            self._active_request.plant_id
            if self._active_request is not None
            else (self._active_plan.plant_id if self._active_plan is not None else None)
        )
        payload = {
            'state': self._sequence_state,
            'message': self._sequence_message,
            'zone_id': self._plan.zone_id,
            'frame_id': self._plan.frame_id,
            'mission_id': self._active_request.mission_id if self._active_request is not None else None,
            'plant_id': active_plant_id,
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
        self._write_idle_execution_status()
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
