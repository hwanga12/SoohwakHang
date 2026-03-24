"""HarvestTomato action server for staged harvest simulation."""

from __future__ import annotations

import json
import math
from pathlib import Path
import threading
import time
import uuid

from action_msgs.msg import GoalStatus
from agribot_interfaces.action import HarvestTomato
from agribot_interfaces.msg import HarvestEvent
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.task import Future
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .harvest_action_support import (
    PHASE_PROGRESS_PCT,
    alignment_required,
    build_feedback,
    build_harvest_event,
    build_result,
    ensure_harvest_target_available,
    resolve_harvest_goal,
)
from .harvest_routing import (
    CropCatalog,
    compute_harvest_route,
    get_default_crop_instances_path,
    load_crop_catalog,
)
from .patrol_config import Pose2D, PatrolPlan, get_default_patrol_waypoints_path, load_patrol_plan


class HarvestActionError(RuntimeError):
    """Raised when the harvest action cannot complete successfully."""


class HarvestActionCanceled(RuntimeError):
    """Raised when the client cancels the harvest action."""


class HarvestActionServerNode(Node):
    """Run a simulated harvest sequence behind the HarvestTomato action."""

    def __init__(self) -> None:
        super().__init__('harvest_action_server')
        callback_group = ReentrantCallbackGroup()

        self.declare_parameter('patrol_waypoints_file', str(get_default_patrol_waypoints_path()))
        self.declare_parameter('crop_instances_file', str(get_default_crop_instances_path()))
        self.declare_parameter('action_name', 'harvest_tomato')
        self.declare_parameter('navigate_to_pose_action', 'navigate_to_pose')
        self.declare_parameter('patrol_status_topic', 'patrol/status')
        self.declare_parameter('patrol_stop_service', 'patrol/stop')
        self.declare_parameter('nav_server_wait_sec', 5.0)
        self.declare_parameter('patrol_service_wait_sec', 1.0)
        self.declare_parameter('patrol_pause_timeout_sec', 8.0)
        self.declare_parameter('alignment_settle_sec', 0.75)
        self.declare_parameter('picking_duration_sec', 1.0)
        self.declare_parameter('verify_duration_sec', 0.6)
        self.declare_parameter('basket_stow_duration_sec', 0.8)
        self.declare_parameter('harvest_event_topic', 'harvest/event')
        self.declare_parameter('reject_duplicate_targets', True)

        self._plan = self._load_patrol_plan()
        self._catalog = self._load_crop_catalog()
        self._action_name = str(self.get_parameter('action_name').value)
        self._navigate_action_name = str(self.get_parameter('navigate_to_pose_action').value)
        self._patrol_status_topic = str(self.get_parameter('patrol_status_topic').value)
        self._patrol_stop_service = str(self.get_parameter('patrol_stop_service').value)
        self._harvest_event_topic = str(self.get_parameter('harvest_event_topic').value)
        self._nav_server_wait_sec = float(self.get_parameter('nav_server_wait_sec').value)
        self._patrol_service_wait_sec = float(self.get_parameter('patrol_service_wait_sec').value)
        self._patrol_pause_timeout_sec = float(self.get_parameter('patrol_pause_timeout_sec').value)
        self._alignment_settle_sec = max(
            0.0,
            float(self.get_parameter('alignment_settle_sec').value),
        )
        self._picking_duration_sec = max(
            0.0,
            float(self.get_parameter('picking_duration_sec').value),
        )
        self._verify_duration_sec = max(
            0.0,
            float(self.get_parameter('verify_duration_sec').value),
        )
        self._basket_stow_duration_sec = max(
            0.0,
            float(self.get_parameter('basket_stow_duration_sec').value),
        )
        self._reject_duplicate_targets = bool(self.get_parameter('reject_duplicate_targets').value)

        self._navigate_client = ActionClient(
            self,
            NavigateToPose,
            self._navigate_action_name,
            callback_group=callback_group,
        )
        self._patrol_stop_client = self.create_client(
            Trigger,
            self._patrol_stop_service,
            callback_group=callback_group,
        )
        self._patrol_status_subscription = self.create_subscription(
            String,
            self._patrol_status_topic,
            self._handle_patrol_status,
            10,
            callback_group=callback_group,
        )
        self._harvest_event_publisher = self.create_publisher(
            HarvestEvent,
            self._harvest_event_topic,
            10,
        )

        self._goal_lock = threading.Lock()
        self._goal_in_progress = False
        self._basket_count = 0
        self._harvested_tomato_ids: set[str] = set()
        self._last_patrol_status: dict[str, object] = {}

        self._action_server = ActionServer(
            self,
            HarvestTomato,
            self._action_name,
            execute_callback=self._execute_callback,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
            callback_group=callback_group,
        )

        self.get_logger().info(
            'HarvestTomato action server ready. '
            f'action_name={self._action_name}, '
            f'navigate_to_pose_action={self._navigate_action_name}, '
            f'harvest_event_topic={self._harvest_event_topic}'
        )

    def _load_patrol_plan(self) -> PatrolPlan:
        patrol_plan_path = Path(str(self.get_parameter('patrol_waypoints_file').value)).expanduser()
        if not patrol_plan_path.is_absolute():
            patrol_plan_path = get_default_patrol_waypoints_path().parent.parent / patrol_plan_path
        self._patrol_plan_path = patrol_plan_path
        return load_patrol_plan(patrol_plan_path)

    def _load_crop_catalog(self) -> CropCatalog:
        crop_catalog_path = Path(str(self.get_parameter('crop_instances_file').value)).expanduser()
        if not crop_catalog_path.is_absolute():
            crop_catalog_path = get_default_crop_instances_path().parent.parent / crop_catalog_path
        self._crop_catalog_path = crop_catalog_path
        return load_crop_catalog(crop_catalog_path)

    def _handle_patrol_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning('Ignoring invalid patrol status payload for harvest action.')
            return
        if not isinstance(payload, dict):
            self.get_logger().warning('Ignoring patrol status payload that is not a JSON object.')
            return
        self._last_patrol_status = payload

    def _goal_callback(self, goal_request: HarvestTomato.Goal) -> GoalResponse:
        with self._goal_lock:
            if self._goal_in_progress:
                self.get_logger().warning('Rejecting harvest goal because another goal is already active.')
                return GoalResponse.REJECT

        try:
            resolved_goal = resolve_harvest_goal(
                mission_id=goal_request.mission_id,
                zone_id=goal_request.zone_id,
                plant_id=goal_request.plant_id,
                fruit_id=goal_request.fruit_id,
                approach_waypoint_id=goal_request.approach_waypoint_id,
                default_zone_id=self._plan.zone_id,
                catalog=self._catalog,
            )
            preferred_waypoint_id = resolved_goal.preferred_approach_waypoint_id
            if preferred_waypoint_id and preferred_waypoint_id not in self._plan.waypoints:
                raise ValueError(f'Unknown approach_waypoint_id: {preferred_waypoint_id}')
        except ValueError as exc:
            self.get_logger().warning(f'Rejecting harvest goal: {exc}')
            return GoalResponse.REJECT

        return GoalResponse.ACCEPT

    def _cancel_callback(self, _goal_handle) -> CancelResponse:
        self.get_logger().info('Cancel request received for HarvestTomato action.')
        return CancelResponse.ACCEPT

    def _execute_callback(self, goal_handle) -> HarvestTomato.Result:
        with self._goal_lock:
            self._goal_in_progress = True

        try:
            resolved_goal = resolve_harvest_goal(
                mission_id=goal_handle.request.mission_id,
                zone_id=goal_handle.request.zone_id,
                plant_id=goal_handle.request.plant_id,
                fruit_id=goal_handle.request.fruit_id,
                approach_waypoint_id=goal_handle.request.approach_waypoint_id,
                default_zone_id=self._plan.zone_id,
                catalog=self._catalog,
            )
            ensure_harvest_target_available(
                catalog=self._catalog,
                tomato_id=resolved_goal.tomato_id,
                harvested_tomato_ids=self._harvested_tomato_ids if self._reject_duplicate_targets else set(),
            )

            self._publish_feedback(
                goal_handle,
                current_phase='PLANNING',
                aligned_to_target=False,
                gripper_engaged=False,
            )
            route_plan = compute_harvest_route(
                self._plan,
                self._catalog,
                resolved_goal.tomato_id,
                preferred_return_waypoint_id=resolved_goal.preferred_approach_waypoint_id or None,
            )

            self._maybe_pause_patrol(goal_handle)
            self._run_navigation_phase(
                goal_handle,
                route_plan.approach_pose,
                current_phase='APPROACHING',
                aligned_to_target=False,
                gripper_engaged=False,
            )
            if alignment_required(route_plan):
                self._run_navigation_phase(
                    goal_handle,
                    route_plan.align_pose,
                    current_phase='ALIGNING',
                    aligned_to_target=False,
                    gripper_engaged=False,
                )

            self._wait_phase(
                goal_handle,
                duration_sec=self._alignment_settle_sec,
                current_phase='ALIGNING',
                aligned_to_target=True,
                gripper_engaged=False,
            )
            self._wait_phase(
                goal_handle,
                duration_sec=self._picking_duration_sec,
                current_phase='PICKING',
                aligned_to_target=True,
                gripper_engaged=False,
            )
            self._publish_feedback(
                goal_handle,
                current_phase='PICKING',
                aligned_to_target=True,
                gripper_engaged=True,
                progress_pct=75.0,
            )
            self._wait_phase(
                goal_handle,
                duration_sec=self._verify_duration_sec,
                current_phase='VERIFYING',
                aligned_to_target=True,
                gripper_engaged=True,
            )
            ensure_harvest_target_available(
                catalog=self._catalog,
                tomato_id=resolved_goal.tomato_id,
                harvested_tomato_ids=self._harvested_tomato_ids if self._reject_duplicate_targets else set(),
            )
            self._wait_phase(
                goal_handle,
                duration_sec=self._basket_stow_duration_sec,
                current_phase='STOWING',
                aligned_to_target=True,
                gripper_engaged=True,
            )

            event_id = f'harvest-event-{uuid.uuid4()}'
            self._basket_count += 1
            self._harvested_tomato_ids.add(resolved_goal.tomato_id)
            event = build_harvest_event(
                event_id=event_id,
                mission_id=resolved_goal.mission_id,
                zone_id=resolved_goal.zone_id,
                plant_id=resolved_goal.plant_id,
                fruit_id=resolved_goal.tomato_id,
                frame_id=self._plan.frame_id,
                basket_count=self._basket_count,
                success=True,
            )
            event.header.stamp = self.get_clock().now().to_msg()
            self._harvest_event_publisher.publish(event)
            self._publish_feedback(
                goal_handle,
                current_phase='COMPLETED',
                aligned_to_target=True,
                gripper_engaged=False,
            )

            goal_handle.succeed()
            return build_result(
                success=True,
                harvest_event_id=event_id,
                basket_count=self._basket_count,
                message=(
                    f'Harvest action completed for {resolved_goal.tomato_id} '
                    f'via {route_plan.inspect_waypoint_id}.'
                ),
            )
        except HarvestActionCanceled as exc:
            event_id = f'harvest-event-{uuid.uuid4()}'
            event = build_harvest_event(
                event_id=event_id,
                mission_id=self._normalize_request_text(goal_handle.request.mission_id) or f'harvest-{uuid.uuid4()}',
                zone_id=self._normalize_request_text(goal_handle.request.zone_id) or self._plan.zone_id,
                plant_id=self._resolve_failure_plant_id(goal_handle.request),
                fruit_id=self._normalize_request_text(goal_handle.request.fruit_id),
                frame_id=self._plan.frame_id,
                basket_count=self._basket_count,
                success=False,
                failure_reason=str(exc),
            )
            event.header.stamp = self.get_clock().now().to_msg()
            self._harvest_event_publisher.publish(event)
            goal_handle.canceled()
            return build_result(
                success=False,
                harvest_event_id=event_id,
                basket_count=self._basket_count,
                message=str(exc),
            )
        except (HarvestActionError, ValueError) as exc:
            event_id = f'harvest-event-{uuid.uuid4()}'
            event = build_harvest_event(
                event_id=event_id,
                mission_id=self._normalize_request_text(goal_handle.request.mission_id) or f'harvest-{uuid.uuid4()}',
                zone_id=self._normalize_request_text(goal_handle.request.zone_id) or self._plan.zone_id,
                plant_id=self._resolve_failure_plant_id(goal_handle.request),
                fruit_id=self._normalize_request_text(goal_handle.request.fruit_id),
                frame_id=self._plan.frame_id,
                basket_count=self._basket_count,
                success=False,
                failure_reason=str(exc),
            )
            event.header.stamp = self.get_clock().now().to_msg()
            self._harvest_event_publisher.publish(event)
            goal_handle.abort()
            return build_result(
                success=False,
                harvest_event_id=event_id,
                basket_count=self._basket_count,
                message=str(exc),
            )
        finally:
            with self._goal_lock:
                self._goal_in_progress = False

    def _maybe_pause_patrol(self, goal_handle) -> None:
        if not self._patrol_is_active():
            return

        self._publish_feedback(
            goal_handle,
            current_phase='WAITING_FOR_PATROL_PAUSE',
            aligned_to_target=False,
            gripper_engaged=False,
        )
        if not self._patrol_stop_client.wait_for_service(timeout_sec=self._patrol_service_wait_sec):
            raise HarvestActionError('Patrol stop service is unavailable during harvest action.')

        future = self._patrol_stop_client.call_async(Trigger.Request())
        response = self._wait_for_future(
            future,
            goal_handle,
            description='patrol stop service response',
        )
        if not response.success and not self._patrol_is_quiescent():
            raise HarvestActionError(f'Patrol stop request failed: {response.message}')

        deadline = time.monotonic() + self._patrol_pause_timeout_sec
        while time.monotonic() < deadline:
            self._ensure_goal_is_active(goal_handle)
            if self._patrol_is_quiescent():
                return
            time.sleep(0.05)
        raise HarvestActionError('Timed out while waiting for patrol to pause before harvest.')

    def _run_navigation_phase(
        self,
        goal_handle,
        pose: Pose2D,
        *,
        current_phase: str,
        aligned_to_target: bool,
        gripper_engaged: bool,
    ) -> None:
        if not self._navigate_client.wait_for_server(timeout_sec=self._nav_server_wait_sec):
            raise HarvestActionError(
                f'NavigateToPose action server not available on {self._navigate_action_name}.'
            )

        self._publish_feedback(
            goal_handle,
            current_phase=current_phase,
            aligned_to_target=aligned_to_target,
            gripper_engaged=gripper_engaged,
        )

        nav_goal = NavigateToPose.Goal()
        nav_goal.pose = self._build_pose_stamped(pose)
        nav_goal.behavior_tree = ''

        send_future = self._navigate_client.send_goal_async(nav_goal)
        nav_goal_handle = self._wait_for_future(
            send_future,
            goal_handle,
            description=f'{current_phase} goal acceptance',
        )
        if not nav_goal_handle.accepted:
            raise HarvestActionError(f'NavigateToPose rejected the {current_phase} goal.')

        result_future = nav_goal_handle.get_result_async()
        result = self._wait_for_future(
            result_future,
            goal_handle,
            description=f'{current_phase} navigation result',
            nav_goal_handle=nav_goal_handle,
        )
        if result.status == GoalStatus.STATUS_SUCCEEDED:
            return
        if result.status == GoalStatus.STATUS_CANCELED:
            raise HarvestActionCanceled(f'Harvest action canceled during {current_phase}.')

        nav_result = result.result
        error_msg = nav_result.error_msg or f'{current_phase} navigation failed.'
        if nav_result.error_code != NavigateToPose.Result.NONE:
            error_msg = f'{error_msg} (error_code={nav_result.error_code})'
        raise HarvestActionError(error_msg)

    def _wait_phase(
        self,
        goal_handle,
        *,
        duration_sec: float,
        current_phase: str,
        aligned_to_target: bool,
        gripper_engaged: bool,
    ) -> None:
        self._publish_feedback(
            goal_handle,
            current_phase=current_phase,
            aligned_to_target=aligned_to_target,
            gripper_engaged=gripper_engaged,
        )
        if duration_sec <= 0.0:
            return

        deadline = time.monotonic() + duration_sec
        while time.monotonic() < deadline:
            self._ensure_goal_is_active(goal_handle)
            time.sleep(0.05)

    def _wait_for_future(
        self,
        future: Future,
        goal_handle,
        *,
        description: str,
        nav_goal_handle=None,
    ):
        while rclpy.ok() and not future.done():
            if goal_handle.is_cancel_requested:
                if nav_goal_handle is not None:
                    self._cancel_navigation_goal(nav_goal_handle)
                raise HarvestActionCanceled(f'Harvest action canceled while waiting for {description}.')
            time.sleep(0.05)
        if not future.done():
            raise HarvestActionError(f'Executor stopped while waiting for {description}.')
        try:
            return future.result()
        except Exception as exc:
            raise HarvestActionError(f'Failed while waiting for {description}: {exc}') from exc

    def _cancel_navigation_goal(self, nav_goal_handle) -> None:
        cancel_future = nav_goal_handle.cancel_goal_async()
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not cancel_future.done():
            time.sleep(0.05)

    def _ensure_goal_is_active(self, goal_handle) -> None:
        if goal_handle.is_cancel_requested:
            raise HarvestActionCanceled('Harvest action canceled by client.')

    def _resolve_failure_plant_id(self, goal_request: HarvestTomato.Goal) -> str:
        plant_id = self._normalize_request_text(goal_request.plant_id)
        if plant_id:
            return plant_id

        tomato_id = self._normalize_request_text(goal_request.fruit_id)
        tomato = self._catalog.tomatoes.get(tomato_id)
        if tomato is not None:
            return tomato.parent_plant_id
        return ''

    def _normalize_request_text(self, value: str | None) -> str:
        if value is None:
            return ''
        normalized = str(value).strip()
        if normalized.lower() in {'none', 'null'}:
            return ''
        return normalized

    def _publish_feedback(
        self,
        goal_handle,
        *,
        current_phase: str,
        aligned_to_target: bool,
        gripper_engaged: bool,
        progress_pct: float | None = None,
    ) -> None:
        feedback = build_feedback(
            current_phase=current_phase,
            progress_pct=(
                PHASE_PROGRESS_PCT.get(current_phase, 0.0)
                if progress_pct is None
                else progress_pct
            ),
            aligned_to_target=aligned_to_target,
            gripper_engaged=gripper_engaged,
        )
        goal_handle.publish_feedback(feedback)

    def _build_pose_stamped(self, pose: Pose2D) -> PoseStamped:
        stamped = PoseStamped()
        stamped.header.stamp = self.get_clock().now().to_msg()
        stamped.header.frame_id = self._plan.frame_id
        stamped.pose.position.x = pose.x
        stamped.pose.position.y = pose.y
        stamped.pose.position.z = pose.z
        stamped.pose.orientation.z = math.sin(pose.yaw / 2.0)
        stamped.pose.orientation.w = math.cos(pose.yaw / 2.0)
        return stamped

    def _patrol_is_active(self) -> bool:
        state = str(self._last_patrol_status.get('state', '')).strip()
        return state in {'starting', 'running', 'observing', 'stopping'}

    def _patrol_is_quiescent(self) -> bool:
        state = str(self._last_patrol_status.get('state', '')).strip()
        return state in {'', 'idle', 'stopped', 'completed', 'error'}

    def destroy_node(self) -> bool:
        self._action_server.destroy()
        self._navigate_client.destroy()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = HarvestActionServerNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
