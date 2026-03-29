"""Drop stale simulated clock and state messages before they poison TF consumers."""

from __future__ import annotations

from dataclasses import dataclass
import fcntl
import os
from pathlib import Path
import sys
from tempfile import gettempdir
from time import monotonic

from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import JointState, LaserScan


def stamp_to_nanoseconds(sec_value: int, nanosec_value: int) -> int:
    return int(sec_value) * 1_000_000_000 + int(nanosec_value)


def nanoseconds_to_stamp_fields(stamp_ns: int) -> tuple[int, int]:
    normalized_ns = max(0, int(stamp_ns))
    sec_value, nanosec_value = divmod(normalized_ns, 1_000_000_000)
    return int(sec_value), int(nanosec_value)


def normalized_state_stamp_ns(
    *,
    source_stamp_ns: int,
    latest_clock_stamp_ns: int | None,
    last_published_stamp_ns: int | None,
) -> int:
    normalized_ns = int(source_stamp_ns)
    if latest_clock_stamp_ns is not None:
        normalized_ns = max(normalized_ns, int(latest_clock_stamp_ns))
    if last_published_stamp_ns is not None and normalized_ns <= last_published_stamp_ns:
        normalized_ns = last_published_stamp_ns + 1
    return normalized_ns


class SingletonLockError(RuntimeError):
    pass


@dataclass
class MonotonicStampFilter:
    last_stamp_ns: int | None = None

    def accept(self, stamp_ns: int) -> bool:
        if self.last_stamp_ns is None or stamp_ns > self.last_stamp_ns:
            self.last_stamp_ns = stamp_ns
            return True
        return False

    def reset(self, stamp_ns: int) -> None:
        self.last_stamp_ns = stamp_ns


