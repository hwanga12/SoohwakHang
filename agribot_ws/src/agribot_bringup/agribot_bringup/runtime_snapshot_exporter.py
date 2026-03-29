import math
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

import rclpy
from nav_msgs.msg import Odometry, Path
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformException, TransformListener

from .runtime_snapshot_service import (
    DEFAULT_MAP_ID,
    build_navigation_path_snapshot_payload,
    build_pose_snapshot_payload,
    build_semantic_layer_snapshot,
    navigation_path_snapshot_path,
    pose_snapshot_path,
    runtime_dir_from_env,
    semantic_layer_snapshot_path,
    write_json_atomic,
)


def quaternion_to_yaw(x_value: float, y_value: float, z_value: float, w_value: float) -> float:
    siny_cosp = 2.0 * (w_value * z_value + x_value * y_value)
    cosy_cosp = 1.0 - 2.0 * (y_value * y_value + z_value * z_value)
    return math.atan2(siny_cosp, cosy_cosp)


@dataclass
class OdomRecord:
    x_value: float
    y_value: float
    z_value: float
    yaw_value: float
    frame_id: str
    linear_speed_mps: float
    stamp_nanoseconds: int


@dataclass(frozen=True)
class NavigationPathPoint:
    x_value: float
    y_value: float
    z_value: float
    yaw_value: float
    frame_id: str


@dataclass
class PathRecord:
    points: list[NavigationPathPoint]
    topic: str
    updated_at: str
    stamp_nanoseconds: int


PATH_POINT_TOLERANCE_M = 0.02


