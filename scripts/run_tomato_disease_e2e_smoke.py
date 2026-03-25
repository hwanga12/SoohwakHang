from __future__ import annotations

import argparse
import base64
import heapq
from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import time
from typing import Any
from urllib import request
import uuid

import cv2
from cv_bridge import CvBridge
from agribot_interfaces.msg import IoTDeviceState
from geometry_msgs.msg import PoseStamped, Twist
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import Odometry
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
import yaml

from agribot_navigation.harvest_routing import compute_harvest_route, load_crop_catalog
from agribot_navigation.patrol_config import load_patrol_plan


@dataclass(frozen=True)
class PoseSnapshot:
    x: float
    y: float
    yaw: float


class TomatoDiseaseE2ESmoke(Node):
    def __init__(self, *, command_id: str) -> None:
        super().__init__('tomato_disease_e2e_smoke')
        self._bridge = CvBridge()
        self._latest_frame = None
        self._latest_pose: PoseSnapshot | None = None
        self._spraying_device_ids: set[str] = set()
        self._command_results: list[dict[str, Any]] = []
        self._command_id = command_id

        self._image_sub = self.create_subscription(
            Image,
            '/agribot/camera/image',
            self._handle_image,
            10,
        )
        self._odom_sub = self.create_subscription(
            Odometry,
            '/odom',
            self._handle_odom,
            20,
        )
        self._device_state_sub = self.create_subscription(
            IoTDeviceState,
            '/iot/device_state',
            self._handle_device_state,
            20,
        )
        self._command_result_sub = self.create_subscription(
            String,
            '/iot/command_result',
            self._handle_command_result,
            20,
        )
        self._nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)

    def _handle_image(self, msg: Image) -> None:
        self._latest_frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

    def _handle_odom(self, msg: Odometry) -> None:
        position = msg.pose.pose.position
        orientation = msg.pose.pose.orientation
        self._latest_pose = PoseSnapshot(
            x=float(position.x),
            y=float(position.y),
            yaw=_yaw_from_quaternion(
                float(orientation.x),
                float(orientation.y),
                float(orientation.z),
                float(orientation.w),
            ),
        )

    def _handle_device_state(self, msg: IoTDeviceState) -> None:
        if msg.state.strip().upper() == 'SPRAYING':
            self._spraying_device_ids.add(msg.device_id)

    def _handle_command_result(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        if payload.get('command_id') == self._command_id:
            self._command_results.append(payload)

    def wait_for_inputs(self, *, timeout_sec: float) -> None:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self._latest_frame is not None and self._latest_pose is not None:
                return
        raise RuntimeError('Timed out waiting for image and odometry topics.')

    def navigate_to(self, *, x: float, y: float, yaw: float, timeout_sec: float) -> None:
        if not self._nav_client.wait_for_server(timeout_sec=timeout_sec):
            raise RuntimeError('navigate_to_pose action server is unavailable.')

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'
        goal.pose.header.stamp = self.get_clock().now().to_msg()
        goal.pose.pose.position.x = float(x)
        goal.pose.pose.position.y = float(y)
        goal.pose.pose.position.z = 0.0
        goal.pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.pose.orientation.w = math.cos(yaw / 2.0)

        send_future = self._nav_client.send_goal_async(goal)
        self._spin_until_future(send_future, timeout_sec=timeout_sec)
        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            raise RuntimeError('navigate_to_pose goal was rejected.')

        result_future = goal_handle.get_result_async()
        self._spin_until_future(result_future, timeout_sec=timeout_sec)
        result = result_future.result()
        if result is None:
            raise RuntimeError('navigate_to_pose returned no result.')
        if result.status != 4:
            raise RuntimeError(f'navigate_to_pose failed with status={result.status}.')

    def _spin_until_future(self, future, *, timeout_sec: float) -> None:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if future.done():
                return
        raise RuntimeError('Timed out while waiting for a ROS future to complete.')

    def wait_for_stable_frame(self, *, duration_sec: float = 1.0) -> None:
        deadline = time.monotonic() + duration_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)

    def save_latest_frame(self, *, output_path: Path) -> bytes:
        if self._latest_frame is None:
            raise RuntimeError('No camera frame is available.')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        success, encoded = cv2.imencode('.jpg', self._latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not success:
            raise RuntimeError('Failed to encode the captured frame as JPEG.')
        encoded_bytes = encoded.tobytes()
        output_path.write_bytes(encoded_bytes)
        return encoded_bytes

    def drive_path(
        self,
        *,
        waypoints: list[tuple[float, float]],
        final_yaw: float,
        timeout_sec: float,
    ) -> None:
        if not waypoints:
            self.rotate_to_yaw(final_yaw=final_yaw, timeout_sec=timeout_sec)
            return

        deadline = time.monotonic() + timeout_sec
        waypoint_index = 0
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            pose = self.latest_pose
            target_x, target_y = waypoints[waypoint_index]
            distance = math.hypot(target_x - pose.x, target_y - pose.y)
            if distance <= 0.25:
                waypoint_index += 1
                if waypoint_index >= len(waypoints):
                    self.stop_motion()
                    self.rotate_to_yaw(final_yaw=final_yaw, timeout_sec=20.0)
                    return
                continue

            heading = math.atan2(target_y - pose.y, target_x - pose.x)
            heading_error = _normalize_angle(heading - pose.yaw)
            linear = min(0.35, distance * 0.45)
            angular = max(-0.85, min(0.85, heading_error * 1.2))
            if abs(heading_error) > 0.6:
                linear = 0.0
            self.publish_cmd_vel(linear_x=linear, angular_z=angular)

        self.stop_motion()
        raise RuntimeError('Timed out while following the fallback cmd_vel path.')

    def rotate_to_yaw(self, *, final_yaw: float, timeout_sec: float) -> None:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            pose = self.latest_pose
            yaw_error = _normalize_angle(final_yaw - pose.yaw)
            if abs(yaw_error) <= math.radians(8.0):
                self.stop_motion()
                return
            angular = max(-0.8, min(0.8, yaw_error * 1.6))
            self.publish_cmd_vel(linear_x=0.0, angular_z=angular)

        self.stop_motion()
        raise RuntimeError('Timed out while rotating to the final capture yaw.')

    def publish_cmd_vel(self, *, linear_x: float, angular_z: float) -> None:
        message = Twist()
        message.linear.x = float(linear_x)
        message.angular.z = float(angular_z)
        self._cmd_vel_pub.publish(message)

    def stop_motion(self) -> None:
        for _ in range(5):
            self.publish_cmd_vel(linear_x=0.0, angular_z=0.0)
            rclpy.spin_once(self, timeout_sec=0.05)

    def wait_for_spray_result(
        self,
        *,
        selected_device_id: str,
        timeout_sec: float,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            matching_result = next(
                (
                    item for item in self._command_results
                    if item.get('device_id') == selected_device_id
                ),
                None,
            )
            if matching_result is not None and selected_device_id in self._spraying_device_ids:
                return matching_result
        raise RuntimeError(
            f'Timed out waiting for spray completion on {selected_device_id} '
            f'for command_id={self._command_id}.'
        )

    @property
    def latest_pose(self) -> PoseSnapshot:
        if self._latest_pose is None:
            raise RuntimeError('No odometry pose is available.')
        return self._latest_pose


def _yaw_from_quaternion(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * ((w * z) + (x * y))
    cosy_cosp = 1.0 - 2.0 * ((y * y) + (z * z))
    return math.atan2(siny_cosp, cosy_cosp)


def _normalize_angle(angle: float) -> float:
    return math.atan2(math.sin(angle), math.cos(angle))


def _build_capture_pose(plant_x: float, plant_y: float) -> tuple[float, float, float]:
    if plant_x <= 0.0:
        return plant_x - 1.0, plant_y, 0.0
    return plant_x + 1.0, plant_y, math.pi


def _load_map_metadata(map_yaml_path: Path) -> tuple[Any, float, float, float]:
    payload = yaml.safe_load(map_yaml_path.read_text(encoding='utf-8'))
    image_path = (map_yaml_path.parent / payload['image']).resolve()
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f'Failed to load occupancy image from {image_path}')
    origin_x, origin_y, origin_yaw = payload['origin']
    return image, float(payload['resolution']), float(origin_x), float(origin_y)


def _map_to_pixel(
    *,
    x: float,
    y: float,
    image_height: int,
    resolution: float,
    origin_x: float,
    origin_y: float,
) -> tuple[int, int]:
    pixel_x = int(round((x - origin_x) / resolution))
    pixel_y = image_height - 1 - int(round((y - origin_y) / resolution))
    return pixel_x, pixel_y


def _pixel_to_map(
    *,
    pixel_x: int,
    pixel_y: int,
    image_height: int,
    resolution: float,
    origin_x: float,
    origin_y: float,
) -> tuple[float, float]:
    return (
        (pixel_x * resolution) + origin_x,
        ((image_height - 1 - pixel_y) * resolution) + origin_y,
    )


def _nearest_free_pixel(
    image,
    *,
    pixel_x: int,
    pixel_y: int,
    free_value_min: int = 250,
    max_radius_px: int = 40,
) -> tuple[int, int]:
    height, width = image.shape[:2]
    if 0 <= pixel_x < width and 0 <= pixel_y < height and int(image[pixel_y, pixel_x]) >= free_value_min:
        return pixel_x, pixel_y

    for radius in range(1, max_radius_px + 1):
        for delta_x in range(-radius, radius + 1):
            for delta_y in (-radius, radius):
                candidate_x = pixel_x + delta_x
                candidate_y = pixel_y + delta_y
                if (
                    0 <= candidate_x < width
                    and 0 <= candidate_y < height
                    and int(image[candidate_y, candidate_x]) >= free_value_min
                ):
                    return candidate_x, candidate_y
        for delta_y in range(-radius + 1, radius):
            for delta_x in (-radius, radius):
                candidate_x = pixel_x + delta_x
                candidate_y = pixel_y + delta_y
                if (
                    0 <= candidate_x < width
                    and 0 <= candidate_y < height
                    and int(image[candidate_y, candidate_x]) >= free_value_min
                ):
                    return candidate_x, candidate_y
    raise RuntimeError('Unable to find a nearby free pixel in the occupancy map.')


def _compute_fallback_path(
    *,
    map_yaml_path: Path,
    start_pose: PoseSnapshot,
    goal_x: float,
    goal_y: float,
) -> list[tuple[float, float]]:
    image, resolution, origin_x, origin_y = _load_map_metadata(map_yaml_path)
    height, width = image.shape[:2]
    start_pixel = _map_to_pixel(
        x=start_pose.x,
        y=start_pose.y,
        image_height=height,
        resolution=resolution,
        origin_x=origin_x,
        origin_y=origin_y,
    )
    goal_pixel = _map_to_pixel(
        x=goal_x,
        y=goal_y,
        image_height=height,
        resolution=resolution,
        origin_x=origin_x,
        origin_y=origin_y,
    )
    start_pixel = _nearest_free_pixel(image, pixel_x=start_pixel[0], pixel_y=start_pixel[1])
    goal_pixel = _nearest_free_pixel(image, pixel_x=goal_pixel[0], pixel_y=goal_pixel[1])

    frontier: list[tuple[float, tuple[int, int]]] = [(0.0, start_pixel)]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start_pixel: None}
    cost_so_far: dict[tuple[int, int], float] = {start_pixel: 0.0}
    neighbors = (
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    )

    while frontier:
        _, current = heapq.heappop(frontier)
        if current == goal_pixel:
            break

        for delta_x, delta_y in neighbors:
            next_pixel = (current[0] + delta_x, current[1] + delta_y)
            if not (
                0 <= next_pixel[0] < width
                and 0 <= next_pixel[1] < height
                and int(image[next_pixel[1], next_pixel[0]]) >= 250
            ):
                continue

            step_cost = math.hypot(delta_x, delta_y)
            new_cost = cost_so_far[current] + step_cost
            if next_pixel in cost_so_far and new_cost >= cost_so_far[next_pixel]:
                continue

            cost_so_far[next_pixel] = new_cost
            heuristic = math.hypot(goal_pixel[0] - next_pixel[0], goal_pixel[1] - next_pixel[1])
            heapq.heappush(frontier, (new_cost + heuristic, next_pixel))
            came_from[next_pixel] = current

    if goal_pixel not in came_from:
        raise RuntimeError('Fallback path planner could not connect the start and goal cells.')

    pixel_path: list[tuple[int, int]] = []
    cursor: tuple[int, int] | None = goal_pixel
    while cursor is not None:
        pixel_path.append(cursor)
        cursor = came_from[cursor]
    pixel_path.reverse()

    downsampled = pixel_path[::20]
    if downsampled[-1] != pixel_path[-1]:
        downsampled.append(pixel_path[-1])

    return [
        _pixel_to_map(
            pixel_x=pixel[0],
            pixel_y=pixel[1],
            image_height=height,
            resolution=resolution,
            origin_x=origin_x,
            origin_y=origin_y,
        )
        for pixel in downsampled
    ]


def _build_request_payload(
    *,
    observation_id: str,
    robot_id: str,
    zone_id: str,
    plant_id: str,
    fruit_id: str,
    target_position: dict[str, float],
    requested_by: str,
    disease_label: str,
    image_bytes: bytes,
) -> dict[str, Any]:
    encoded = base64.b64encode(image_bytes).decode('ascii')
    return {
        'observation_id': observation_id,
        'robot_id': robot_id,
        'zone_id': zone_id,
        'plant_id': plant_id,
        'fruit_id': fruit_id,
        'frame_id': 'agribot/camera_link/rgbd_camera',
        'target_position': target_position,
        'requested_by': requested_by,
        'auto_execute_treatment': True,
        'preliminary_label': disease_label,
        'preliminary_confidence': 0.99,
        'test_override_final_label': disease_label,
        'test_override_final_confidence': 0.99,
        'image_base64': encoded,
        'image_format': 'jpg',
    }


def _post_backend(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = request.Request(
        url,
        data=raw,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with request.urlopen(req, timeout=20.0) as response:
        return json.loads(response.read().decode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description='Run a Gazebo disease-treatment end-to-end smoke test.')
    parser.add_argument(
        '--backend-url',
        default='http://127.0.0.1:8000/api/v1/inference/confirm',
    )
    parser.add_argument(
        '--patrol-waypoints',
        default='/home/ssafy/Desktop/DEV/S14P21A602/agribot_ws/src/agribot_navigation/config/patrol_waypoints.yaml',
    )
    parser.add_argument(
        '--crop-instances',
        default='/home/ssafy/Desktop/DEV/S14P21A602/agribot_ws/src/agribot_description/config/crop_instances.yaml',
    )
    parser.add_argument(
        '--map-yaml',
        default='/home/ssafy/Desktop/DEV/S14P21A602/agribot_ws/src/agribot_navigation/maps/farm_map.yaml',
    )
    parser.add_argument('--tomato-id', default='farm01_plant_10_tomato_01')
    parser.add_argument('--disease-label', default='tomato_powdery_mildew')
    parser.add_argument('--robot-id', default='agribot')
    parser.add_argument('--requested-by', default='e2e-smoke')
    parser.add_argument('--navigate-timeout-sec', type=float, default=120.0)
    parser.add_argument('--spray-timeout-sec', type=float, default=20.0)
    parser.add_argument(
        '--use-nav2-first',
        action='store_true',
        help='Try navigate_to_pose before using the occupancy-map fallback controller.',
    )
    args = parser.parse_args()

    patrol_plan = load_patrol_plan(Path(args.patrol_waypoints))
    crop_catalog = load_crop_catalog(Path(args.crop_instances))
    route_plan = compute_harvest_route(patrol_plan, crop_catalog, args.tomato_id)
    tomato = crop_catalog.tomatoes[args.tomato_id]
    plant = crop_catalog.plants[route_plan.plant_id]
    observation_id = f'e2e-{uuid.uuid4()}'
    capture_pose_x, capture_pose_y, capture_pose_yaw = _build_capture_pose(
        plant.pose.x,
        plant.pose.y,
    )

    rclpy.init()
    node = TomatoDiseaseE2ESmoke(command_id=observation_id)
    try:
        node.wait_for_inputs(timeout_sec=20.0)
        navigation_method = 'cmd_vel_fallback'
        navigation_error = ''
        if args.use_nav2_first:
            navigation_method = 'nav2'
            try:
                node.navigate_to(
                    x=capture_pose_x,
                    y=capture_pose_y,
                    yaw=capture_pose_yaw,
                    timeout_sec=min(args.navigate_timeout_sec, 45.0),
                )
            except RuntimeError as exc:
                navigation_method = 'cmd_vel_fallback'
                navigation_error = str(exc)

        if navigation_method == 'cmd_vel_fallback':
            fallback_waypoints = _compute_fallback_path(
                map_yaml_path=Path(args.map_yaml),
                start_pose=node.latest_pose,
                goal_x=capture_pose_x,
                goal_y=capture_pose_y,
            )
            node.drive_path(
                waypoints=fallback_waypoints,
                final_yaw=capture_pose_yaw,
                timeout_sec=args.navigate_timeout_sec,
            )
        node.wait_for_stable_frame(duration_sec=1.5)

        runtime_dir = (
            Path('/home/ssafy/Desktop/DEV/S14P21A602/artifacts/runtime/e2e')
            / datetime.now().strftime('%Y%m%d')
        )
        snapshot_path = runtime_dir / f'{observation_id}.jpg'
        image_bytes = node.save_latest_frame(output_path=snapshot_path)

        current_pose = node.latest_pose
        facing_error_deg = abs(
            math.degrees(
                _normalize_angle(
                    math.atan2(
                        tomato.pose.y - current_pose.y,
                        tomato.pose.x - current_pose.x,
                    )
                    - current_pose.yaw
                )
            )
        )

        backend_payload = _build_request_payload(
            observation_id=observation_id,
            robot_id=args.robot_id,
            zone_id=plant.zone_id,
            plant_id=plant.plant_id,
            fruit_id=tomato.tomato_id,
            target_position={
                'x': float(plant.pose.x),
                'y': float(plant.pose.y),
                'z': float(plant.pose.z),
            },
            requested_by=args.requested_by,
            disease_label=args.disease_label,
            image_bytes=image_bytes,
        )
        backend_response = _post_backend(args.backend_url, backend_payload)
        selected_sprinkler = (
            ((backend_response.get('treatment_plan') or {}).get('selected_sprinkler') or {})
        )
        selected_device_id = str(selected_sprinkler.get('device_id', '')).strip()
        if not selected_device_id:
            raise RuntimeError(f'Backend response did not select a sprinkler: {backend_response}')

        spray_result = node.wait_for_spray_result(
            selected_device_id=selected_device_id,
            timeout_sec=args.spray_timeout_sec,
        )
        print(
            json.dumps(
                {
                    'observation_id': observation_id,
                    'align_pose': {
                        'x': capture_pose_x,
                        'y': capture_pose_y,
                        'yaw': capture_pose_yaw,
                    },
                    'current_pose': {
                        'x': current_pose.x,
                        'y': current_pose.y,
                        'yaw': current_pose.yaw,
                    },
                    'navigation_method': navigation_method,
                    'navigation_error': navigation_error,
                    'facing_error_deg': facing_error_deg,
                    'snapshot_path': str(snapshot_path),
                    'backend_response': backend_response,
                    'spray_result': spray_result,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
