import json
from pathlib import Path
from types import SimpleNamespace

from agribot_bringup.control_state import ControlMode
from agribot_bringup.robot_manual_command_executor import (
    ActiveCommandContext,
    CommandPose,
    CommandValidationError,
    _navigation_failure_message,
    _navigation_result_indicates_transient_tf_error,
    _navigation_result_indicates_start_occupied,
    ManualCommand,
    PatrolStatusSnapshot,
    build_manual_resume_context,
    build_patrol_resume_context,
    describe_manual_navigation_label,
    is_navigation_command_type,
    is_pause_command_type,
    is_resume_command_type,
    parse_manual_command_payload,
    read_runtime_pose_snapshot,
    should_release_orphaned_active_command,
    should_restore_paused_manual_navigation_after_failed_resume,
    should_treat_failed_navigation_as_success,
    should_run_resume_release_recovery,
    should_retry_start_occupied_recovery,
    resolve_preempt_current_navigation,
    resolve_return_home_target,
    should_block_command_for_control_mode,
    should_retry_goal_rejection,
)
from agribot_bringup.manual_navigation_routing import (
    build_manual_navigation_route,
    select_start_waypoint_id,
)
from agribot_navigation.patrol_config import get_default_patrol_waypoints_path, load_patrol_plan


def test_parse_manual_command_payload_extracts_nested_target_pose() -> None:
    command = parse_manual_command_payload(
        {
            'command_id': 'cmd-nav-01',
            'command_type': 'navigate_to_pose',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
            'payload': {
                'target_pose': {
                    'x': 1.2,
                    'y': -3.4,
                    'z': 0.0,
                    'yaw': 0.75,
                    'frame_id': 'map',
                }
            },
        }
    )

    assert command.command_id == 'cmd-nav-01'
    assert command.command_type == 'navigate_to_pose'
    assert command.target_pose is not None
    assert command.target_pose.x == 1.2
    assert command.target_pose.y == -3.4
    assert command.target_pose.yaw == 0.75
    assert command.target_pose.frame_id == 'map'
    assert command.preempt_current_navigation is True


def test_parse_manual_command_payload_rejects_missing_target_pose() -> None:
    try:
        parse_manual_command_payload(
            {
                'command_id': 'cmd-nav-invalid',
                'command_type': 'navigate_to_pose',
                'robot_id': 'AGR-02',
                'requested_by': 'frontend-operator',
                'payload': {},
            }
        )
    except CommandValidationError as exc:
        assert exc.command_id == 'cmd-nav-invalid'
        assert exc.command_type == 'navigate_to_pose'
        assert 'x, y, yaw' in str(exc)
    else:
        raise AssertionError('missing target pose should raise CommandValidationError')


def test_resolve_return_home_target_uses_patrol_plan_home_pose() -> None:
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    command = parse_manual_command_payload(
        {
            'command_id': 'cmd-home-01',
            'command_type': 'return_home',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
        }
    )

    waypoint_id, target_pose = resolve_return_home_target(command, patrol_plan)

    assert waypoint_id == patrol_plan.home_pose_id
    assert target_pose.frame_id == patrol_plan.frame_id
    assert target_pose.x == patrol_plan.waypoints[patrol_plan.home_pose_id].pose.x
    assert target_pose.y == patrol_plan.waypoints[patrol_plan.home_pose_id].pose.y


def test_resolve_return_home_target_allows_waypoint_override() -> None:
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    command = parse_manual_command_payload(
        {
            'command_id': 'cmd-home-02',
            'command_type': 'return_home',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
            'payload': {
                'home_waypoint_id': 'farm_01_lane_01_south_entry',
            },
        }
    )

    waypoint_id, target_pose = resolve_return_home_target(command, patrol_plan)

    assert waypoint_id == 'farm_01_lane_01_south_entry'
    assert target_pose.x == patrol_plan.waypoints[waypoint_id].pose.x
    assert target_pose.y == patrol_plan.waypoints[waypoint_id].pose.y


