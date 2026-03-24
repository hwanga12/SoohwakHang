from __future__ import annotations

import base64
from datetime import datetime
import os
from pathlib import Path
import uuid

import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import Pose
from agribot_interfaces.msg import PlantObservation
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image

from .backend_client import BackendClient
from .model_runner import Detection, ModelRunner, choose_detection, parse_label_list


_DEFAULT_RUNTIME_RELATIVE_PATH = Path('artifacts/runtime/robot/thin_inference')
_DEFAULT_IGNORED_CLASSES = 'healthy,normal,normal_leaf,healthy_leaf'


class ThinInferenceNode(Node):
    """Run fast local inference, then ask the backend to confirm the disease label."""

    def __init__(self) -> None:
        super().__init__('thin_inference_node')

        repo_root = Path(__file__).resolve().parents[4]
        default_runtime_dir = repo_root / _DEFAULT_RUNTIME_RELATIVE_PATH
        default_model_path = os.environ.get('AGRIBOT_TOMATO_MODEL_PATH', '')

        self.declare_parameter('image_topic', '/agribot/camera/image')
        self.declare_parameter('plant_observation_topic', '/plant_observation')
        self.declare_parameter(
            'backend_confirm_url',
            'http://127.0.0.1:8000/api/v1/inference/confirm',
        )
        self.declare_parameter('zone_id', 'greenhouse_01')
        self.declare_parameter('robot_id', 'agribot')
        self.declare_parameter('model_path', default_model_path)
        self.declare_parameter('imgsz', 640)
        self.declare_parameter('confidence_threshold', 0.35)
        self.declare_parameter('allowed_classes', '')
        self.declare_parameter('ignored_classes', _DEFAULT_IGNORED_CLASSES)
        self.declare_parameter('backend_timeout_sec', 10.0)
        self.declare_parameter('frame_stride', 8)
        self.declare_parameter('cooldown_sec', 4.0)
        self.declare_parameter('crop_padding_ratio', 0.1)
        self.declare_parameter('runtime_dir', str(default_runtime_dir))
        self.declare_parameter('snapshot_format', 'jpg')
        self.declare_parameter('jpeg_quality', 90)
        self.declare_parameter('publish_preliminary_on_backend_error', True)

        image_topic = str(self.get_parameter('image_topic').value)
        plant_observation_topic = str(self.get_parameter('plant_observation_topic').value)
        backend_confirm_url = str(self.get_parameter('backend_confirm_url').value)
        self._zone_id = str(self.get_parameter('zone_id').value)
        self._robot_id = str(self.get_parameter('robot_id').value)
        model_path = str(self.get_parameter('model_path').value).strip() or None
        imgsz = int(self.get_parameter('imgsz').value)
        confidence_threshold = float(self.get_parameter('confidence_threshold').value)
        allowed_classes = parse_label_list(str(self.get_parameter('allowed_classes').value))
        ignored_classes = parse_label_list(str(self.get_parameter('ignored_classes').value))
        backend_timeout_sec = float(self.get_parameter('backend_timeout_sec').value)
        self._frame_stride = max(1, int(self.get_parameter('frame_stride').value))
        self._cooldown_sec = max(0.0, float(self.get_parameter('cooldown_sec').value))
        self._crop_padding_ratio = max(
            0.0,
            float(self.get_parameter('crop_padding_ratio').value),
        )
        self._runtime_dir = Path(str(self.get_parameter('runtime_dir').value)).expanduser()
        self._snapshot_format = _normalize_snapshot_format(
            str(self.get_parameter('snapshot_format').value)
        )
        self._jpeg_quality = max(1, min(100, int(self.get_parameter('jpeg_quality').value)))
        self._publish_preliminary_on_backend_error = bool(
            self.get_parameter('publish_preliminary_on_backend_error').value
        )

        self._runtime_dir.mkdir(parents=True, exist_ok=True)
        self._bridge = CvBridge()
        self._runner = ModelRunner(
            model_path=model_path,
            imgsz=imgsz,
            confidence_threshold=confidence_threshold,
        )
        self._allowed_classes = allowed_classes
        self._ignored_classes = ignored_classes
        self._backend_client = BackendClient(backend_confirm_url, backend_timeout_sec)
        image_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self._publisher = self.create_publisher(
            PlantObservation,
            plant_observation_topic,
            20,
        )
        self._subscription = self.create_subscription(
            Image,
            image_topic,
            self._handle_image,
            image_qos,
        )

        self._frame_counter = 0
        self._busy = False
        self._last_publish_sec = 0.0

        self.get_logger().info(
            'Thin inference node ready. '
            f'image_topic={image_topic}, '
            f'plant_observation_topic={plant_observation_topic}, '
            f'backend_confirm_url={backend_confirm_url}, '
            f'model_path={self._runner.model_path}'
        )

    def _handle_image(self, msg: Image) -> None:
        self._frame_counter += 1
        if self._busy or self._frame_counter % self._frame_stride != 0:
            return

        now_sec = self.get_clock().now().nanoseconds / 1_000_000_000
        if (now_sec - self._last_publish_sec) < self._cooldown_sec:
            return

        self._busy = True
        try:
            self._process_frame(msg)
        except Exception as exc:  # pragma: no cover - runtime guard for ROS callbacks
            self.get_logger().error(f'thin inference callback failed: {exc}')
        finally:
            self._busy = False

    def _process_frame(self, msg: Image) -> None:
        frame = self._bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        detections = self._runner.infer(frame)
        detection = choose_detection(
            detections,
            allowed_classes=self._allowed_classes,
            ignored_classes=self._ignored_classes,
        )
        if detection is None:
            return

        crop = _crop_detection(
            frame,
            detection,
            padding_ratio=self._crop_padding_ratio,
        )
        encoded_bytes = _encode_image(
            crop,
            image_format=self._snapshot_format,
            jpeg_quality=self._jpeg_quality,
        )
        observation_id = str(uuid.uuid4())
        local_image_path = self._persist_snapshot(observation_id, encoded_bytes)

        preliminary_label = detection.label.strip()
        preliminary_confidence = float(detection.confidence)
        confirmation = None
        try:
            confirmation = self._backend_client.confirm_detection(
                {
                    'observation_id': observation_id,
                    'robot_id': self._robot_id,
                    'zone_id': self._zone_id,
                    'frame_id': msg.header.frame_id,
                    'preliminary_label': preliminary_label,
                    'preliminary_confidence': preliminary_confidence,
                    'image_format': self._snapshot_format,
                    'image_base64': base64.b64encode(encoded_bytes).decode('ascii'),
                    'bbox': {
                        'x1': detection.bbox[0],
                        'y1': detection.bbox[1],
                        'x2': detection.bbox[2],
                        'y2': detection.bbox[3],
                    },
                }
            )
            final_label = confirmation.final_label
            final_confidence = confirmation.final_confidence
            image_path = confirmation.image_path or str(local_image_path)
        except RuntimeError as exc:
            if not self._publish_preliminary_on_backend_error:
                self.get_logger().warning(f'backend confirmation skipped: {exc}')
                return
            self.get_logger().warning(
                f'backend confirmation failed, publishing preliminary result instead: {exc}'
            )
            final_label = preliminary_label
            final_confidence = preliminary_confidence
            image_path = str(local_image_path)

        observation = PlantObservation()
        observation.header = msg.header
        observation.observation_id = observation_id
        observation.mission_id = ''
        observation.zone_id = self._zone_id
        observation.plant_id = ''
        observation.fruit_id = ''
        observation.class_name = final_label
        observation.confidence = float(final_confidence)
        observation.health_score = _estimate_health_score(final_label)
        observation.needs_water = False
        observation.ready_to_harvest = _is_ready_to_harvest(final_label)
        observation.growth_stage = ''
        observation.pose = Pose()
        observation.image_path = image_path
        self._publisher.publish(observation)

        self._last_publish_sec = self.get_clock().now().nanoseconds / 1_000_000_000
        self.get_logger().info(
            'Published confirmed plant observation '
            f'label={final_label}, confidence={final_confidence:.3f}, image_path={image_path}'
        )

    def _persist_snapshot(self, observation_id: str, encoded_bytes: bytes) -> Path:
        date_dir = self._runtime_dir / datetime.now().strftime('%Y%m%d')
        date_dir.mkdir(parents=True, exist_ok=True)
        file_path = date_dir / f'{observation_id}.{self._snapshot_format}'
        file_path.write_bytes(encoded_bytes)
        return file_path


