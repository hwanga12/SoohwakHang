# 이 테스트는 상위 제어와 의사결정 패키지의 mission manager 동작을 검증한다.
import json

from agribot_control.mission_manager import (
    MissionState,
    MissionStateMachine,
    MissionType,
    RobotMode,
    apply_patrol_status_snapshot,
    build_status_telemetry,
    parse_control_state,
    parse_patrol_status,
)
from agribot_control.observation_priority import ObservationTaskCandidate


def test_start_mission_sets_running_state() -> None:
    # start 미션 sets running 상태 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')

    machine.start_mission(MissionType.PATROL.value, target_id='lane_05')

    snapshot = machine.snapshot()
    assert snapshot.mission_type == MissionType.PATROL.value
    assert snapshot.state == MissionState.RUNNING.value
    assert snapshot.current_phase == RobotMode.PATROL.value
    assert snapshot.target_id == 'lane_05'
    assert snapshot.mission_id.startswith('mission-')


def test_pause_and_resume_restore_previous_phase() -> None:
    # pause AND resume restore previous 단계 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')
    machine.start_mission(MissionType.HARVEST.value, target_id='fruit_01')

    machine.pause()
    paused_snapshot = machine.snapshot()
    assert paused_snapshot.state == MissionState.PAUSED.value
    assert paused_snapshot.current_phase == 'PAUSED'
    assert machine.robot_mode == RobotMode.STOPPED.value

    machine.resume()
    resumed_snapshot = machine.snapshot()
    assert resumed_snapshot.state == MissionState.RUNNING.value
    assert resumed_snapshot.current_phase == RobotMode.HARVEST.value
    assert machine.robot_mode == RobotMode.HARVEST.value


def test_fail_moves_machine_into_error_state() -> None:
    # fail moves machine into error 상태 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')
    machine.start_mission(MissionType.RETURN_HOME.value)

    machine.fail(detail_message='Planner aborted.')

    snapshot = machine.snapshot()
    assert snapshot.state == MissionState.FAILED.value
    assert snapshot.current_phase == RobotMode.ERROR.value
    assert machine.robot_mode == RobotMode.ERROR.value
    assert snapshot.retry_count == 1
    assert snapshot.detail_message == 'Planner aborted.'


def test_parse_patrol_status_calculates_progress() -> None:
    # parse patrol 상태 calculates progress 동작과 회귀 여부를 검증한다.
    snapshot = parse_patrol_status(
        json.dumps(
            {
                'state': 'running',
                'message': 'Navigating to lane 05.',
                'current_waypoint_id': 'farm_01_home',
                'next_waypoint_id': 'farm_01_lane_05_north',
                'current_waypoint_index': 0,
                'next_waypoint_index': 4,
                'total_waypoints': 10,
            }
        )
    )

    assert snapshot is not None
    assert snapshot.state == 'running'
    assert snapshot.next_waypoint_id == 'farm_01_lane_05_north'
    assert snapshot.progress_pct == 40.0


def test_patrol_status_snapshot_pauses_and_resumes_patrol_mission() -> None:
    # patrol 상태 스냅샷 pauses AND resumes patrol 미션 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')
    machine.start_mission(MissionType.PATROL.value, target_id='farm_01_lane_05_north')

    stopped_snapshot = parse_patrol_status(
        json.dumps(
            {
                'state': 'stopped',
                'message': 'Patrol paused before waypoint Lane 05.',
                'next_waypoint_id': 'farm_01_lane_05_north',
                'next_waypoint_index': 4,
                'total_waypoints': 10,
            }
        )
    )
    assert stopped_snapshot is not None
    apply_patrol_status_snapshot(machine, stopped_snapshot)
    assert machine.mission_state == MissionState.PAUSED.value
    assert machine.robot_mode == RobotMode.STOPPED.value
    assert machine.target_id == 'farm_01_lane_05_north'

    running_snapshot = parse_patrol_status(
        json.dumps(
            {
                'state': 'running',
                'message': 'Navigating to lane 05.',
                'next_waypoint_id': 'farm_01_lane_05_north',
                'next_waypoint_index': 4,
                'total_waypoints': 10,
            }
        )
    )
    assert running_snapshot is not None
    apply_patrol_status_snapshot(machine, running_snapshot)

    snapshot = machine.snapshot()
    assert snapshot.state == MissionState.RUNNING.value
    assert snapshot.current_phase == RobotMode.PATROL.value
    assert snapshot.progress_pct == 40.0
    assert snapshot.detail_message == 'Navigating to lane 05.'


def test_patrol_status_snapshot_completes_patrol_mission() -> None:
    # patrol 상태 스냅샷 completes patrol 미션 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')
    machine.start_mission(MissionType.PATROL.value, target_id='farm_01_lane_09_south')

    completed_snapshot = parse_patrol_status(
        json.dumps(
            {
                'state': 'completed',
                'message': 'Patrol completed the configured waypoint sequence.',
                'next_waypoint_index': 19,
                'total_waypoints': 19,
            }
        )
    )
    assert completed_snapshot is not None
    apply_patrol_status_snapshot(machine, completed_snapshot)

    snapshot = machine.snapshot()
    assert snapshot.state == MissionState.COMPLETED.value
    assert snapshot.progress_pct == 100.0
    assert machine.robot_mode == RobotMode.IDLE.value