def test_parse_manual_command_payload_allows_explicit_preempt_override() -> None:
    command = parse_manual_command_payload(
        {
            'command_id': 'cmd-nav-02',
            'command_type': 'navigate_to_pose',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
            'preempt_current_navigation': False,
            'payload': {
                'target_pose': {
                    'x': 2.0,
                    'y': -1.0,
                    'yaw': 0.0,
                    'frame_id': 'map',
                }
            },
        }
    )

    assert command.preempt_current_navigation is False


def test_parse_manual_command_payload_keeps_inspect_waypoint_id_for_plant_navigation() -> None:
    command = parse_manual_command_payload(
        {
            'command_id': 'cmd-nav-plant-01',
            'command_type': 'navigate_to_pose',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
            'target_pose': {
                'x': -4.0,
                'y': 2.0,
                'yaw': -1.5708,
                'frame_id': 'map',
            },
            'payload': {
                'inspect_waypoint_id': 'farm_01_lane_02_inspect_03',
            },
        }
    )

    assert command.inspect_waypoint_id == 'farm_01_lane_02_inspect_03'


def test_parse_manual_command_payload_defaults_non_navigation_preempt_to_false() -> None:
    command = parse_manual_command_payload(
        {
            'command_id': 'cmd-patrol-pause-01',
            'command_type': 'pause_patrol',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
        }
    )

    assert command.preempt_current_navigation is False


def test_parse_manual_command_payload_supports_emergency_stop_and_resume_motion() -> None:
    emergency_command = parse_manual_command_payload(
        {
            'command_id': 'cmd-estop-01',
            'command_type': 'emergency_stop',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
        }
    )
    resume_command = parse_manual_command_payload(
        {
            'command_id': 'cmd-resume-01',
            'command_type': 'resume_motion',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
        }
    )

    assert emergency_command.preempt_current_navigation is False
    assert resume_command.preempt_current_navigation is False


def test_describe_manual_navigation_label_uses_home_waypoint_when_present() -> None:
    assert describe_manual_navigation_label('navigate_to_pose') == '수동 목표점'
    assert describe_manual_navigation_label('return_home') == '홈 복귀'
    assert (
        describe_manual_navigation_label('return_home', 'farm_01_home')
        == '홈 복귀(farm_01_home)'
    )


def test_should_retry_goal_rejection_respects_retry_limit() -> None:
    assert should_retry_goal_rejection(0, 4) is True
    assert should_retry_goal_rejection(3, 4) is True
    assert should_retry_goal_rejection(4, 4) is False
    assert should_retry_goal_rejection(0, 0) is False


def test_should_retry_start_occupied_recovery_respects_retry_limit() -> None:
    assert should_retry_start_occupied_recovery(0, 1) is True
    assert should_retry_start_occupied_recovery(0, 2) is True
    assert should_retry_start_occupied_recovery(1, 1) is False
    assert should_retry_start_occupied_recovery(0, 0) is False


def test_navigation_result_detects_start_occupied_without_missing_nav2_constant() -> None:
    nav_result = SimpleNamespace(error_code=42, error_msg='GridBased planner failed: Start occupied')

    assert _navigation_result_indicates_start_occupied(nav_result) is True
    assert '현재 시작 위치가 통로 밖 장애물로 판정' in _navigation_failure_message(nav_result)
    assert 'error_code=42' in _navigation_failure_message(nav_result)


def test_navigation_result_detects_start_occupied_from_nav2_error_code_only() -> None:
    nav_result = SimpleNamespace(error_code=205, error_msg='')

    assert _navigation_result_indicates_start_occupied(nav_result) is True
    assert '현재 시작 위치가 통로 밖 장애물로 판정' in _navigation_failure_message(nav_result)
    assert 'error_code=205' in _navigation_failure_message(nav_result)


