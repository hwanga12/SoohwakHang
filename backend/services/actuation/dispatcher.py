# 이 모듈은 백엔드 장치 제어 영역에서 장치 제어 요청을 실제 실행 계획으로 분배한다.
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import uuid

from services.actuation.schemas import ActuationDispatchResult, DiseaseTreatmentPlan


@dataclass(frozen=True)
class _IoTCommandPayload:
    # IO T 명령 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    command_id: str
    zone_id: str
    device_id: str
    device_type: str
    command_type: str
    target_value: float
    unit: str
    requires_approval: bool
    auto_execute: bool
    requested_by: str
    reason: str
    frame_id: str = 'map'


class TreatmentCommandDispatcher:
    # 처치 명령 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.

    def __init__(self) -> None:
        # TreatmentCommandDispatcher 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        repo_root = Path(__file__).resolve().parents[3]
        self._repo_root = repo_root
        self._ros_setup_script = Path(
            os.environ.get('AGRIBOT_ROS_SETUP_SCRIPT', '/opt/ros/jazzy/setup.bash')
        ).expanduser()
        self._workspace_setup_script = Path(
            os.environ.get(
                'AGRIBOT_WS_SETUP_SCRIPT',
                str(repo_root / 'agribot_ws' / 'install' / 'setup.bash'),
            )
        ).expanduser()
        self._env_setup_script = Path(
            os.environ.get(
                'AGRIBOT_ENV_SETUP_SCRIPT',
                str(repo_root / 'scripts' / 'agribot_env.sh'),
            )
        ).expanduser()
        self._publisher_script = Path(
            os.environ.get(
                'AGRIBOT_IOT_COMMAND_PUBLISHER',
                str(repo_root / 'scripts' / 'publish_iot_command.py'),
            )
        ).expanduser()
        self._manual_command_topic = os.environ.get(
            'AGRIBOT_IOT_MANUAL_COMMAND_TOPIC',
            '/iot/commands/manual',
        ).strip() or '/iot/commands/manual'
        self._automatic_command_topic = os.environ.get(
            'AGRIBOT_IOT_AUTOMATIC_COMMAND_TOPIC',
            '/iot/commands/auto',
        ).strip() or '/iot/commands/auto'
        self._dispatch_command_topic = os.environ.get(
            'AGRIBOT_IOT_DISPATCH_COMMAND_TOPIC',
            '/iot/commands/dispatch',
        ).strip() or '/iot/commands/dispatch'
        self._dispatch_timeout_sec = max(
            1.0,
            float(os.environ.get('AGRIBOT_TREATMENT_DISPATCH_TIMEOUT_SEC', '10.0')),
        )
        self._dispatch_min_subscribers = max(
            1,
            int(os.environ.get('AGRIBOT_TREATMENT_DISPATCH_MIN_SUBSCRIBERS', '1')),
        )
        self._manual_min_subscribers = max(
            1,
            int(os.environ.get('AGRIBOT_MANUAL_COMMAND_MIN_SUBSCRIBERS', '1')),
        )
        self._default_requested_by = (
            os.environ.get('AGRIBOT_TREATMENT_REQUESTED_BY', 'backend:treatment_rule_engine').strip()
            or 'backend:treatment_rule_engine'
        )

    def dispatch_plan(
        self,
        treatment_plan: DiseaseTreatmentPlan,
        *,
        observation_id: str = '',
        requested_by: str = '',
        auto_execute: bool = True,
    ) -> ActuationDispatchResult:
        # 계획를 외부 시스템이나 다음 처리 단계로 전달한다.
        if not auto_execute:
            return ActuationDispatchResult(
                dispatched=False,
                status='skipped_auto_execute',
                detail_message='Auto execution disabled for this request.',
            )

        if not treatment_plan.action_required:
            return ActuationDispatchResult(
                dispatched=False,
                status='no_action',
                detail_message='Treatment plan does not require sprinkler actuation.',
            )

        if treatment_plan.status != 'ready':
            return ActuationDispatchResult(
                dispatched=False,
                status=treatment_plan.status,
                detail_message=treatment_plan.reason,
            )

        if treatment_plan.selected_sprinkler is None or treatment_plan.command_payload is None:
            return ActuationDispatchResult(
                dispatched=False,
                status='invalid_plan',
                detail_message='Treatment plan is missing sprinkler selection or command payload.',
            )

        validation_error = self._validate_runtime(topic=self._automatic_command_topic)
        if validation_error is not None:
            return validation_error

        command_id = observation_id.strip() or str(uuid.uuid4())
        command = _IoTCommandPayload(
            command_id=command_id,
            zone_id=treatment_plan.selected_sprinkler.zone_id,
            device_id=treatment_plan.selected_sprinkler.device_id,
            device_type=str(treatment_plan.command_payload.get('device_type', 'sprinkler')),
            command_type=str(treatment_plan.command_payload.get('command_type', '')),
            target_value=float(treatment_plan.command_payload.get('target_value', 0.0)),
            unit=str(treatment_plan.command_payload.get('unit', 'sec')),
            requires_approval=False,
            auto_execute=True,
            requested_by=requested_by.strip() or self._default_requested_by,
            reason=_build_reason_text(treatment_plan, observation_id=command_id),
        )
        return self._publish_command(
            command,
            topic=self._automatic_command_topic,
            min_subscribers=self._dispatch_min_subscribers,
        )

    def dispatch_manual_command(
        self,
        *,
        command_id: str,
        zone_id: str,
        device_id: str,
        device_type: str,
        command_type: str,
        target_value: float,
        unit: str,
        requested_by: str,
        reason: str = '',
        auto_execute: bool = True,
        requires_approval: bool = False,
    ) -> ActuationDispatchResult:
        # manual 명령를 외부 시스템이나 다음 처리 단계로 전달한다.
        normalized_device_type = device_type.strip().lower()
        if normalized_device_type == 'sprinkler':
            topic = self._dispatch_command_topic
            min_subscribers = self._dispatch_min_subscribers
        else:
            topic = self._manual_command_topic
            min_subscribers = self._manual_min_subscribers

        validation_error = self._validate_runtime(topic=topic)
        if validation_error is not None:
            return validation_error

        command = _IoTCommandPayload(
            command_id=command_id.strip() or str(uuid.uuid4()),
            zone_id=zone_id.strip(),
            device_id=device_id.strip(),
            device_type=device_type.strip(),
            command_type=command_type.strip(),
            target_value=float(target_value),
            unit=unit.strip(),
            requires_approval=bool(requires_approval),
            auto_execute=bool(auto_execute),
            requested_by=requested_by.strip() or self._default_requested_by,
            reason=reason.strip(),
        )
        return self._publish_command(
            command,
            topic=topic,
            min_subscribers=min_subscribers,
        )

    def _validate_runtime(self, *, topic: str) -> ActuationDispatchResult | None:
        # 런타임 데이터가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
        if not self._env_setup_script.exists():
            return ActuationDispatchResult(
                dispatched=False,
                status='env_setup_missing',
                method='ros_topic_pub_subprocess',
                topic=topic,
                detail_message=f'Environment setup script not found: {self._env_setup_script}',
            )
        if not self._ros_setup_script.exists():
            return ActuationDispatchResult(
                dispatched=False,
                status='ros_setup_missing',
                method='ros_topic_pub_subprocess',
                topic=topic,
                detail_message=f'ROS setup script not found: {self._ros_setup_script}',
            )
        if not self._workspace_setup_script.exists():
            return ActuationDispatchResult(
                dispatched=False,
                status='workspace_setup_missing',
                method='ros_topic_pub_subprocess',
                topic=topic,
                detail_message=f'Workspace setup script not found: {self._workspace_setup_script}',
            )
        if not self._publisher_script.exists():
            return ActuationDispatchResult(
                dispatched=False,
                status='publisher_script_missing',
                method='ros_topic_pub_subprocess',
                topic=topic,
                detail_message=f'IoT command publisher script not found: {self._publisher_script}',
            )
        return None

    def _publish_command(
        self,
        command: _IoTCommandPayload,
        *,
        topic: str,
        min_subscribers: int,
    ) -> ActuationDispatchResult:
        # 명령를 외부 시스템이나 다음 처리 단계로 전달한다.
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            suffix='.json',
            prefix='agribot_iot_command_',
            delete=False,
        ) as stream:
            json.dump(asdict(command), stream, ensure_ascii=False, indent=2, sort_keys=True)
            temp_path = Path(stream.name)

        shell_command = (
            f'source {shlex.quote(str(self._env_setup_script))} && '
            f'source_ros_setup_files && '
            f'python3 {shlex.quote(str(self._publisher_script))} '
            f'--topic {shlex.quote(topic)} '
            f'--min-subscribers {int(min_subscribers)} '
            f'--discovery-timeout-sec 4.0 '
            f'--post-publish-wait-sec 0.8 '
            f'--payload-file {shlex.quote(str(temp_path))}'
        )
        try:
            completed = subprocess.run(
                ['bash', '-lc', shell_command],
                capture_output=True,
                text=True,
                timeout=self._dispatch_timeout_sec,
                check=False,
                cwd=self._repo_root,
            )
        except subprocess.TimeoutExpired:
            return ActuationDispatchResult(
                dispatched=False,
                status='dispatch_timeout',
                command_id=command.command_id,
                topic=topic,
                device_id=command.device_id,
                device_type=command.device_type,
                method='ros_topic_pub_subprocess',
                detail_message='Timed out while publishing the IoT command to ROS.',
            )
        finally:
            temp_path.unlink(missing_ok=True)

        output_text = completed.stdout.strip() or completed.stderr.strip()
        if completed.returncode != 0:
            return ActuationDispatchResult(
                dispatched=False,
                status='dispatch_failed',
                command_id=command.command_id,
                topic=topic,
                device_id=command.device_id,
                device_type=command.device_type,
                method='ros_topic_pub_subprocess',
                detail_message=output_text or 'ROS IoT command publisher exited with a failure status.',
            )

        return ActuationDispatchResult(
            dispatched=True,
            status='dispatched',
            command_id=command.command_id,
            topic=topic,
            device_id=command.device_id,
            device_type=command.device_type,
            method='ros_topic_pub_subprocess',
            detail_message=output_text or 'IoT command published to ROS successfully.',
        )


def _build_reason_text(
    treatment_plan: DiseaseTreatmentPlan,
    *,
    observation_id: str,
) -> str:
    # reason text를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    payload_items = {
        'effect_color': treatment_plan.effect_color or '',
        'treatment_type': treatment_plan.treatment_type or '',
        'rule_id': treatment_plan.rule_id,
        'observation_id': observation_id,
    }
    if treatment_plan.target_position is not None:
        payload_items['target_x'] = f'{treatment_plan.target_position.x:.3f}'
        payload_items['target_y'] = f'{treatment_plan.target_position.y:.3f}'
        payload_items['target_z'] = f'{treatment_plan.target_position.z:.3f}'
    payload_text = ','.join(
        f'{key}={value}'
        for key, value in payload_items.items()
        if value != ''
    )
    return (
        f'Disease treatment dispatch for {treatment_plan.disease_label}. '
        f'payload={payload_text}'
    )
