# 이 모듈은 로봇 모델과 시뮬레이션 자산 패키지에서 cmd vel watchdog 로직을 담당한다.
from geometry_msgs.msg import Twist
import rclpy
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


class CmdVelWatchdog(Node):
    # CMD VEL 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    def __init__(self) -> None:
        # CmdVelWatchdog 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
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
        # handle cmd vel 정보를 계산해 반환한다.
        self._latest_command = msg
        self._last_command_time = self.get_clock().now()

    def _publish_command(self) -> None:
        # 명령를 외부 시스템이나 다음 처리 단계로 전달한다.
        if self._last_command_time is None:
            self._publisher.publish(Twist())
            return

        age = self.get_clock().now() - self._last_command_time
        if age > self._command_timeout:
            self._publisher.publish(Twist())
            return

        self._publisher.publish(self._latest_command)


def main(args=None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = CmdVelWatchdog()
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
