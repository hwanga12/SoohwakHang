# 이 모듈은 통합 실행과 런치 조율 패키지에서 mission bridge executor 절차를 담당한다.
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from agribot_interfaces.msg import (
    MissionBridgeStatus as MissionBridgeStatusMsg,
    MissionRequest as MissionRequestMsg,
)
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from .mission_bridge_contract import (
    MissionBridgeValidationError,
    MissionRequest,
    harvest_bridge_status_from_payload,
    harvest_status_refers_to_request,
    parse_mission_request_payload,
    parse_status_payload,
    patrol_bridge_status_from_payload,
)
from .runtime_snapshot_service import (
    build_mission_bridge_status_payload,
    mission_request_path,
    mission_status_path,
    mission_status_record_path,
    read_json_object,
    runtime_dir_from_env,
    write_json_atomic,
)
from .runtime_message_contract import (
    mission_bridge_status_message_from_payload,
    mission_request_payload_from_message,
)
from .protocol_qos import protocol_qos_profile

TERMINAL_STATUSES = {'succeeded', 'failed', 'canceled'}


@dataclass
class ActiveMissionContext:
    # 진행 중 미션 context 한 건을 명확한 필드 구조로 담기 위한 데이터 클래스다.
    request: MissionRequest
    received_at: str
    started_at: str | None = None
    observed_runtime_progress: bool = False


def _iso_now() -> str:
    # iso now 정보를 계산해 반환한다.
    return datetime.now(timezone.utc).isoformat()


def _extract_string(payload: dict[str, Any], key: str, *, default: str = '') -> str:
    # 원본 데이터에서 string만 골라 추출한다.
    raw_value = payload.get(key, default)
    return str(raw_value).strip() if raw_value is not None else default


