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
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import JointState


def stamp_to_nanoseconds(sec_value: int, nanosec_value: int) -> int:
    return int(sec_value) * 1_000_000_000 + int(nanosec_value)


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
        self.declare_parameter('warning_interval_sec', 2.0)

        self._warning_interval_sec = max(0.0, float(self.get_parameter('warning_interval_sec').value))
        self._last_warning_monotonic_by_stream: dict[str, float] = {}

        self._clock_filter = MonotonicStampFilter()
        self._odom_filter = MonotonicStampFilter()
        self._joint_state_filter = MonotonicStampFilter()

        clock_input_topic = str(self.get_parameter('clock_input_topic').value)
        clock_output_topic = str(self.get_parameter('clock_output_topic').value)
        odom_input_topic = str(self.get_parameter('odom_input_topic').value)
        odom_output_topic = str(self.get_parameter('odom_output_topic').value)
        joint_states_input_topic = str(self.get_parameter('joint_states_input_topic').value)
        joint_states_output_topic = str(self.get_parameter('joint_states_output_topic').value)

        self._clock_publisher = self.create_publisher(Clock, clock_output_topic, 20)
        self._odom_publisher = self.create_publisher(Odometry, odom_output_topic, 20)
        self._joint_state_publisher = self.create_publisher(JointState, joint_states_output_topic, 20)

        self.create_subscription(Clock, clock_input_topic, self._handle_clock, 20)
        self.create_subscription(Odometry, odom_input_topic, self._handle_odom, 20)
        self.create_subscription(JointState, joint_states_input_topic, self._handle_joint_states, 20)

        self.get_logger().info(
            'sim time guard started. '
            f'clock={clock_input_topic}->{clock_output_topic}, '
            f'odom={odom_input_topic}->{odom_output_topic}, '
            f'joint_states={joint_states_input_topic}->{joint_states_output_topic}'
        )

    def _handle_clock(self, message: Clock) -> None:
        stamp_ns = stamp_to_nanoseconds(message.clock.sec, message.clock.nanosec)
        if self._clock_filter.accept(stamp_ns):
            self._clock_publisher.publish(message)
            return
        self._warn_drop('clock', stamp_ns, self._clock_filter.last_stamp_ns)

    def _handle_odom(self, message: Odometry) -> None:
        stamp_ns = stamp_to_nanoseconds(message.header.stamp.sec, message.header.stamp.nanosec)
        if self._odom_filter.accept(stamp_ns):
            self._odom_publisher.publish(message)
            return
        self._warn_drop('odom', stamp_ns, self._odom_filter.last_stamp_ns)

    def _handle_joint_states(self, message: JointState) -> None:
        stamp_ns = stamp_to_nanoseconds(message.header.stamp.sec, message.header.stamp.nanosec)
        if self._joint_state_filter.accept(stamp_ns):
            self._joint_state_publisher.publish(message)
            return
        self._warn_drop('joint_states', stamp_ns, self._joint_state_filter.last_stamp_ns)

    def _warn_drop(self, stream_label: str, stamp_ns: int, last_stamp_ns: int | None) -> None:
        if last_stamp_ns is None:
            return
        now_monotonic = monotonic()
        last_warning = self._last_warning_monotonic_by_stream.get(stream_label, 0.0)
        if now_monotonic - last_warning < self._warning_interval_sec:
            return
        self._last_warning_monotonic_by_stream[stream_label] = now_monotonic
        delta_sec = max(0.0, (last_stamp_ns - stamp_ns) / 1_000_000_000)
        self.get_logger().warning(
            f'Dropping stale {stream_label} sample after backward timestamp jump '
            f'({delta_sec:.3f}s behind latest accepted sample).'
        )


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
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        os.close(lock_fd)


if __name__ == '__main__':
    main()
