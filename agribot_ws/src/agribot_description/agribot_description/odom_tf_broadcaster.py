"""Broadcast the odom -> base_link transform from nav_msgs/Odometry."""

from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class OdomTfBroadcaster(Node):
    """Mirror /odom messages onto /tf for RViz2 and tf2 consumers."""

    def __init__(self) -> None:
        super().__init__('odom_tf_broadcaster')
        self.declare_parameter('reset_on_time_jump_sec', 1.0)
        self.declare_parameter('drop_warning_interval_sec', 2.0)
        self._broadcaster = TransformBroadcaster(self)
        self._last_stamp_ns: int | None = None
        self._reset_on_time_jump_ns = int(
            float(self.get_parameter('reset_on_time_jump_sec').value) * 1_000_000_000
        )
        self._drop_warning_interval_sec = max(
            0.0,
            float(self.get_parameter('drop_warning_interval_sec').value),
        )
        self._last_drop_warning_monotonic = 0.0
        self._subscription = self.create_subscription(
            Odometry,
            '/odom',
            self._handle_odom,
            10,
        )

    def _handle_odom(self, msg: Odometry) -> None:
        stamp = (
            msg.header.stamp
            if (msg.header.stamp.sec != 0 or msg.header.stamp.nanosec != 0)
            else self.get_clock().now().to_msg()
        )
        stamp_ns = stamp.sec * 1_000_000_000 + stamp.nanosec
        if self._last_stamp_ns is not None:
            if stamp_ns > self._last_stamp_ns:
                pass
            else:
                self._warn(
                    'Dropping stale /odom sample after backward timestamp jump; '
                    'keeping the latest odom -> base_link TF.'
                )
                return

        transform = TransformStamped()
        transform.header.stamp = stamp
        transform.header.frame_id = msg.header.frame_id or 'odom'
        transform.child_frame_id = msg.child_frame_id or 'base_link'
        transform.transform.translation.x = msg.pose.pose.position.x
        transform.transform.translation.y = msg.pose.pose.position.y
        transform.transform.translation.z = msg.pose.pose.position.z
        transform.transform.rotation = msg.pose.pose.orientation
        self._last_stamp_ns = stamp_ns
        self._broadcaster.sendTransform(transform)

    def _warn(self, message: str) -> None:
        from time import monotonic

        now_monotonic = monotonic()
        if now_monotonic - self._last_drop_warning_monotonic < self._drop_warning_interval_sec:
            return
        self.get_logger().warning(message)
        self._last_drop_warning_monotonic = now_monotonic


def main(args=None) -> None:
    rclpy.init(args=args)
    node = OdomTfBroadcaster()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