class MissionBridgeExecutor(Node):
    # 미션 브리지 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    def __init__(self) -> None:
        # MissionBridgeExecutor 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__('mission_bridge_executor')

        if not self.has_parameter('use_sim_time'):
            self.declare_parameter('use_sim_time', True)
        self.declare_parameter('robot_id', 'AGR-02')
        self.declare_parameter('command_poll_period_sec', 0.25)
        self.declare_parameter('processed_request_history_size', 64)
        self.declare_parameter('request_topic', '/mission/requests')
        self.declare_parameter('bridge_status_topic', '/mission/bridge_status')
        self.declare_parameter('patrol_start_service', '/patrol/start')
        self.declare_parameter('patrol_status_topic', '/patrol/status')
        self.declare_parameter('harvest_request_topic', '/harvest/request')
        self.declare_parameter('harvest_status_topic', '/harvest_route/status')
        self.declare_parameter('patrol_service_wait_sec', 1.5)

        self._runtime_dir = runtime_dir_from_env()
        self._request_path = mission_request_path(self._runtime_dir)
        self._status_path = mission_status_path(self._runtime_dir)
        self._default_robot_id = str(self.get_parameter('robot_id').value)
        self._patrol_service_wait_sec = float(self.get_parameter('patrol_service_wait_sec').value)
        self._request_topic = str(self.get_parameter('request_topic').value)
        self._bridge_status_topic = str(self.get_parameter('bridge_status_topic').value)
        history_size = max(8, int(self.get_parameter('processed_request_history_size').value))

        self._request_subscription = self.create_subscription(
            MissionRequestMsg,
            self._request_topic,
            self._handle_request_topic,
            protocol_qos_profile(self._request_topic, default_depth=20),
        )
        self._bridge_status_publisher = self.create_publisher(
            MissionBridgeStatusMsg,
            self._bridge_status_topic,
            protocol_qos_profile(self._bridge_status_topic, default_depth=20),
        )
        self._patrol_start_client = self.create_client(
            Trigger,
            str(self.get_parameter('patrol_start_service').value),
        )
        self._harvest_request_publisher = self.create_publisher(
            String,
            str(self.get_parameter('harvest_request_topic').value),
            10,
        )
        self._patrol_status_subscription = self.create_subscription(
            String,
            str(self.get_parameter('patrol_status_topic').value),
            self._handle_patrol_status,
            20,
        )
        self._harvest_status_subscription = self.create_subscription(
            String,
            str(self.get_parameter('harvest_status_topic').value),
            self._handle_harvest_status,
            20,
        )

        self._processed_command_ids: set[str] = set()
        self._processed_command_order: deque[str] = deque(maxlen=history_size)
        self._active_context: ActiveMissionContext | None = None
        self._service_future = None
        self._last_seen_request_signature: tuple[int, int] | None = None
        self._last_status_payload: dict[str, Any] | None = None

        self._recover_previous_status()
        poll_period = float(self.get_parameter('command_poll_period_sec').value)
        self.create_timer(poll_period, self._poll_request_file)

        self.get_logger().info(
            'mission bridge executor started. '
            f'request_path={self._request_path}, '
            f'status_path={self._status_path}, '
            f'request_topic={self._request_topic}, '
            f'bridge_status_topic={self._bridge_status_topic}'
        )

    def _recover_previous_status(self) -> None:
        # recover previous 상태 정보를 계산해 반환한다.
        if not self._status_path.exists():
            return

        try:
            payload = read_json_object(self._status_path)
        except (OSError, ValueError) as exc:
            self.get_logger().warning(f'기존 mission status 파일을 읽지 못했습니다: {exc}')
            return

        self._last_status_payload = payload
        command_id = _extract_string(payload, 'command_id')
        status = _extract_string(payload, 'status').lower()
        if not command_id:
            return

        if status in TERMINAL_STATUSES:
            self._remember_processed_command_id(command_id)
            return

        repaired_payload = build_mission_bridge_status_payload(
            mission_id=_extract_string(payload, 'mission_id') or command_id,
            command_id=command_id,
            request_type=_extract_string(payload, 'request_type'),
            robot_id=_extract_string(payload, 'robot_id', default=self._default_robot_id) or self._default_robot_id,
            requested_by=_extract_string(payload, 'requested_by'),
            status='failed',
            message='이전 mission bridge 세션이 완료 전에 종료되었습니다. 새 command_id로 다시 요청하세요.',
            error='executor_restart',
            zone_ids=payload.get('zone_ids') if isinstance(payload.get('zone_ids'), list) else None,
            loop_count=payload.get('loop_count') if isinstance(payload.get('loop_count'), int) else None,
            patrol_mode=_extract_string(payload, 'patrol_mode') or None,
            plant_id=_extract_string(payload, 'plant_id') or None,
            fruit_id=_extract_string(payload, 'fruit_id') or None,
            tomato_id=_extract_string(payload, 'tomato_id') or None,
            received_at=_extract_string(payload, 'received_at') or None,
            started_at=_extract_string(payload, 'started_at') or None,
            completed_at=_iso_now(),
        )
        self._write_status(repaired_payload)
        self._remember_processed_command_id(command_id)

    def _remember_processed_command_id(self, command_id: str) -> None:
        # remember processed 명령 id 정보를 계산해 반환한다.
        if command_id in self._processed_command_ids:
            return

        if len(self._processed_command_order) == self._processed_command_order.maxlen:
            oldest = self._processed_command_order.popleft()
            self._processed_command_ids.discard(oldest)

        self._processed_command_order.append(command_id)
        self._processed_command_ids.add(command_id)

    def _request_file_signature(self, path: Path) -> tuple[int, int]:
        # request file signature 정보를 계산해 반환한다.
        stat_result = path.stat()
        return (int(stat_result.st_mtime_ns), int(stat_result.st_size))

    def _build_status_payload(
        self,
        context: ActiveMissionContext,
        status: str,
        message: str,
        *,
        error: str | None = None,
        result: str | None = None,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        # 상태 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
        request = context.request
        return build_mission_bridge_status_payload(
            mission_id=request.mission_id,
            command_id=request.command_id,
            request_type=request.request_type,
            robot_id=request.robot_id,
            requested_by=request.requested_by,
            status=status,
            message=message,
            error=error,
            result=result,
            zone_ids=list(request.zone_ids),
            loop_count=request.loop_count,
            patrol_mode=request.patrol_mode,
            plant_id=request.plant_id,
            fruit_id=request.fruit_id,
            tomato_id=request.tomato_id,
            received_at=context.received_at,
            started_at=context.started_at,
            completed_at=completed_at,
        )

    def _build_non_active_status_payload(
        self,
        request: MissionRequest,
        status: str,
        message: str,
        *,
        error: str | None = None,
        result: str | None = None,
        completed_at: str | None = None,
    ) -> dict[str, Any]:
        # NON active 상태 payload를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
        return build_mission_bridge_status_payload(
            mission_id=request.mission_id,
            command_id=request.command_id,
            request_type=request.request_type,
            robot_id=request.robot_id,
            requested_by=request.requested_by,
            status=status,
            message=message,
            error=error,
            result=result,
            zone_ids=list(request.zone_ids),
            loop_count=request.loop_count,
            patrol_mode=request.patrol_mode,
            plant_id=request.plant_id,
            fruit_id=request.fruit_id,
            tomato_id=request.tomato_id,
            received_at=_iso_now(),
            completed_at=completed_at,
        )

    def _write_status(self, payload: dict[str, Any]) -> None:
        # 상태를 파일이나 저장소에 기록한다.
        write_json_atomic(self._status_path, payload)
        mission_identifier = str(payload.get('mission_id') or payload.get('command_id') or '').strip()
        if mission_identifier:
            write_json_atomic(
                mission_status_record_path(mission_identifier, self._runtime_dir),
                payload,
            )
        self._last_status_payload = payload
        self._bridge_status_publisher.publish(
            mission_bridge_status_message_from_payload(
                payload,
                stamp=self.get_clock().now().to_msg(),
            )
        )

    def _finish_active_request(
        self,
        status: str,
        message: str,
        *,
        error: str | None = None,
        result: str | None = None,
    ) -> None:
        # finish active request 정보를 계산해 반환한다.
        context = self._active_context
        if context is None:
            return

        payload = self._build_status_payload(
            context,
            status,
            message,
            error=error,
            result=result,
            completed_at=_iso_now(),
        )
        self._write_status(payload)
        self._remember_processed_command_id(context.request.command_id)
        self._active_context = None
        self._service_future = None

    def _handle_request_topic(self, message: MissionRequestMsg) -> None:
        # Handle a typed mission request published directly onto the ROS graph.
        self._process_raw_request_payload(
            mission_request_payload_from_message(message),
            source='topic',
        )

    def _poll_request_file(self) -> None:
        # poll request file 정보를 계산해 반환한다.
        if not self._request_path.exists():
            return

        signature = self._request_file_signature(self._request_path)
        if signature == self._last_seen_request_signature:
            return
        self._last_seen_request_signature = signature

        try:
            raw_payload = read_json_object(self._request_path)
        except (OSError, ValueError) as exc:
            failed_payload = build_mission_bridge_status_payload(
                mission_id=None,
                command_id='unknown-command',
                request_type='unknown',
                robot_id=self._default_robot_id,
                status='failed',
                message=f'mission request 파일을 해석하지 못했습니다: {exc}',
                error='invalid_mission_request',
                completed_at=_iso_now(),
            )
            self._write_status(failed_payload)
            return

        self._process_raw_request_payload(raw_payload, source='file')

    def _process_raw_request_payload(self, raw_payload: dict[str, Any], *, source: str) -> None:
        # Process a request payload from either the legacy file bridge or the direct ROS topic.
        try:
            request = parse_mission_request_payload(
                raw_payload,
                default_robot_id=self._default_robot_id,
            )
        except MissionBridgeValidationError as exc:
            failed_payload = build_mission_bridge_status_payload(
                mission_id=None,
                command_id=_extract_string(raw_payload, 'command_id') or 'unknown-command',
                request_type=(
                    _extract_string(raw_payload, 'request_type')
                    or _extract_string(raw_payload, 'command_type')
                    or 'unknown'
                ),
                robot_id=_extract_string(raw_payload, 'robot_id', default=self._default_robot_id) or self._default_robot_id,
                requested_by=_extract_string(raw_payload, 'requested_by'),
                status='failed',
                message=str(exc),
                error='invalid_mission_request',
                completed_at=_iso_now(),
            )
            self._write_status(failed_payload)
            return

        if request.command_id in self._processed_command_ids:
            self._write_status(
                self._build_non_active_status_payload(
                    request,
                    'failed',
                    '이미 처리된 command_id 입니다. 새 command_id로 다시 요청하세요.',
                    error='duplicate_command_id',
                    completed_at=_iso_now(),
                )
            )
            return

        if self._active_context is not None:
            self._remember_processed_command_id(request.command_id)
            self._write_status(
                self._build_non_active_status_payload(
                    request,
                    'failed',
                    (
                        f'{self._active_context.request.request_type} 가 아직 진행 중이라 '
                        '새 operator mission 요청을 수락할 수 없습니다.'
                    ),
                    error='mission_in_progress',
                    completed_at=_iso_now(),
                )
            )
            return

        if source == 'topic':
            self.get_logger().info(
                f'직접 ROS 미션 요청을 수신했습니다: mission_id={request.mission_id}, '
                f'request_type={request.request_type}'
            )
        if request.request_type == 'start_patrol':
            self._start_patrol_request(request)
            return

        self._start_harvest_request(request)

    def _start_patrol_request(self, request: MissionRequest) -> None:
        # patrol 요청 데이터 실행 흐름을 시작하거나 마무리한다.
        if not self._patrol_start_client.wait_for_service(timeout_sec=self._patrol_service_wait_sec):
            self._remember_processed_command_id(request.command_id)
            self._write_status(
                self._build_non_active_status_payload(
                    request,
                    'failed',
                    'patrol/start service 를 찾지 못했습니다.',
                    error='patrol_service_unavailable',
                    completed_at=_iso_now(),
                )
            )
            return

        context = ActiveMissionContext(
            request=request,
            received_at=_iso_now(),
        )
        self._active_context = context
        self._write_status(
            self._build_status_payload(
                context,
                'pending',
                'start_patrol 요청을 읽었습니다. patrol/start service 를 호출합니다.',
                result='accepted',
            )
        )

        self._service_future = self._patrol_start_client.call_async(Trigger.Request())
        self._service_future.add_done_callback(self._handle_patrol_start_response)

    def _handle_patrol_start_response(self, future: Any) -> None:
        # handle patrol start response 정보를 계산해 반환한다.
        context = self._active_context
        if context is None or context.request.request_type != 'start_patrol':
            return

        try:
            response = future.result()
        except Exception as exc:
            self._finish_active_request(
                'failed',
                f'patrol/start service 호출이 실패했습니다: {exc}',
                error='patrol_service_call_failed',
            )
            return

        if not response.success:
            self._finish_active_request(
                'failed',
                response.message or 'patrol/start service 가 요청을 거부했습니다.',
                error='patrol_start_rejected',
            )
            return

        context.started_at = _iso_now()
        self._write_status(
            self._build_status_payload(
                context,
                'running',
                response.message or 'Patrol start 요청이 수락되었습니다.',
                result='service_started',
            )
        )

    def _start_harvest_request(self, request: MissionRequest) -> None:
        # harvest 요청 데이터 실행 흐름을 시작하거나 마무리한다.
        context = ActiveMissionContext(
            request=request,
            received_at=_iso_now(),
        )
        self._active_context = context
        self._write_status(
            self._build_status_payload(
                context,
                'pending',
                'harvest/request 토픽으로 harvest target 을 발행했습니다. harvest_route/status 반영을 기다립니다.',
                result='published',
            )
        )
        harvest_request_payload = {
            'mission_id': request.mission_id,
            'plant_id': request.plant_id,
            'fruit_id': request.fruit_id,
            'tomato_id': request.effective_tomato_id,
            'requested_by': request.requested_by,
            'trigger': 'mission_bridge',
        }
        if request.inspect_waypoint_id:
            harvest_request_payload['inspect_waypoint_id'] = request.inspect_waypoint_id
        if request.inspect_waypoint_ids:
            harvest_request_payload['inspect_waypoint_ids'] = list(request.inspect_waypoint_ids)
        self._harvest_request_publisher.publish(
            String(data=json.dumps(harvest_request_payload, ensure_ascii=False))
        )

    def _handle_patrol_status(self, msg: String) -> None:
        # handle patrol 상태 정보를 계산해 반환한다.
        context = self._active_context
        if context is None or context.request.request_type != 'start_patrol':
            return

        payload = parse_status_payload(msg.data)
        if payload is None:
            self.get_logger().warning('유효하지 않은 patrol status payload를 무시합니다.')
            return

        mapped_status = patrol_bridge_status_from_payload(payload)
        if mapped_status is None:
            return

        status, message, error, is_terminal = mapped_status
        if status == 'running':
            if context.started_at is None:
                context.started_at = _iso_now()
            context.observed_runtime_progress = True
            self._write_status(
                self._build_status_payload(
                    context,
                    status,
                    message,
                    error=error,
                    result='runtime_observed',
                )
            )
            return

        self._finish_active_request(
            status,
            message,
            error=error,
            result='runtime_completed' if is_terminal else 'runtime_observed',
        )

    def _handle_harvest_status(self, msg: String) -> None:
        # handle 수확 상태 정보를 계산해 반환한다.
        context = self._active_context
        if context is None or context.request.request_type != 'harvest_target':
            return

        payload = parse_status_payload(msg.data)
        if payload is None:
            self.get_logger().warning('유효하지 않은 harvest route status payload를 무시합니다.')
            return

        request = context.request
        tomato_id = request.effective_tomato_id
        refers_to_request = harvest_status_refers_to_request(payload, tomato_id)
        mapped_status = harvest_bridge_status_from_payload(payload)
        if mapped_status is None:
            return

        status, message, error, is_terminal = mapped_status
        if not refers_to_request and not (context.observed_runtime_progress and is_terminal):
            return

        if status == 'running':
            if context.started_at is None:
                context.started_at = _iso_now()
            context.observed_runtime_progress = True
            self._write_status(
                self._build_status_payload(
                    context,
                    status,
                    message,
                    error=error,
                    result='runtime_observed',
                )
            )
            return

        self._finish_active_request(
            status,
            message,
            error=error,
            result='runtime_completed' if is_terminal else 'runtime_observed',
        )


def main(args: list[str] | None = None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = MissionBridgeExecutor()
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