def test_navigation_failure_message_keeps_generic_errors_when_not_start_occupied() -> None:
    nav_result = SimpleNamespace(error_code=17, error_msg='Goal failed')

    assert _navigation_result_indicates_start_occupied(nav_result) is False
    assert _navigation_failure_message(nav_result) == 'Goal failed (error_code=17)'


def test_navigation_result_detects_transient_tf_error_by_error_code() -> None:
    nav_result = SimpleNamespace(error_code=102, error_msg='')

    assert _navigation_result_indicates_transient_tf_error(nav_result) is True


def test_read_runtime_pose_snapshot_reads_map_pose(tmp_path: Path) -> None:
    (tmp_path / 'robot_pose_snapshot.json').write_text(
        json.dumps(
            {
                'pose': {
                    'x': -3.92,
                    'y': 2.18,
                    'z': 0.0,
                    'yaw': -1.57,
                    'frame_id': 'map',
                }
            }
        ),
        encoding='utf-8',
    )

    pose = read_runtime_pose_snapshot(tmp_path, expected_frame='map')

    assert pose is not None
    assert pose.x == -3.92
    assert pose.y == 2.18


def test_should_treat_failed_navigation_as_success_when_runtime_pose_is_near_target(
    tmp_path: Path,
) -> None:
    (tmp_path / 'robot_pose_snapshot.json').write_text(
        json.dumps(
            {
                'pose': {
                    'x': -3.78,
                    'y': 2.12,
                    'z': 0.0,
                    'yaw': -1.57,
                    'frame_id': 'map',
                }
            }
        ),
        encoding='utf-8',
    )

    assert should_treat_failed_navigation_as_success(
        tmp_path,
        expected_frame='map',
        target_pose=CommandPose(
            x=-4.0,
            y=2.0,
            z=0.0,
            yaw=-1.5708,
            frame_id='map',
        ),
        xy_tolerance_m=0.55,
    ) is True


def test_should_not_treat_failed_navigation_as_success_when_runtime_pose_is_far(
    tmp_path: Path,
) -> None:
    (tmp_path / 'robot_pose_snapshot.json').write_text(
        json.dumps(
            {
                'pose': {
                    'x': -1.71,
                    'y': 5.38,
                    'z': 0.0,
                    'yaw': -1.57,
                    'frame_id': 'map',
                }
            }
        ),
        encoding='utf-8',
    )

    assert should_treat_failed_navigation_as_success(
        tmp_path,
        expected_frame='map',
        target_pose=CommandPose(
            x=-4.0,
            y=2.0,
            z=0.0,
            yaw=-1.5708,
            frame_id='map',
        ),
        xy_tolerance_m=0.55,
    ) is False


def test_should_release_orphaned_active_command_when_terminal_status_was_already_written() -> None:
    command = ManualCommand(
        command_id='cmd-nav-terminal',
        command_type='navigate_to_pose',
        robot_id='AGR-02',
        requested_by='frontend-operator',
        target_pose=CommandPose(x=-4.0, y=2.0, z=0.0, yaw=-1.57, frame_id='map'),
        home_waypoint_id=None,
        preempt_current_navigation=True,
    )
    active_context = ActiveCommandContext(
        command=command,
        received_at='2026-03-29T00:00:00Z',
        started_at='2026-03-29T00:00:01Z',
        target_pose=command.target_pose,
    )

    assert should_release_orphaned_active_command(
        active_context,
        {
            'command_id': 'cmd-nav-terminal',
            'status': 'failed',
        },
        has_pending_activity=False,
    ) is True


def test_should_not_release_orphaned_active_command_while_executor_still_has_pending_activity() -> None:
    command = ManualCommand(
        command_id='cmd-nav-active',
        command_type='navigate_to_pose',
        robot_id='AGR-02',
        requested_by='frontend-operator',
        target_pose=CommandPose(x=4.0, y=6.0, z=0.0, yaw=1.57, frame_id='map'),
        home_waypoint_id=None,
        preempt_current_navigation=True,
    )
    active_context = ActiveCommandContext(
        command=command,
        received_at='2026-03-29T00:00:00Z',
        started_at='2026-03-29T00:00:01Z',
        target_pose=command.target_pose,
    )

    assert should_release_orphaned_active_command(
        active_context,
        {
            'command_id': 'cmd-nav-active',
            'status': 'failed',
        },
        has_pending_activity=True,
    ) is False