class SimTimeGuard(Node):
    """Republish only monotonic simulation messages to keep Nav2 TF stable."""

    def __init__(self) -> None:
        super().__init__('sim_time_guard')

        self.declare_parameter('clock_input_topic', '/clock_raw')
        self.declare_parameter('clock_output_topic', '/clock')
        self.declare_parameter('odom_input_topic', '/odom_raw')
        self.declare_parameter('odom_output_topic', '/odom')
        self.declare_parameter('joint_states_input_topic', '/joint_states_raw')
        self.declare_parameter('joint_states_output_topic', '/joint_states')
        self.declare_parameter('lidar_input_topic', '/agribot/lidar_raw')
        self.declare_parameter('lidar_output_topic', '/agribot/lidar')
        self.declare_parameter('warning_interval_sec', 2.0)
        self.declare_parameter('reset_on_time_jump_sec', 1.0)
        # Sim time can legitimately run much faster than wall time, especially
        # when Gazebo starts headless or the physics loop briefly outruns
        # rendering. Only guard against backwards jumps; forward jumps are
        # allowed as long as stamps keep increasing.

        self._warning_interval_sec = max(0.0, float(self.get_parameter('warning_interval_sec').value))
        self._reset_on_time_jump_ns = int(
            float(self.get_parameter('reset_on_time_jump_sec').value) * 1_000_000_000
        )
        self._last_warning_monotonic_by_stream: dict[str, float] = {}

        self._clock_filter = MonotonicStampFilter()
        self._odom_filter = MonotonicStampFilter()
        self._joint_state_filter = MonotonicStampFilter()
        self._lidar_filter = MonotonicStampFilter()
        self._latest_clock_stamp_ns: int | None = None

        clock_input_topic = str(self.get_parameter('clock_input_topic').value)
        clock_output_topic = str(self.get_parameter('clock_output_topic').value)
        odom_input_topic = str(self.get_parameter('odom_input_topic').value)
        odom_output_topic = str(self.get_parameter('odom_output_topic').value)
        joint_states_input_topic = str(self.get_parameter('joint_states_input_topic').value)
        joint_states_output_topic = str(self.get_parameter('joint_states_output_topic').value)
        lidar_input_topic = str(self.get_parameter('lidar_input_topic').value)
        lidar_output_topic = str(self.get_parameter('lidar_output_topic').value)

        self._clock_publisher = self.create_publisher(Clock, clock_output_topic, 20)
        self._odom_publisher = self.create_publisher(Odometry, odom_output_topic, 20)
        self._joint_state_publisher = self.create_publisher(JointState, joint_states_output_topic, 20)
        self._lidar_publisher = self.create_publisher(LaserScan, lidar_output_topic, 20)

        self.create_subscription(Clock, clock_input_topic, self._handle_clock, 20)
        self.create_subscription(Odometry, odom_input_topic, self._handle_odom, 20)
        self.create_subscription(JointState, joint_states_input_topic, self._handle_joint_states, 20)
        self.create_subscription(LaserScan, lidar_input_topic, self._handle_lidar, 20)

        self.get_logger().info(
            'sim time guard started. '
            f'clock={clock_input_topic}->{clock_output_topic}, '
            f'odom={odom_input_topic}->{odom_output_topic}, '
            f'joint_states={joint_states_input_topic}->{joint_states_output_topic}, '
            f'lidar={lidar_input_topic}->{lidar_output_topic}'
        )

    def _handle_clock(self, message: Clock) -> None:
        stamp_ns = stamp_to_nanoseconds(message.clock.sec, message.clock.nanosec)
        self._latest_clock_stamp_ns = max(
            stamp_ns,
            self._latest_clock_stamp_ns or stamp_ns,
        )
        self._republish_monotonic(
            'clock',
            stamp_ns,
            message,
            self._clock_filter,
            self._clock_publisher.publish,
        )

    def _handle_odom(self, message: Odometry) -> None:
        stamp_ns = stamp_to_nanoseconds(message.header.stamp.sec, message.header.stamp.nanosec)
        normalized_stamp_ns = normalized_state_stamp_ns(
            source_stamp_ns=stamp_ns,
            latest_clock_stamp_ns=self._latest_clock_stamp_ns,
            last_published_stamp_ns=self._odom_filter.last_stamp_ns,
        )
        message.header.stamp.sec, message.header.stamp.nanosec = nanoseconds_to_stamp_fields(normalized_stamp_ns)
        self._republish_monotonic(
            'odom',
            normalized_stamp_ns,
            message,
            self._odom_filter,
            self._odom_publisher.publish,
        )

    def _handle_joint_states(self, message: JointState) -> None:
        stamp_ns = stamp_to_nanoseconds(message.header.stamp.sec, message.header.stamp.nanosec)
        normalized_stamp_ns = normalized_state_stamp_ns(
            source_stamp_ns=stamp_ns,
            latest_clock_stamp_ns=self._latest_clock_stamp_ns,
            last_published_stamp_ns=self._joint_state_filter.last_stamp_ns,
        )
        message.header.stamp.sec, message.header.stamp.nanosec = nanoseconds_to_stamp_fields(normalized_stamp_ns)
        self._republish_monotonic(
            'joint_states',
            normalized_stamp_ns,
            message,
            self._joint_state_filter,
            self._joint_state_publisher.publish,
        )

    def _handle_lidar(self, message: LaserScan) -> None:
        stamp_ns = stamp_to_nanoseconds(message.header.stamp.sec, message.header.stamp.nanosec)
        normalized_stamp_ns = normalized_state_stamp_ns(
            source_stamp_ns=stamp_ns,
            latest_clock_stamp_ns=self._latest_clock_stamp_ns,
            last_published_stamp_ns=self._lidar_filter.last_stamp_ns,
        )
        message.header.stamp.sec, message.header.stamp.nanosec = nanoseconds_to_stamp_fields(normalized_stamp_ns)
        self._republish_monotonic(
            'lidar',
            normalized_stamp_ns,
            message,
            self._lidar_filter,
            self._lidar_publisher.publish,
        )

    def _republish_monotonic(self, stream_label: str, stamp_ns: int, message, stamp_filter: MonotonicStampFilter, publish) -> None:
        if not rclpy.ok():
            return

        last_stamp_ns = stamp_filter.last_stamp_ns
        if last_stamp_ns is None:
            stamp_filter.reset(stamp_ns)
            self._safe_publish(publish, message)
            return

        if stamp_ns > last_stamp_ns:
            stamp_filter.reset(stamp_ns)
            self._safe_publish(publish, message)
            return

        backwards_jump_ns = last_stamp_ns - stamp_ns
        self._warn_drop(
            stream_label,
            f'Dropping stale {stream_label} sample after backward timestamp jump '
            f'({backwards_jump_ns / 1_000_000_000:.3f}s behind latest accepted sample).'
        )

    def _safe_publish(self, publish, message) -> None:
        if not rclpy.ok():
            return

        try:
            publish(message)
        except Exception:
            if rclpy.ok():
                raise

    def _warn_drop(self, stream_label: str, message: str) -> None:
        now_monotonic = monotonic()
        last_warning = self._last_warning_monotonic_by_stream.get(stream_label, 0.0)
        if now_monotonic - last_warning < self._warning_interval_sec:
            return
        self._last_warning_monotonic_by_stream[stream_label] = now_monotonic
        self.get_logger().warning(message)

def resolve_lock_path() -> Path:
    raw_path = os.environ.get('AGRIBOT_SIM_TIME_GUARD_LOCK', '').strip()
    return Path(raw_path) if raw_path else Path(gettempdir()) / 'agribot_sim_time_guard.lock'


def acquire_singleton_lock(lock_path: Path | None = None) -> int:
    resolved_lock_path = lock_path or resolve_lock_path()
    resolved_lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(resolved_lock_path), os.O_CREAT | os.O_RDWR, 0o644)

    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(lock_fd)
        raise SingletonLockError(
            f'another sim_time_guard instance already owns {resolved_lock_path}'
        ) from exc

    os.ftruncate(lock_fd, 0)
    os.write(lock_fd, f'{os.getpid()}\n'.encode())
    return lock_fd


def main(args=None) -> None:
    try:
        lock_fd = acquire_singleton_lock()
    except SingletonLockError as exc:
        print(f'sim_time_guard startup skipped: {exc}', file=sys.stderr)
        return

    rclpy.init(args=args)
    node = SimTimeGuard()
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
        os.close(lock_fd)


if __name__ == '__main__':
    main()
