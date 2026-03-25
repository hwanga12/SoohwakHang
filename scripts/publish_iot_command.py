from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from agribot_interfaces.msg import IoTCommand
import rclpy
from rclpy.node import Node


def _load_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding='utf-8'))


def _build_message(node: Node, payload: dict[str, object]) -> IoTCommand:
    message = IoTCommand()
    message.header.stamp = node.get_clock().now().to_msg()
    message.header.frame_id = str(payload.get('frame_id', 'map'))
    message.command_id = str(payload.get('command_id', ''))
    message.zone_id = str(payload.get('zone_id', ''))
    message.device_id = str(payload.get('device_id', ''))
    message.device_type = str(payload.get('device_type', ''))
    message.command_type = str(payload.get('command_type', ''))
    message.target_value = float(payload.get('target_value', 0.0))
    message.unit = str(payload.get('unit', ''))
    message.requires_approval = bool(payload.get('requires_approval', False))
    message.auto_execute = bool(payload.get('auto_execute', True))
    message.requested_by = str(payload.get('requested_by', ''))
    message.reason = str(payload.get('reason', ''))
    return message


def main() -> int:
    parser = argparse.ArgumentParser(description='Publish a single IoTCommand message to ROS.')
    parser.add_argument('--topic', required=True)
    parser.add_argument('--payload-file', required=True)
    args = parser.parse_args()

    payload = _load_payload(Path(args.payload_file))

    rclpy.init()
    node = Node('agribot_iot_command_once_publisher')
    publisher = node.create_publisher(IoTCommand, args.topic, 10)
    try:
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline and publisher.get_subscription_count() == 0:
            rclpy.spin_once(node, timeout_sec=0.1)

        message = _build_message(node, payload)
        publisher.publish(message)
        # Give DDS discovery and the outbound queue a brief chance to flush
        # before tearing the process down.
        rclpy.spin_once(node, timeout_sec=0.2)
        time.sleep(0.1)
        print(
            f'Published IoTCommand {message.command_id} '
            f'to {args.topic} for {message.device_type}:{message.device_id}.'
        )
        return 0
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