def test_is_navigation_command_type_matches_manual_navigation_commands() -> None:
    assert is_navigation_command_type('navigate_to_pose') is True
    assert is_navigation_command_type('return_home') is True
    assert is_navigation_command_type('pause_patrol') is False
    assert is_pause_command_type('pause_motion') is True
    assert is_resume_command_type('resume_motion') is True


def test_resolve_preempt_current_navigation_prefers_explicit_values() -> None:
    assert (
        resolve_preempt_current_navigation(
            'navigate_to_pose',
            raw_payload={'preempt_current_navigation': False},
            payload={'preempt_current_navigation': True},
        )
        is False
    )
    assert (
        resolve_preempt_current_navigation(
            'pause_patrol',
            raw_payload={},
            payload={'preempt_current_navigation': True},
        )
        is True
    )


def test_manual_navigation_emergency_stop_scenario_captures_resume_context() -> None:
    context = ActiveCommandContext(
        command=ManualCommand(
            command_id='cmd-nav-live',
            command_type='return_home',
            robot_id='AGR-02',
            requested_by='frontend-operator',
            target_pose=None,
            home_waypoint_id='farm_01_home',
            preempt_current_navigation=True,
        ),
        received_at='2026-03-25T00:00:00+00:00',
        target_pose=CommandPose(
            x=1.0,
            y=2.0,
            z=0.0,
            yaw=0.5,
            frame_id='map',
        ),
        home_waypoint_id='farm_01_home',
    )

    resume_context = build_manual_resume_context(
        context,
        captured_at='2026-03-25T00:00:10+00:00',
    )

    assert resume_context is not None
    assert resume_context.context_type.value == 'manual_navigation'
    assert resume_context.command_type == 'return_home'
    assert resume_context.home_waypoint_id == 'farm_01_home'
    assert resume_context.target_pose is not None
    assert resume_context.target_pose['frame_id'] == 'map'


def test_failed_resume_motion_restores_paused_manual_navigation_context() -> None:
    context = ActiveCommandContext(
        command=ManualCommand(
            command_id='cmd-resume-02',
            command_type='resume_motion',
            robot_id='AGR-02',
            requested_by='frontend-operator',
            target_pose=None,
            home_waypoint_id=None,
            preempt_current_navigation=False,
        ),
        received_at='2026-03-29T00:00:00+00:00',
        started_at='2026-03-29T00:00:01+00:00',
        target_pose=CommandPose(
            x=4.0,
            y=6.0,
            z=0.0,
            yaw=1.5708,
            frame_id='map',
        ),
    )

    assert should_restore_paused_manual_navigation_after_failed_resume(
        context,
        status='failed',
    ) is True
    assert should_restore_paused_manual_navigation_after_failed_resume(
        context,
        status='succeeded',
    ) is False


def test_resume_motion_runs_short_release_recovery_before_retrying_goal() -> None:
    context = ActiveCommandContext(
        command=ManualCommand(
            command_id='cmd-resume-03',
            command_type='resume_motion',
            robot_id='AGR-02',
            requested_by='frontend-operator',
            target_pose=None,
            home_waypoint_id=None,
            preempt_current_navigation=False,
        ),
        received_at='2026-03-29T00:00:00+00:00',
        target_pose=CommandPose(
            x=-4.0,
            y=2.0,
            z=0.0,
            yaw=0.0,
            frame_id='map',
        ),
    )

    assert should_run_resume_release_recovery(context, distance_m=0.14) is True
    assert should_run_resume_release_recovery(context, distance_m=0.0) is False
    assert should_run_resume_release_recovery(None, distance_m=0.14) is False


