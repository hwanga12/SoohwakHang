# 이 모듈은 IoT 장치 연동 패키지에서 environment sensor node 장치 흐름을 담당한다.
from __future__ import annotations

from pathlib import Path
import time

from agribot_interfaces.msg import EnvironmentData
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from .device_mapping import get_default_iot_devices_path, load_iot_device_catalog
from .environment_sensor_profile import generate_environment_sample


class EnvironmentSensorNode(Node):
    # ROS 2 실행 환경에서 environment sensor 흐름을 담당하는 노드 클래스를 정의한다.

    def __init__(self) -> None:
        # EnvironmentSensorNode 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__('environment_sensor_node')
        self.declare_parameter('iot_devices_file', str(get_default_iot_devices_path()))
        self.declare_parameter('environment_topic', '/environment_data')
        self.declare_parameter('zone_id_filter', '')
        self.declare_parameter('publish_hz', 1.0)
        self.declare_parameter('log_every_n', 5)

        catalog_path = Path(str(self.get_parameter('iot_devices_file').value)).expanduser()
        if not catalog_path.is_absolute():
            catalog_path = get_default_iot_devices_path().parent / catalog_path
        self._catalog = load_iot_device_catalog(catalog_path)
        self._environment_topic = str(self.get_parameter('environment_topic').value)
        self._zone_id_filter = str(self.get_parameter('zone_id_filter').value).strip()
        self._publish_hz = max(0.1, float(self.get_parameter('publish_hz').value))
        self._log_every_n = max(1, int(self.get_parameter('log_every_n').value))

        self._publisher = self.create_publisher(EnvironmentData, self._environment_topic, 20)
        self._started_at = time.monotonic()
        self._publish_count = 0
        self._timer = self.create_timer(1.0 / self._publish_hz, self._publish_samples)

        self.get_logger().info(
            'Environment sensor node ready. '
            f'iot_devices_file={catalog_path}, '
            f'environment_topic={self._environment_topic}, '
            f'zone_filter={self._zone_id_filter or "ALL"}, '
            f'publish_hz={self._publish_hz:.2f}'
        )

    def _publish_samples(self) -> None:
        # samples를 외부 시스템이나 다음 처리 단계로 전달한다.
        elapsed_sec = time.monotonic() - self._started_at
        for zone in self._catalog.zones.values():
            if self._zone_id_filter and zone.zone_id != self._zone_id_filter:
                continue

            sample = generate_environment_sample(
                zone.zone_id,
                zone.sensor_profile,
                elapsed_sec=elapsed_sec,
            )
            message = EnvironmentData()
            message.zone_id = sample.zone_id
            message.temperature = float(sample.temperature)
            message.humidity = float(sample.humidity)
            message.soil_moisture = float(sample.soil_moisture)
            message.light_level = float(sample.light_level)
            message.co2_level = float(sample.co2_level)
            self._publisher.publish(message)

            if self._publish_count % self._log_every_n == 0:
                self.get_logger().info(
                    'Environment sample published: '
                    f'zone={sample.zone_id}, '
                    f'temperature={sample.temperature:.1f}C, '
                    f'humidity={sample.humidity:.1f}%, '
                    f'soil_moisture={sample.soil_moisture:.1f}%, '
                    f'light={sample.light_level:.0f}lux, '
                    f'co2={sample.co2_level:.0f}ppm'
                )
        self._publish_count += 1


def main(args=None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = EnvironmentSensorNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
