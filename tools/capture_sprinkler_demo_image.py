#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Image


class _CaptureNode(Node):
    def __init__(self, *, topic: str, output_path: Path, timeout_sec: float) -> None:
        super().__init__("sprinkler_demo_capture_once")
        self._bridge = CvBridge()
        self._output_path = output_path
        self._deadline = time.monotonic() + timeout_sec
        self.timed_out = False
        self.saved = False
        self.create_subscription(Image, topic, self._handle_image, 10)
        self.create_timer(0.5, self._handle_timeout)

    def _handle_image(self, msg: Image) -> None:
        frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(self._output_path), frame):
            raise RuntimeError(f"Failed to write capture to {self._output_path}")
        self.saved = True
        self.get_logger().info(f"Saved sprinkler capture to {self._output_path}")

    def _handle_timeout(self) -> None:
        if self.saved:
            return
        if time.monotonic() > self._deadline:
            self.timed_out = True
            self.get_logger().error("Timed out waiting for Gazebo camera frame.")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _gz_binary() -> str:
    candidate = Path("/opt/ros/jazzy/opt/gz_tools_vendor/bin/gz")
    if candidate.exists():
        return str(candidate)
    resolved = shutil.which("gz")
    if resolved:
        return resolved
    raise FileNotFoundError("gz executable not found.")


def _ros2_binary() -> str:
    resolved = shutil.which("ros2")
    if resolved:
        return resolved
    raise FileNotFoundError("ros2 executable not found. Source the ROS 2 environment first.")


def _world_text(mesh_uri: str, camera_pose: str, topic: str, width: int, height: int) -> str:
    return f"""<?xml version="1.0" ?>
<sdf version="1.9">
  <world name="sprinkler_capture">
    <gravity>0 0 -9.8</gravity>
    <scene>
      <ambient>0.8 0.8 0.8 1</ambient>
      <background>0.95 0.95 0.95 1</background>
    </scene>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>
    <light name="sun" type="directional">
      <pose>0 0 10 0 0 0</pose>
      <diffuse>1 1 1 1</diffuse>
      <specular>0.3 0.3 0.3 1</specular>
      <direction>-0.5 0.2 -1</direction>
    </light>
    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry>
            <plane>
              <normal>0 0 1</normal>
              <size>5 5</size>
            </plane>
          </geometry>
        </collision>
        <visual name="visual">
          <geometry>
            <plane>
              <normal>0 0 1</normal>
              <size>5 5</size>
            </plane>
          </geometry>
          <material>
            <ambient>0.92 0.92 0.92 1</ambient>
            <diffuse>0.92 0.92 0.92 1</diffuse>
          </material>
        </visual>
      </link>
    </model>
    <model name="sprinkler_subject">
      <static>true</static>
      <link name="link">
        <pose>0 0 0 1.5708 0 0</pose>
        <visual name="visual">
          <geometry>
            <mesh>
              <uri>{mesh_uri}</uri>
              <scale>0.4 0.4 0.4</scale>
            </mesh>
          </geometry>
        </visual>
      </link>
    </model>
    <model name="capture_camera">
      <static>true</static>
      <pose>{camera_pose}</pose>
      <link name="link">
        <sensor name="sprinkler_cam" type="camera">
          <always_on>1</always_on>
          <update_rate>5</update_rate>
          <visualize>false</visualize>
          <topic>{topic}</topic>
          <camera>
            <horizontal_fov>1.1</horizontal_fov>
            <image>
              <width>{width}</width>
              <height>{height}</height>
              <format>R8G8B8</format>
            </image>
            <clip>
              <near>0.05</near>
              <far>20</far>
            </clip>
          </camera>
        </sensor>
      </link>
    </model>
  </world>
</sdf>
"""


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def capture_sprinkler_image(
    *,
    output_path: Path,
    camera_pose: str,
    topic: str,
    startup_delay_sec: float,
    timeout_sec: float,
    width: int,
    height: int,
) -> None:
    repo_root = _repo_root()
    mesh_path = repo_root / "agribot_ws" / "src" / "agribot_description" / "models" / "sprinkler" / "meshes" / "basic_sprinkler.glb"
    if not mesh_path.exists():
        raise FileNotFoundError(f"Sprinkler mesh not found: {mesh_path}")

    gz_process: subprocess.Popen[bytes] | None = None
    bridge_process: subprocess.Popen[bytes] | None = None
    temp_dir = Path(tempfile.mkdtemp(prefix="sprinkler-capture-"))

    try:
        world_path = temp_dir / "sprinkler_capture.sdf"
        world_path.write_text(
            _world_text(
                mesh_uri=mesh_path.as_uri(),
                camera_pose=camera_pose,
                topic=topic,
                width=width,
                height=height,
            ),
            encoding="utf-8",
        )

        gz_process = subprocess.Popen(
            [_gz_binary(), "sim", "-s", "-r", "--headless-rendering", str(world_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
        time.sleep(startup_delay_sec)

        bridge_process = subprocess.Popen(
            [
                _ros2_binary(),
                "run",
                "ros_gz_bridge",
                "parameter_bridge",
                f"{topic}@sensor_msgs/msg/Image@gz.msgs.Image",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,
        )
        time.sleep(1.5)

        rclpy.init()
        node = _CaptureNode(topic=topic, output_path=output_path, timeout_sec=timeout_sec)
        executor = SingleThreadedExecutor()
        executor.add_node(node)
        try:
            while rclpy.ok() and not node.saved:
                executor.spin_once(timeout_sec=0.5)
                if node.timed_out:
                    break
        finally:
            executor.remove_node(node)
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()

        if node.timed_out:
            raise TimeoutError("Timed out waiting for Gazebo camera frame.")
        if not output_path.exists():
            raise RuntimeError(f"Capture finished but file is missing: {output_path}")
    finally:
        if bridge_process is not None and bridge_process.poll() is None:
            os.killpg(os.getpgid(bridge_process.pid), signal.SIGTERM)
            _terminate(bridge_process)
        if gz_process is not None and gz_process.poll() is None:
            os.killpg(os.getpgid(gz_process.pid), signal.SIGTERM)
            _terminate(gz_process)
        shutil.rmtree(temp_dir, ignore_errors=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a Gazebo-rendered sprinkler image for the frontend demo UI.")
    parser.add_argument(
        "--output",
        default=str(_repo_root() / "frontend" / "public" / "mock-images" / "sprinkler-gazebo.jpg"),
        help="Output image path.",
    )
    parser.add_argument(
        "--camera-pose",
        default="0.8 -0.6 0.45 0 0.34 2.50",
        help="Gazebo camera pose: x y z roll pitch yaw",
    )
    parser.add_argument("--topic", default="/sprinkler_cam", help="Gazebo / ROS topic name.")
    parser.add_argument("--startup-delay-sec", type=float, default=5.0)
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    capture_sprinkler_image(
        output_path=Path(args.output).expanduser().resolve(),
        camera_pose=args.camera_pose,
        topic=args.topic,
        startup_delay_sec=args.startup_delay_sec,
        timeout_sec=args.timeout_sec,
        width=args.width,
        height=args.height,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
