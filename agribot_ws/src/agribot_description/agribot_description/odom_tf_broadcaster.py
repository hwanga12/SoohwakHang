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
        self._broadcaster = TransformBroadcaster(self)
        self._last_stamp_ns: int | None = None
        self._reset_on_time_jump_ns = int(
            float(self.get_parameter('reset_on_time_jump_sec').value) * 1_000_000_000
        )
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
        if self._last_stamp_ns is not None and stamp_ns < self._last_stamp_ns:
            backwards_jump_ns = self._last_stamp_ns - stamp_ns
            if backwards_jump_ns >= self._reset_on_time_jump_ns:
                self.get_logger().warning(
                    'Detected backward /odom timestamp jump; resetting TF timestamp guard.'
                )
                self._last_stamp_ns = None
            else:
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
