import json

from agribot_control.mission_manager import (
    MissionState,
    MissionStateMachine,
    MissionType,
    RobotMode,
    apply_patrol_status_snapshot,
    parse_patrol_status,
)


def test_start_mission_sets_running_state() -> None:
    machine = MissionStateMachine('farm_01')

    machine.start_mission(MissionType.PATROL.value, target_id='lane_05')

    snapshot = machine.snapshot()
    assert snapshot.mission_type == MissionType.PATROL.value
    assert snapshot.state == MissionState.RUNNING.value
    assert snapshot.current_phase == RobotMode.PATROL.value
    assert snapshot.target_id == 'lane_05'
    assert snapshot.mission_id.startswith('mission-')


def test_pause_and_resume_restore_previous_phase() -> None:
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
