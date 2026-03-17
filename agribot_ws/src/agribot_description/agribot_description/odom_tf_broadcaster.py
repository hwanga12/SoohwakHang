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
        self._broadcaster = TransformBroadcaster(self)
        self._subscription = self.create_subscription(
            Odometry,
            '/odom',
            self._handle_odom,
            10,
        )

    def _handle_odom(self, msg: Odometry) -> None:
        transform = TransformStamped()
        transform.header.stamp = (
            msg.header.stamp
            if (msg.header.stamp.sec != 0 or msg.header.stamp.nanosec != 0)
            else self.get_clock().now().to_msg()
        )
        transform.header.frame_id = msg.header.frame_id or 'odom'
        transform.child_frame_id = msg.child_frame_id or 'base_link'
        transform.transform.translation.x = msg.pose.pose.position.x
        transform.transform.translation.y = msg.pose.pose.position.y
        transform.transform.translation.z = msg.pose.pose.position.z
        transform.transform.rotation = msg.pose.pose.orientation
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
