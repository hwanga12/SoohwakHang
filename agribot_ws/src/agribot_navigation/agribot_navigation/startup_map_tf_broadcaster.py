# 이 모듈은 자율주행과 경로 계획 패키지에서 startup map tf broadcaster 기능을 담당한다.
from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from tf2_ros import TransformBroadcaster


class StartupMapTfBroadcaster(Node):
    # startup 지도 TF 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    def __init__(self) -> None:
        # StartupMapTfBroadcaster 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
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
        # identity transform를 외부 시스템이나 다음 처리 단계로 전달한다.
        if not rclpy.ok():
            return

        transform = TransformStamped()
        transform.header.stamp = self.get_clock().now().to_msg()
        transform.header.frame_id = 'map'
        transform.child_frame_id = 'odom'
        transform.transform.rotation.w = 1.0
        try:
            self._broadcaster.sendTransform(transform)
        except Exception:
            if rclpy.ok():
                raise

    def _handle_initial_pose(self, msg: PoseWithCovarianceStamped) -> None:
        # handle initial 위치 자세 정보를 계산해 반환한다.
        if not self._initial_pose_received:
            self._initial_pose_received = True
            self.get_logger().info(
                f'Received /initialpose ({msg.header.frame_id}), waiting for AMCL...'
            )

    def _handle_amcl_pose(self, msg: PoseWithCovarianceStamped) -> None:
        # handle amcl 위치 자세 정보를 계산해 반환한다.
        if self._amcl_pose_received:
            return

        self._amcl_pose_received = True
        self.get_logger().info(
            f'Received /amcl_pose ({msg.header.frame_id}), stopping temporary identity map -> odom broadcaster.'
        )
        self._stop_identity_broadcaster()

    def _stop_identity_broadcaster(self) -> None:
        # AMCL이 map -> odom을 잡기 시작하면 임시 identity TF는 즉시 내려야
        # TF_OLD_DATA와 중복 frame 경쟁을 만들지 않는다.
        # identity broadcaster 실행 흐름을 시작하거나 마무리한다.
        if self._timer is not None:
            self._timer.cancel()
            self.destroy_timer(self._timer)
            self._timer = None

        if self._initial_pose_subscription is not None:
            self.destroy_subscription(self._initial_pose_subscription)
            self._initial_pose_subscription = None

        if self._amcl_pose_subscription is not None:
            self.destroy_subscription(self._amcl_pose_subscription)
            self._amcl_pose_subscription = None


def main(args=None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = StartupMapTfBroadcaster()
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