class RuntimeSnapshotExporter(Node):
    def __init__(self) -> None:
        super().__init__('runtime_snapshot_exporter')

        if not self.has_parameter('use_sim_time'):
            self.declare_parameter('use_sim_time', True)
        self.declare_parameter('map_id', DEFAULT_MAP_ID)
        self.declare_parameter('robot_id', 'AGR-02')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('pose_write_period_sec', 0.5)
        self.declare_parameter('semantic_write_period_sec', 15.0)
        self.declare_parameter('navigation_path_write_period_sec', 0.25)
        self.declare_parameter('global_plan_topic', '/plan')
        self.declare_parameter('local_plan_topic', '/local_plan')
        self.declare_parameter('navigation_preview_max_points', 60)
        self.declare_parameter('navigation_preview_max_distance_m', 6.0)

        self._runtime_dir = runtime_dir_from_env()
        self._pose_snapshot_path = pose_snapshot_path(self._runtime_dir)
        self._semantic_snapshot_path = semantic_layer_snapshot_path(self._runtime_dir)
        self._navigation_path_snapshot_path = navigation_path_snapshot_path(self._runtime_dir)
        self._map_id = str(self.get_parameter('map_id').value)
        self._robot_id = str(self.get_parameter('robot_id').value)
        self._map_frame = str(self.get_parameter('map_frame').value)
        self._base_frame = str(self.get_parameter('base_frame').value)
        self._global_plan_topic = str(self.get_parameter('global_plan_topic').value)
        self._local_plan_topic = str(self.get_parameter('local_plan_topic').value)
        self._navigation_preview_max_points = max(
            2,
            int(self.get_parameter('navigation_preview_max_points').value),
        )
        self._navigation_preview_max_distance_m = max(
            0.5,
            float(self.get_parameter('navigation_preview_max_distance_m').value),
        )
        self._last_pose_mode: Optional[str] = None
        self._latest_odom_records: dict[str, OdomRecord] = {}
        self._latest_path_records: dict[str, PathRecord] = {}

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        for topic in ('/odometry/filtered', '/odom'):
            self.create_subscription(
                Odometry,
                topic,
                self._make_odom_callback(topic),
                20,
            )
        for topic in (self._global_plan_topic, self._local_plan_topic):
            self.create_subscription(
                Path,
                topic,
                self._make_path_callback(topic),
                20,
            )

        pose_write_period = float(self.get_parameter('pose_write_period_sec').value)
        semantic_write_period = float(self.get_parameter('semantic_write_period_sec').value)
        navigation_path_write_period = float(
            self.get_parameter('navigation_path_write_period_sec').value,
        )
        self.create_timer(pose_write_period, self._write_pose_snapshot)
        self.create_timer(semantic_write_period, self._write_semantic_snapshot)
        self.create_timer(navigation_path_write_period, self._write_navigation_path_snapshot)
        self._write_semantic_snapshot()

        self.get_logger().info(
            f'Runtime snapshot exporter started. runtime_dir={self._runtime_dir}'
        )

    def _make_odom_callback(self, topic: str):
        def _callback(message: Odometry) -> None:
            pose = message.pose.pose
            twist = message.twist.twist
            self._latest_odom_records[topic] = OdomRecord(
                x_value=float(pose.position.x),
                y_value=float(pose.position.y),
                z_value=float(pose.position.z),
                yaw_value=quaternion_to_yaw(
                    pose.orientation.x,
                    pose.orientation.y,
                    pose.orientation.z,
                    pose.orientation.w,
                ),
                frame_id=message.header.frame_id or topic.strip('/'),
                linear_speed_mps=math.hypot(twist.linear.x, twist.linear.y),
                stamp_nanoseconds=(
                    int(message.header.stamp.sec) * 1_000_000_000
                    + int(message.header.stamp.nanosec)
                ),
            )

        return _callback

    def _make_path_callback(self, topic: str):
        def _callback(message: Path) -> None:
            points = self._path_points_from_message(message)
            if not points:
                self._latest_path_records.pop(topic, None)
                return

            stamp_nanoseconds = (
                int(message.header.stamp.sec) * 1_000_000_000
                + int(message.header.stamp.nanosec)
            )
            self._latest_path_records[topic] = PathRecord(
                points=points,
                topic=topic,
                updated_at=self._clock_now_iso(),
                stamp_nanoseconds=stamp_nanoseconds,
            )

        return _callback

    def _clock_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _lookup_frame_transform(self, source_frame: str) -> Optional[dict[str, float]]:
        try:
            transform = self._tf_buffer.lookup_transform(
                self._map_frame,
                source_frame,
                Time(),
            )
        except TransformException:
            return None

        translation = transform.transform.translation
        rotation = transform.transform.rotation
        return {
            'x': float(translation.x),
            'y': float(translation.y),
            'z': float(translation.z),
            'yaw': quaternion_to_yaw(rotation.x, rotation.y, rotation.z, rotation.w),
        }

    def _transform_point_to_map(
        self,
        *,
        x_value: float,
        y_value: float,
        z_value: float,
        yaw_value: float,
        frame_id: str,
    ) -> Optional[NavigationPathPoint]:
        normalized_frame_id = frame_id.strip() or self._map_frame
        if normalized_frame_id == self._map_frame:
            return NavigationPathPoint(
                x_value=x_value,
                y_value=y_value,
                z_value=z_value,
                yaw_value=yaw_value,
                frame_id=self._map_frame,
            )

        transform = self._lookup_frame_transform(normalized_frame_id)
        if transform is None:
            return None

        transform_yaw = float(transform['yaw'])
        cos_yaw = math.cos(transform_yaw)
        sin_yaw = math.sin(transform_yaw)
        map_x = float(transform['x']) + (x_value * cos_yaw - y_value * sin_yaw)
        map_y = float(transform['y']) + (x_value * sin_yaw + y_value * cos_yaw)
        return NavigationPathPoint(
            x_value=map_x,
            y_value=map_y,
            z_value=float(transform['z']) + z_value,
            yaw_value=yaw_value + transform_yaw,
            frame_id=self._map_frame,
        )

    def _trim_path_points(
        self,
        points: list[NavigationPathPoint],
    ) -> list[NavigationPathPoint]:
        trimmed: list[NavigationPathPoint] = []
        traversed_distance = 0.0
        previous_point: NavigationPathPoint | None = None

        for point in points:
            if previous_point is not None:
                delta_x = point.x_value - previous_point.x_value
                delta_y = point.y_value - previous_point.y_value
                segment_distance = math.hypot(delta_x, delta_y)
                if segment_distance <= PATH_POINT_TOLERANCE_M:
                    continue
                if trimmed and (
                    traversed_distance + segment_distance
                    > self._navigation_preview_max_distance_m
                ):
                    break
                traversed_distance += segment_distance

            trimmed.append(point)
            previous_point = point
            if len(trimmed) >= self._navigation_preview_max_points:
                break

        return trimmed

    def _path_points_from_message(self, message: Path) -> list[NavigationPathPoint]:
        source_frame = str(message.header.frame_id).strip() or self._map_frame
        transformed_points: list[NavigationPathPoint] = []

        for pose_stamped in message.poses:
            pose = pose_stamped.pose
            point = self._transform_point_to_map(
                x_value=float(pose.position.x),
                y_value=float(pose.position.y),
                z_value=float(pose.position.z),
                yaw_value=quaternion_to_yaw(
                    pose.orientation.x,
                    pose.orientation.y,
                    pose.orientation.z,
                    pose.orientation.w,
                ),
                frame_id=str(pose_stamped.header.frame_id).strip() or source_frame,
            )
            if point is None:
                continue
            transformed_points.append(point)

        return self._trim_path_points(transformed_points)

    def _lookup_map_pose(self) -> Optional[dict[str, float | str]]:
        try:
            transform = self._tf_buffer.lookup_transform(
                self._map_frame,
                self._base_frame,
                Time(),
            )
        except TransformException:
            return None

        translation = transform.transform.translation
        rotation = transform.transform.rotation
        return {
            'x': float(translation.x),
            'y': float(translation.y),
            'z': float(translation.z),
            'yaw': quaternion_to_yaw(rotation.x, rotation.y, rotation.z, rotation.w),
            'frame_id': self._map_frame,
        }

    def _latest_odom(self) -> Optional[OdomRecord]:
        if not self._latest_odom_records:
            return None

        return max(
            self._latest_odom_records.values(),
            key=lambda record: record.stamp_nanoseconds,
        )

    def _serialize_path_points(
        self,
        points: list[NavigationPathPoint],
    ) -> list[dict[str, float | str]]:
        return [
            {
                'x': point.x_value,
                'y': point.y_value,
                'z': point.z_value,
                'yaw': point.yaw_value,
                'frame_id': point.frame_id,
            }
            for point in points
        ]

    def _write_pose_snapshot(self) -> None:
        map_pose = self._lookup_map_pose()
        latest_odom = self._latest_odom()

        if map_pose is not None:
            payload = build_pose_snapshot_payload(
                map_id=self._map_id,
                robot_id=self._robot_id,
                x_value=float(map_pose['x']),
                y_value=float(map_pose['y']),
                z_value=float(map_pose['z']),
                yaw_value=float(map_pose['yaw']),
                frame_id=str(map_pose['frame_id']),
                linear_speed_mps=latest_odom.linear_speed_mps if latest_odom else 0.0,
                source_mode='tf_map',
            )
            mode = 'tf_map'
        elif latest_odom is not None:
            payload = build_pose_snapshot_payload(
                map_id=self._map_id,
                robot_id=self._robot_id,
                x_value=latest_odom.x_value,
                y_value=latest_odom.y_value,
                z_value=latest_odom.z_value,
                yaw_value=latest_odom.yaw_value,
                frame_id=latest_odom.frame_id,
                linear_speed_mps=latest_odom.linear_speed_mps,
                source_mode='odom_fallback',
            )
            mode = 'odom_fallback'
        else:
            return

        write_json_atomic(self._pose_snapshot_path, payload)
        if self._last_pose_mode != mode:
            if mode == 'tf_map':
                self.get_logger().info('map -> base_link pose 스냅샷 기록을 시작합니다.')
            else:
                self.get_logger().warn('map TF 대기 중입니다. odom fallback pose를 기록합니다.')
            self._last_pose_mode = mode

    def _write_semantic_snapshot(self) -> None:
        payload = build_semantic_layer_snapshot(self._map_id)
        write_json_atomic(self._semantic_snapshot_path, payload)

    def _write_navigation_path_snapshot(self) -> None:
        local_plan_record = self._latest_path_records.get(self._local_plan_topic)
        global_plan_record = self._latest_path_records.get(self._global_plan_topic)

        active_record = local_plan_record
        preview_kind = 'local_plan'
        if active_record is None or len(active_record.points) < 2:
            active_record = global_plan_record
            preview_kind = 'global_plan'

        if active_record is None or len(active_record.points) < 2:
            preview_kind = 'none'

        payload = build_navigation_path_snapshot_payload(
            map_id=self._map_id,
            robot_id=self._robot_id,
            frame_id=self._map_frame,
            preview_kind=preview_kind,
            active_points=self._serialize_path_points(active_record.points) if active_record else [],
            active_topic=active_record.topic if active_record else None,
            local_plan_points=(
                self._serialize_path_points(local_plan_record.points)
                if local_plan_record
                else []
            ),
            local_plan_topic=local_plan_record.topic if local_plan_record else self._local_plan_topic,
            local_plan_updated_at=local_plan_record.updated_at if local_plan_record else None,
            global_plan_points=(
                self._serialize_path_points(global_plan_record.points)
                if global_plan_record
                else []
            ),
            global_plan_topic=global_plan_record.topic if global_plan_record else self._global_plan_topic,
            global_plan_updated_at=global_plan_record.updated_at if global_plan_record else None,
        )
        write_json_atomic(self._navigation_path_snapshot_path, payload)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RuntimeSnapshotExporter()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    except Exception:
        if rclpy.ok():
            raise
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
