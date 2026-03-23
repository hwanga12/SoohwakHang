"""Republish /cmd_vel with a timeout so the robot stops on stale commands."""

from geometry_msgs.msg import Twist
import rclpy
from rclpy.duration import Duration
from rclpy.node import Node


class CmdVelWatchdog(Node):
    """Forward command velocity messages and publish zero when they go stale."""

    def __init__(self) -> None:
        super().__init__('cmd_vel_watchdog')
        self.declare_parameter('input_topic', '/cmd_vel')
        self.declare_parameter('output_topic', '/cmd_vel_safe')
        self.declare_parameter('publish_rate_hz', 20.0)
        self.declare_parameter('command_timeout_sec', 0.25)

        input_topic = self.get_parameter('input_topic').value
        output_topic = self.get_parameter('output_topic').value
        publish_rate_hz = float(self.get_parameter('publish_rate_hz').value)
        self._command_timeout = Duration(
            seconds=float(self.get_parameter('command_timeout_sec').value)
        )

        self._publisher = self.create_publisher(Twist, output_topic, 10)
        self._subscription = self.create_subscription(
            Twist,
            input_topic,
            self._handle_cmd_vel,
            10,
        )
        self._timer = self.create_timer(1.0 / publish_rate_hz, self._publish_command)

        self._latest_command = Twist()
        self._last_command_time = None

    def _handle_cmd_vel(self, msg: Twist) -> None:
        self._latest_command = msg
        self._last_command_time = self.get_clock().now()

    def _publish_command(self) -> None:
        if self._last_command_time is None:
            self._publisher.publish(Twist())
            return

        age = self.get_clock().now() - self._last_command_time
        if age > self._command_timeout:
            self._publisher.publish(Twist())
            return

        self._publisher.publish(self._latest_command)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CmdVelWatchdog()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