def test_patrol_emergency_stop_scenario_captures_resume_context() -> None:
    patrol_status = PatrolStatusSnapshot(
        state='running',
        message='Navigating to lane 03.',
        current_waypoint_id='farm_01_home',
        next_waypoint_id='farm_01_lane_03_north',
        current_waypoint_index=0,
        next_waypoint_index=4,
        total_waypoints=10,
        active_navigation_kind='single',
        active_batch_end_waypoint_id='',
        segment_target_waypoint_id='',
    )

    resume_context = build_patrol_resume_context(
        patrol_status,
        captured_at='2026-03-25T00:00:15+00:00',
    )

    assert resume_context is not None
    assert resume_context.context_type.value == 'patrol'
    assert resume_context.patrol_snapshot is not None
    assert resume_context.patrol_snapshot['next_waypoint_id'] == 'farm_01_lane_03_north'


def test_latched_emergency_stop_blocks_new_navigation_until_resume() -> None:
    assert should_block_command_for_control_mode(ControlMode.EMERGENCY_STOP, 'navigate_to_pose') is True
    assert should_block_command_for_control_mode(ControlMode.EMERGENCY_STOP, 'return_home') is True
    assert should_block_command_for_control_mode(ControlMode.EMERGENCY_STOP, 'resume_motion') is False


def test_select_start_waypoint_id_prefers_current_connector_band_anchor() -> None:
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    start_waypoint_id = select_start_waypoint_id(
        patrol_plan,
        SimpleNamespace(x=0.0, y=-8.6, z=0.0, yaw=1.5708),
        target_waypoint_id='farm_01_lane_02_inspect_03',
    )

    assert start_waypoint_id == 'farm_01_home'


def test_build_manual_navigation_route_uses_patrol_lane_sequence_for_plant_inspection() -> None:
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    route = build_manual_navigation_route(
        patrol_plan,
        current_pose=SimpleNamespace(x=0.0, y=-8.6, z=0.0, yaw=1.5708),
        target_pose=SimpleNamespace(x=-4.0, y=2.0, z=0.0, yaw=-1.5708),
        explicit_waypoint_id='farm_01_lane_02_inspect_03',
    )

    assert route.target_waypoint_id == 'farm_01_lane_02_inspect_03'
    assert route.waypoint_ids[0] == 'farm_01_lane_02_south_turn'
    assert route.waypoint_ids[-1] == 'farm_01_lane_02_inspect_03'
    assert route.poses[-1].x == -4.0
    assert route.poses[-1].y == 2.0


def test_select_start_waypoint_id_prefers_target_lane_anchor_when_robot_is_between_beds() -> None:
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    start_waypoint_id = select_start_waypoint_id(
        patrol_plan,
        SimpleNamespace(x=-1.7347, y=1.9200, z=0.0, yaw=2.0991),
        target_waypoint_id='farm_01_lane_02_inspect_03',
    )

    assert start_waypoint_id == 'farm_01_lane_02_north_entry'


def test_build_manual_navigation_route_starts_from_safe_lane_anchor_when_robot_is_between_beds() -> None:
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    route = build_manual_navigation_route(
        patrol_plan,
        current_pose=SimpleNamespace(x=-1.7347, y=1.9200, z=0.0, yaw=2.0991),
        target_pose=SimpleNamespace(x=-4.0, y=2.0, z=0.0, yaw=-1.5708),
        explicit_waypoint_id='farm_01_lane_02_inspect_03',
    )

    assert route.waypoint_ids[0] == 'farm_01_lane_02_north_entry'
    assert route.waypoint_ids[-1] == 'farm_01_lane_02_inspect_03'
    assert route.waypoint_ids[:4] == (
        'farm_01_lane_02_north_entry',
        'farm_01_lane_02_inspect_01',
        'farm_01_lane_02_inspect_02',
        'farm_01_lane_02_inspect_03',
    )
