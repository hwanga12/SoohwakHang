# 이 모듈은 로봇 모델과 시뮬레이션 자산 패키지에서 odom tf broadcaster 로직을 담당한다.
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class OdomTfBroadcaster(Node):
    # odom TF 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    def __init__(self) -> None:
        # OdomTfBroadcaster 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
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
        # handle odom 정보를 계산해 반환한다.
        if not rclpy.ok():
            return

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
        try:
            self._broadcaster.sendTransform(transform)
        except Exception:
            if rclpy.ok():
                raise

    def _warn(self, message: str) -> None:
        # warn 정보를 계산해 반환한다.
        from time import monotonic

        now_monotonic = monotonic()
        if now_monotonic - self._last_drop_warning_monotonic < self._drop_warning_interval_sec:
            return
        self.get_logger().warning(message)
        self._last_drop_warning_monotonic = now_monotonic


def main(args=None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = OdomTfBroadcaster()
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