def _normalize_snapshot_format(image_format: str) -> str:
    normalized = image_format.strip().lower().lstrip('.')
    if normalized in {'jpg', 'jpeg', 'png'}:
        return 'jpg' if normalized == 'jpeg' else normalized
    return 'jpg'


def _crop_detection(
    image,
    detection: Detection,
    *,
    padding_ratio: float,
):
    image_height, image_width = image.shape[:2]
    x1, y1, x2, y2 = detection.bbox
    box_width = max(1.0, x2 - x1)
    box_height = max(1.0, y2 - y1)
    pad_x = int(box_width * padding_ratio)
    pad_y = int(box_height * padding_ratio)

    left = max(0, int(x1) - pad_x)
    top = max(0, int(y1) - pad_y)
    right = min(image_width, int(x2) + pad_x)
    bottom = min(image_height, int(y2) + pad_y)

    if left >= right or top >= bottom:
        return image
    return image[top:bottom, left:right]


def _encode_image(
    image,
    *,
    image_format: str,
    jpeg_quality: int,
) -> bytes:
    extension = f'.{image_format}'
    encode_args = []
    if image_format == 'jpg':
        encode_args = [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)]
    success, encoded = cv2.imencode(extension, image, encode_args)
    if not success:
        raise RuntimeError('failed to encode crop image for backend confirmation')
    return encoded.tobytes()


def _estimate_health_score(label: str) -> float:
    normalized = label.strip().lower()
    if not normalized:
        return 0.5
    if 'healthy' in normalized or 'normal' in normalized:
        return 1.0
    if 'disease' in normalized or 'mold' in normalized or 'rot' in normalized:
        return 0.0
    return 0.25


def _is_ready_to_harvest(label: str) -> bool:
    normalized = label.strip().lower()
    return 'ripe' in normalized and 'tomato' in normalized and 'unripe' not in normalized


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ThinInferenceNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
