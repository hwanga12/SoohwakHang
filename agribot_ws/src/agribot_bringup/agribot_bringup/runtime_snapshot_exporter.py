import math
from dataclasses import dataclass
from typing import Optional

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.time import Time
from tf2_ros import Buffer, TransformException, TransformListener

from .runtime_snapshot_service import (
    DEFAULT_MAP_ID,
    build_pose_snapshot_payload,
    build_semantic_layer_snapshot,
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


class RuntimeSnapshotExporter(Node):
    def __init__(self) -> None:
        super().__init__('runtime_snapshot_exporter')

        self.declare_parameter('use_sim_time', True)
        self.declare_parameter('map_id', DEFAULT_MAP_ID)
        self.declare_parameter('robot_id', 'AGR-02')
        self.declare_parameter('map_frame', 'map')
        self.declare_parameter('base_frame', 'base_link')
        self.declare_parameter('pose_write_period_sec', 0.5)
        self.declare_parameter('semantic_write_period_sec', 15.0)

        self._runtime_dir = runtime_dir_from_env()
        self._pose_snapshot_path = pose_snapshot_path(self._runtime_dir)
        self._semantic_snapshot_path = semantic_layer_snapshot_path(self._runtime_dir)
        self._map_id = str(self.get_parameter('map_id').value)
        self._robot_id = str(self.get_parameter('robot_id').value)
        self._map_frame = str(self.get_parameter('map_frame').value)
        self._base_frame = str(self.get_parameter('base_frame').value)
        self._last_pose_mode: Optional[str] = None
        self._latest_odom_records: dict[str, OdomRecord] = {}

        self._tf_buffer = Buffer()
        self._tf_listener = TransformListener(self._tf_buffer, self)

        for topic in ('/odometry/filtered', '/odom'):
            self.create_subscription(
                Odometry,
                topic,
                self._make_odom_callback(topic),
                20,
            )

        pose_write_period = float(self.get_parameter('pose_write_period_sec').value)
        semantic_write_period = float(self.get_parameter('semantic_write_period_sec').value)
        self.create_timer(pose_write_period, self._write_pose_snapshot)
        self.create_timer(semantic_write_period, self._write_semantic_snapshot)
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


def main(args=None) -> None:
    rclpy.init(args=args)
    node = RuntimeSnapshotExporter()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