def test_build_status_telemetry_enriches_patrol_phase_and_target() -> None:
    # build 상태 telemetry enriches patrol 단계 AND target 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')
    machine.start_mission(MissionType.PATROL.value, target_id='farm_01_lane_05_north')
    machine.update_progress(25.0, detail_message='Patrol mission started.')

    patrol_status = parse_patrol_status(
        json.dumps(
            {
                'state': 'running',
                'message': 'Navigating to lane 05 north.',
                'current_waypoint_id': 'farm_01_home',
                'next_waypoint_id': 'farm_01_lane_05_north',
                'current_waypoint_index': 0,
                'next_waypoint_index': 4,
                'total_waypoints': 10,
            }
        )
    )

    assert patrol_status is not None
    telemetry = build_status_telemetry(
        machine.snapshot(),
        robot_mode=machine.robot_mode,
        patrol_status=patrol_status,
        active_observation=None,
        pending_observation_count=2,
        pending_observation_activation_requested=True,
    )

    assert telemetry.current_phase == 'PATROL_NAVIGATING'
    assert telemetry.target_id == 'farm_01_lane_05_north'
    assert telemetry.progress_pct == 40.0
    assert 'current=farm_01_home' in telemetry.detail_message
    assert 'next=farm_01_lane_05_north' in telemetry.detail_message
    assert 'pending_observations=2' in telemetry.detail_message
    assert 'waiting_for_patrol_stop=true' in telemetry.detail_message


def test_build_status_telemetry_marks_return_home_error() -> None:
    # build 상태 telemetry marks return home error 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')
    machine.start_mission(MissionType.RETURN_HOME.value, target_id='farm_01_home')
    machine.fail(detail_message='Planner aborted while returning home.')

    telemetry = build_status_telemetry(
        machine.snapshot(),
        robot_mode=machine.robot_mode,
        patrol_status=None,
        active_observation=None,
        pending_observation_count=0,
        pending_observation_activation_requested=False,
    )

    assert telemetry.has_error is True
    assert telemetry.is_returning_home is False
    assert telemetry.error_code == 'RETURN_HOME_ERROR'
    assert telemetry.error_message == 'Planner aborted while returning home.'


def test_build_status_telemetry_reflects_active_observation_target() -> None:
    # build 상태 telemetry reflects active 관측 결과 target 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')
    machine.start_mission(MissionType.OBSERVE.value, target_id='farm01_plant_03')

    active_observation = ObservationTaskCandidate(
        observation_id='obs-01',
        dedup_key='farm_01:farm01_plant_03:-:diseased_leaf',
        event_kind='diseased_leaf',
        mission_type=MissionType.OBSERVE.value,
        target_id='farm01_plant_03',
        priority=300,
        confidence=0.92,
        observed_at_ns=10,
        detail_message='Selected diseased_leaf event for target farm01_plant_03.',
        plant_id='farm01_plant_03',
        fruit_id='',
        class_name='tomato_leaf_disease',
    )

    telemetry = build_status_telemetry(
        machine.snapshot(),
        robot_mode=machine.robot_mode,
        patrol_status=None,
        active_observation=active_observation,
        pending_observation_count=1,
        pending_observation_activation_requested=False,
    )

    assert telemetry.current_phase == 'OBSERVE_ACTIVE'
    assert telemetry.target_id == 'farm01_plant_03'
    assert 'active_observation=diseased_leaf:farm01_plant_03' in telemetry.detail_message


def test_build_status_telemetry_marks_emergency_stop_as_blocking_error() -> None:
    # build 상태 telemetry marks emergency stop AS blocking error 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')
    machine.start_mission(MissionType.PATROL.value, target_id='farm_01_lane_05_north')

    control_state = parse_control_state(
        json.dumps(
            {
                'mode': 'emergency_stop',
                'is_latched': True,
                'active_activity': 'idle',
                'message': '비상 정지가 활성화되었습니다.',
                'resume_available': True,
                'resume_context': {
                    'context_type': 'patrol',
                },
            }
        )
    )

    assert control_state is not None
    telemetry = build_status_telemetry(
        machine.snapshot(),
        robot_mode=machine.robot_mode,
        patrol_status=None,
        active_observation=None,
        pending_observation_count=0,
        pending_observation_activation_requested=False,
        control_state=control_state,
    )

    assert telemetry.robot_mode == RobotMode.STOPPED.value
    assert telemetry.mission_state == MissionState.PAUSED.value
    assert telemetry.current_phase == 'EMERGENCY_STOPPED'
    assert telemetry.has_error is True
    assert telemetry.error_code == 'EMERGENCY_STOP_ACTIVE'
    assert 'resume_available=patrol' in telemetry.detail_message


def test_build_status_telemetry_returns_no_error_for_control_pause() -> None:
    # build 상태 telemetry returns NO error FOR control pause 동작과 회귀 여부를 검증한다.
    machine = MissionStateMachine('farm_01')
    machine.start_mission(MissionType.PATROL.value, target_id='farm_01_lane_05_north')

    control_state = parse_control_state(
        json.dumps(
            {
                'mode': 'paused',
                'is_latched': True,
                'active_activity': 'idle',
                'message': '일시정지가 활성화되었습니다.',
                'resume_available': False,
            }
        )
    )

    assert control_state is not None
    telemetry = build_status_telemetry(
        machine.snapshot(),
        robot_mode=machine.robot_mode,
        patrol_status=None,
        active_observation=None,
        pending_observation_count=0,
        pending_observation_activation_requested=False,
        control_state=control_state,
    )

    assert telemetry.robot_mode == RobotMode.STOPPED.value
    assert telemetry.mission_state == MissionState.PAUSED.value
    assert telemetry.has_error is False
    assert '일시정지가 활성화되었습니다.' in telemetry.detail_message
