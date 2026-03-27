"""Publish a temporary identity map -> odom transform during AMCL startup."""

from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped
import rclpy
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class StartupMapTfBroadcaster(Node):
    """Keep a stable identity map -> odom transform available in simulation."""

    def __init__(self) -> None:
        super().__init__('startup_map_tf_broadcaster')

        self._broadcaster = TransformBroadcaster(self)
        self._timer = self.create_timer(0.1, self._publish_identity_transform)
        self._initial_pose_subscription = self.create_subscription(
            PoseWithCovarianceStamped,
            '/initialpose',
            self._handle_initial_pose,
            10,
        )
        self._amcl_pose_subscription = self.create_subscription(
            PoseWithCovarianceStamped,
            '/amcl_pose',
            self._handle_amcl_pose,
            10,
        )
        self._initial_pose_received = False
        self._amcl_pose_received = False

    def _publish_identity_transform(self) -> None:
        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = 'map'
        transform.child_frame_id = 'odom'
        transform.transform.rotation.w = 1.0
        self._broadcaster.sendTransform(transform)

    def _handle_initial_pose(self, msg: PoseWithCovarianceStamped) -> None:
        if not self._initial_pose_received:
            self._initial_pose_received = True
            self.get_logger().info(
                f'Received /initialpose ({msg.header.frame_id}), waiting for AMCL...'
            )

    def _handle_amcl_pose(self, msg: PoseWithCovarianceStamped) -> None:
        if self._amcl_pose_received:
            return

        self._amcl_pose_received = True
        self.get_logger().info(
            f'Received /amcl_pose ({msg.header.frame_id}), keeping identity map -> odom broadcaster alive.'
        )
        self.destroy_subscription(self._initial_pose_subscription)
        self._initial_pose_subscription = None
        self.destroy_subscription(self._amcl_pose_subscription)
        self._amcl_pose_subscription = None


def main(args=None) -> None:
    rclpy.init(args=args)
    node = StartupMapTfBroadcaster()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
