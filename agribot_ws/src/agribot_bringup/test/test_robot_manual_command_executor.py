# 이 테스트는 통합 실행과 런치 조율 패키지의 robot manual command executor 동작을 검증한다.
import json
from pathlib import Path
import time
from types import SimpleNamespace

from agribot_bringup.control_state import ControlMode, ManualNavigationPhase
from agribot_bringup.robot_manual_command_executor import (
    ActiveCommandContext,
    CommandPose,
    CommandValidationError,
    _navigation_failure_message,
    _navigation_result_indicates_transient_tf_error,
    _navigation_result_indicates_start_occupied,
    build_intermediate_final_observation_targets,
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
    should_run_route_egress_release_recovery,
    should_restore_paused_manual_navigation_after_failed_resume,
    should_treat_failed_navigation_as_success,
    should_run_resume_release_recovery,
    should_retry_start_occupied_recovery,
    resolve_preempt_current_navigation,
    resolve_return_home_target,
    should_block_command_for_control_mode,
    should_complete_route_anchor_only,
    should_attempt_route_egress_simulation_pose_reset,
    should_retry_goal_rejection,
)
from agribot_bringup.manual_navigation_routing import (
    build_manual_navigation_route,
    select_best_target_waypoint_id,
    select_route_egress_waypoint_id,
    select_start_waypoint_id,
)
from agribot_navigation.patrol_config import Pose2D, get_default_patrol_waypoints_path, load_patrol_plan


def test_parse_manual_command_payload_extracts_nested_target_pose() -> None:
    # parse manual 명령 payload extracts nested target 위치 자세 동작과 회귀 여부를 검증한다.
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
    # parse manual 명령 payload rejects missing target 위치 자세 동작과 회귀 여부를 검증한다.
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
    # resolve return home target uses patrol 계획 home 위치 자세 동작과 회귀 여부를 검증한다.
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
    # resolve return home target allows waypoint override 동작과 회귀 여부를 검증한다.
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
    # parse manual 명령 payload allows explicit preempt override 동작과 회귀 여부를 검증한다.
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
    # parse manual 명령 payload keeps inspect waypoint ID FOR 작물 개체 navigation 동작과 회귀 여부를 검증한다.
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


def test_parse_manual_command_payload_keeps_candidate_inspect_waypoint_ids_for_plant_navigation() -> None:
    # parse manual 명령 payload keeps candidate inspect waypoint ID 목록 FOR 작물 개체 navigation 동작과 회귀 여부를 검증한다.
    command = parse_manual_command_payload(
        {
            'command_id': 'cmd-nav-plant-02',
            'command_type': 'navigate_to_pose',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
            'target_pose': {
                'x': 4.0,
                'y': 4.0,
                'yaw': 1.5708,
                'frame_id': 'map',
            },
            'payload': {
                'plant_id': 'farm01_plant_19',
                'inspect_waypoint_id': 'farm_01_lane_03_inspect_05',
                'inspect_waypoint_ids': [
                    'farm_01_lane_03_inspect_05',
                    'farm_01_lane_center_inspect_05',
                ],
            },
        }
    )

    assert command.plant_id == 'farm01_plant_19'
    assert command.inspect_waypoint_id == 'farm_01_lane_03_inspect_05'
    assert command.inspect_waypoint_ids == (
        'farm_01_lane_03_inspect_05',
        'farm_01_lane_center_inspect_05',
    )


def test_parse_manual_command_payload_keeps_observation_candidates_for_dual_stage_crop_navigation() -> None:
    # parse manual 명령 payload keeps 관측 결과 candidates FOR dual stage 작물 navigation 동작과 회귀 여부를 검증한다.
    command = parse_manual_command_payload(
        {
            'command_id': 'cmd-nav-plant-03',
            'command_type': 'navigate_to_pose',
            'robot_id': 'AGR-02',
            'requested_by': 'frontend-operator',
            'target_pose': {
                'x': 1.7,
                'y': 4.0,
                'yaw': 1.5708,
                'frame_id': 'map',
            },
            'payload': {
                'plant_id': 'farm01_plant_19',
                'inspect_waypoint_id': 'farm_01_lane_center_inspect_05',
                'observation_candidates': [
                    {
                        'inspect_waypoint_id': 'farm_01_lane_center_inspect_05',
                        'inspect_waypoint_name': '중앙 5번 관측점',
                        'navigation_pose': {
                            'x': 0.0,
                            'y': 4.0,
                            'yaw': -1.5708,
                            'frame_id': 'map',
                        },
                        'final_target_pose': {
                            'x': 1.7,
                            'y': 4.0,
                            'yaw': 1.5708,
                            'frame_id': 'map',
                        },
                    },
                    {
                        'inspect_waypoint_id': 'farm_01_lane_03_inspect_05',
                        'inspect_waypoint_name': '3번 라인 5번 관측점',
                        'navigation_pose': {
                            'x': 4.0,
                            'y': 4.0,
                            'yaw': 1.5708,
                            'frame_id': 'map',
                        },
                        'final_target_pose': {
                            'x': 2.3,
                            'y': 4.0,
                            'yaw': -1.5708,
                            'frame_id': 'map',
                        },
                    },
                ],
            },
        }
    )

    assert command.plant_id == 'farm01_plant_19'
    assert len(command.observation_candidates) == 2
    assert command.observation_candidates[0].inspect_waypoint_id == 'farm_01_lane_center_inspect_05'
    assert command.observation_candidates[0].final_target_pose.x == 1.7
    assert command.observation_candidates[1].navigation_pose is not None
    assert command.observation_candidates[1].navigation_pose.x == 4.0


def test_parse_manual_command_payload_defaults_non_navigation_preempt_to_false() -> None:
    # parse manual 명령 payload defaults NON navigation preempt TO false 동작과 회귀 여부를 검증한다.
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
    # parse manual 명령 payload supports emergency stop AND resume motion 동작과 회귀 여부를 검증한다.
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
    # describe manual navigation 라벨 uses home waypoint when present 동작과 회귀 여부를 검증한다.
    assert describe_manual_navigation_label('navigate_to_pose') == '수동 목표점'
    assert describe_manual_navigation_label('return_home') == '홈 복귀'
    assert (
        describe_manual_navigation_label('return_home', 'farm_01_home')
        == '홈 복귀(farm_01_home)'
    )


def test_should_retry_goal_rejection_respects_retry_limit() -> None:
    # should retry 목표 rejection respects retry limit 동작과 회귀 여부를 검증한다.
    assert should_retry_goal_rejection(0, 4) is True
    assert should_retry_goal_rejection(3, 4) is True
    assert should_retry_goal_rejection(4, 4) is False
    assert should_retry_goal_rejection(0, 0) is False


def test_should_retry_start_occupied_recovery_respects_retry_limit() -> None:
    # should retry start occupied recovery respects retry limit 동작과 회귀 여부를 검증한다.
    assert should_retry_start_occupied_recovery(0, 1) is True
    assert should_retry_start_occupied_recovery(0, 2) is True
    assert should_retry_start_occupied_recovery(1, 1) is False
    assert should_retry_start_occupied_recovery(0, 0) is False


def test_navigation_result_detects_start_occupied_without_missing_nav2_constant() -> None:
    # navigation 결과 detects start occupied without missing nav2 constant 동작과 회귀 여부를 검증한다.
    nav_result = SimpleNamespace(error_code=42, error_msg='GridBased planner failed: Start occupied')

    assert _navigation_result_indicates_start_occupied(nav_result) is True
    assert '현재 시작 위치가 통로 밖 장애물로 판정' in _navigation_failure_message(nav_result)
    assert 'error_code=42' in _navigation_failure_message(nav_result)


def test_navigation_result_detects_start_occupied_from_nav2_error_code_only() -> None:
    # navigation 결과 detects start occupied from nav2 error code only 동작과 회귀 여부를 검증한다.
    nav_result = SimpleNamespace(error_code=205, error_msg='')

    assert _navigation_result_indicates_start_occupied(nav_result) is True
    assert '현재 시작 위치가 통로 밖 장애물로 판정' in _navigation_failure_message(nav_result)
    assert 'error_code=205' in _navigation_failure_message(nav_result)


def test_navigation_failure_message_keeps_generic_errors_when_not_start_occupied() -> None:
    # navigation failure message keeps generic errors when NOT start occupied 동작과 회귀 여부를 검증한다.
    nav_result = SimpleNamespace(error_code=17, error_msg='Goal failed')

    assert _navigation_result_indicates_start_occupied(nav_result) is False
    assert _navigation_failure_message(nav_result) == 'Goal failed (error_code=17)'


def test_navigation_result_detects_transient_tf_error_by_error_code() -> None:
    # navigation 결과 detects transient TF error BY error code 동작과 회귀 여부를 검증한다.
    nav_result = SimpleNamespace(error_code=102, error_msg='')

    assert _navigation_result_indicates_transient_tf_error(nav_result) is True


def test_should_attempt_route_egress_simulation_pose_reset_only_for_active_route_egress() -> None:
    # should attempt 경로 egress 시뮬레이션 위치 자세 reset only FOR active 경로 egress 동작과 회귀 여부를 검증한다.
    active_context = ActiveCommandContext(
        command=ManualCommand(
            command_id='cmd-egress-reset',
            command_type='navigate_to_pose',
            robot_id='AGR-02',
            requested_by='tester',
            target_pose=CommandPose(x=0.0, y=6.0, z=0.0, yaw=1.5708, frame_id='map'),
        ),
        received_at='2026-03-29T00:00:00+00:00',
        target_pose=CommandPose(x=0.0, y=6.0, z=0.0, yaw=1.5708, frame_id='map'),
        navigation_phase=ManualNavigationPhase.ROUTE_EGRESS,
    )

    assert should_attempt_route_egress_simulation_pose_reset(active_context) is True

    active_context.navigation_phase = ManualNavigationPhase.ROUTE_ANCHOR
    assert should_attempt_route_egress_simulation_pose_reset(active_context) is False
    assert should_attempt_route_egress_simulation_pose_reset(None) is False


def test_read_runtime_pose_snapshot_reads_map_pose(tmp_path: Path) -> None:
    # read 런타임 데이터 위치 자세 스냅샷 reads 지도 위치 자세 동작과 회귀 여부를 검증한다.
    (tmp_path / 'robot_pose_snapshot.json').write_text(
        json.dumps(
            {
                'timestamp': time.time(),
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


def test_read_runtime_pose_snapshot_ignores_stale_snapshot_when_max_age_is_set(tmp_path: Path) -> None:
    # read 런타임 데이터 위치 자세 스냅샷 ignores stale 스냅샷 when MAX AGE IS SET 동작과 회귀 여부를 검증한다.
    (tmp_path / 'robot_pose_snapshot.json').write_text(
        json.dumps(
            {
                'timestamp': time.time() - 10.0,
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

    pose = read_runtime_pose_snapshot(
        tmp_path,
        expected_frame='map',
        max_age_sec=1.5,
    )

    assert pose is None


def test_should_treat_failed_navigation_as_success_when_runtime_pose_is_near_target(
    tmp_path: Path,
) -> None:
    # should treat failed navigation AS success when 런타임 데이터 위치 자세 IS near target 동작과 회귀 여부를 검증한다.
    (tmp_path / 'robot_pose_snapshot.json').write_text(
        json.dumps(
            {
                'timestamp': time.time(),
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


def test_should_complete_route_anchor_only_when_final_path_is_blocked_but_anchor_is_reached() -> None:
    # should complete 경로 anchor only when final 경로 IS blocked BUT anchor IS reached 동작과 회귀 여부를 검증한다.
    current_pose = Pose2D(x=0.08, y=5.61, z=0.0, yaw=1.57)
    route_target_pose = CommandPose(x=0.0, y=6.0, z=0.0, yaw=1.57, frame_id='map')

    assert should_complete_route_anchor_only(
        current_pose=current_pose,
        route_target_pose=route_target_pose,
        final_path_available=False,
        xy_tolerance_m=0.65,
    ) is True
    assert should_complete_route_anchor_only(
        current_pose=current_pose,
        route_target_pose=route_target_pose,
        final_path_available=True,
        xy_tolerance_m=0.65,
    ) is False


def test_build_intermediate_final_observation_targets_prefers_farthest_reachable_candidates_first() -> None:
    # build intermediate final 관측 결과 targets prefers farthest reachable candidates first 동작과 회귀 여부를 검증한다.
    route_target_pose = CommandPose(x=0.0, y=4.0, z=0.0, yaw=1.5708, frame_id='map')
    final_target_pose = CommandPose(x=1.85, y=4.0, z=0.0, yaw=0.0, frame_id='map')

    candidates = build_intermediate_final_observation_targets(
        route_target_pose,
        final_target_pose,
    )

    assert [round(candidate.x, 3) for candidate in candidates] == [1.702, 1.554, 1.406, 1.258, 1.11]
    assert all(candidate.y == 4.0 for candidate in candidates)
    assert all(0.0 < candidate.x < 1.85 for candidate in candidates)


def test_build_intermediate_final_observation_targets_skips_tiny_adjustments() -> None:
    # build intermediate final 관측 결과 targets skips tiny adjustments 동작과 회귀 여부를 검증한다.
    route_target_pose = CommandPose(x=0.0, y=4.0, z=0.0, yaw=1.5708, frame_id='map')
    final_target_pose = CommandPose(x=0.09, y=4.0, z=0.0, yaw=0.0, frame_id='map')

    assert build_intermediate_final_observation_targets(
        route_target_pose,
        final_target_pose,
    ) == ()


def test_should_not_treat_failed_navigation_as_success_when_runtime_pose_is_far(
    tmp_path: Path,
) -> None:
    # should NOT treat failed navigation AS success when 런타임 데이터 위치 자세 IS FAR 동작과 회귀 여부를 검증한다.
    (tmp_path / 'robot_pose_snapshot.json').write_text(
        json.dumps(
            {
                'timestamp': time.time(),
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


def test_should_not_treat_failed_navigation_as_success_when_snapshot_is_stale(
    tmp_path: Path,
) -> None:
    # should NOT treat failed navigation AS success when 스냅샷 IS stale 동작과 회귀 여부를 검증한다.
    (tmp_path / 'robot_pose_snapshot.json').write_text(
        json.dumps(
            {
                'timestamp': time.time() - 10.0,
                'pose': {
                    'x': -3.95,
                    'y': 2.03,
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
        max_snapshot_age_sec=1.5,
    ) is False


def test_should_release_orphaned_active_command_when_terminal_status_was_already_written() -> None:
    # should release orphaned active 명령 when terminal 상태 WAS already written 동작과 회귀 여부를 검증한다.
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
    # should NOT release orphaned active 명령 while executor still HAS pending 활동 상태 동작과 회귀 여부를 검증한다.
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
    # IS navigation 명령 type matches manual navigation 명령 목록 동작과 회귀 여부를 검증한다.
    assert is_navigation_command_type('navigate_to_pose') is True
    assert is_navigation_command_type('return_home') is True
    assert is_navigation_command_type('pause_patrol') is False
    assert is_pause_command_type('pause_motion') is True
    assert is_resume_command_type('resume_motion') is True


def test_resolve_preempt_current_navigation_prefers_explicit_values() -> None:
    # resolve preempt current navigation prefers explicit values 동작과 회귀 여부를 검증한다.
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
    # manual navigation emergency stop scenario captures resume context 동작과 회귀 여부를 검증한다.
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


def test_build_manual_resume_context_preserves_dual_stage_navigation_targets() -> None:
    # build manual resume context preserves dual stage navigation targets 동작과 회귀 여부를 검증한다.
    context = ActiveCommandContext(
        command=ManualCommand(
            command_id='cmd-nav-dual-stage',
            command_type='navigate_to_pose',
            robot_id='AGR-02',
            requested_by='frontend-operator',
            target_pose=None,
            home_waypoint_id=None,
            preempt_current_navigation=True,
        ),
        received_at='2026-03-29T00:00:00+00:00',
        started_at='2026-03-29T00:00:01+00:00',
        target_pose=CommandPose(
            x=0.0,
            y=2.0,
            z=0.0,
            yaw=-1.5708,
            frame_id='map',
        ),
        route_target_pose=CommandPose(
            x=0.0,
            y=2.0,
            z=0.0,
            yaw=-1.5708,
            frame_id='map',
        ),
        final_target_pose=CommandPose(
            x=-1.7,
            y=2.0,
            z=0.0,
            yaw=1.5708,
            frame_id='map',
        ),
        target_waypoint_id='farm_01_lane_center_inspect_04',
        navigation_phase=ManualNavigationPhase.ROUTE_ANCHOR,
    )

    resume_context = build_manual_resume_context(context)

    assert resume_context is not None
    assert resume_context.target_waypoint_id == 'farm_01_lane_center_inspect_04'
    assert resume_context.route_target_pose is not None
    assert resume_context.final_target_pose is not None
    assert resume_context.route_target_pose['x'] == 0.0
    assert resume_context.final_target_pose['x'] == -1.7
    assert resume_context.navigation_phase == ManualNavigationPhase.ROUTE_ANCHOR.value


def test_failed_resume_motion_restores_paused_manual_navigation_context() -> None:
    # failed resume motion restores paused manual navigation context 동작과 회귀 여부를 검증한다.
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
    # resume motion runs short release recovery before retrying 목표 동작과 회귀 여부를 검증한다.
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


def test_route_egress_runs_short_release_recovery_before_navigate_goal() -> None:
    # 경로 egress runs short release recovery before navigate 목표 동작과 회귀 여부를 검증한다.
    context = ActiveCommandContext(
        command=ManualCommand(
            command_id='cmd-egress-01',
            command_type='navigate_to_pose',
            robot_id='AGR-02',
            requested_by='frontend-operator',
            target_pose=None,
            home_waypoint_id=None,
            preempt_current_navigation=True,
        ),
        received_at='2026-03-29T00:00:00+00:00',
        target_pose=CommandPose(
            x=0.0,
            y=6.0,
            z=0.0,
            yaw=1.5708,
            frame_id='map',
        ),
        navigation_phase=ManualNavigationPhase.ROUTE_EGRESS,
    )

    assert should_run_route_egress_release_recovery(context, distance_m=0.24) is True
    context.route_egress_release_attempted = True
    assert should_run_route_egress_release_recovery(context, distance_m=0.24) is False
    assert should_run_route_egress_release_recovery(context, distance_m=0.0) is False


def test_patrol_emergency_stop_scenario_captures_resume_context() -> None:
    # patrol emergency stop scenario captures resume context 동작과 회귀 여부를 검증한다.
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
    # latched emergency stop blocks NEW navigation until resume 동작과 회귀 여부를 검증한다.
    assert should_block_command_for_control_mode(ControlMode.EMERGENCY_STOP, 'navigate_to_pose') is True
    assert should_block_command_for_control_mode(ControlMode.EMERGENCY_STOP, 'return_home') is True
    assert should_block_command_for_control_mode(ControlMode.EMERGENCY_STOP, 'resume_motion') is False


def test_select_start_waypoint_id_prefers_current_connector_band_anchor() -> None:
    # select start waypoint ID prefers current connector band anchor 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    start_waypoint_id = select_start_waypoint_id(
        patrol_plan,
        SimpleNamespace(x=0.0, y=-8.6, z=0.0, yaw=1.5708),
        target_waypoint_id='farm_01_lane_02_inspect_03',
    )

    assert start_waypoint_id == 'farm_01_home'


def test_build_manual_navigation_route_uses_patrol_lane_sequence_for_plant_inspection() -> None:
    # build manual navigation 경로 uses patrol lane sequence FOR 작물 개체 inspection 동작과 회귀 여부를 검증한다.
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


def test_select_best_target_waypoint_id_prefers_center_lane_candidate_from_home() -> None:
    # select best target waypoint ID prefers center lane candidate from home 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())

    selected_waypoint_id = select_best_target_waypoint_id(
        patrol_plan,
        current_pose=SimpleNamespace(x=0.0, y=-8.6, z=0.0, yaw=1.5708),
        candidate_waypoint_ids=(
            'farm_01_lane_03_inspect_05',
            'farm_01_lane_center_inspect_05',
        ),
        preferred_waypoint_id='farm_01_lane_03_inspect_05',
    )

    assert selected_waypoint_id == 'farm_01_lane_center_inspect_05'


def test_select_best_target_waypoint_id_prefers_right_lane_candidate_when_robot_is_on_right_side() -> None:
    # select best target waypoint ID prefers right lane candidate when robot IS ON right side 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())

    selected_waypoint_id = select_best_target_waypoint_id(
        patrol_plan,
        current_pose=SimpleNamespace(x=5.6, y=4.2, z=0.0, yaw=3.1415),
        candidate_waypoint_ids=(
            'farm_01_lane_03_inspect_05',
            'farm_01_lane_center_inspect_05',
        ),
        preferred_waypoint_id='farm_01_lane_center_inspect_05',
    )

    assert selected_waypoint_id == 'farm_01_lane_03_inspect_05'


def test_select_start_waypoint_id_prefers_target_lane_anchor_when_robot_is_between_beds() -> None:
    # select start waypoint ID prefers target lane anchor when robot IS between beds 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    start_waypoint_id = select_start_waypoint_id(
        patrol_plan,
        SimpleNamespace(x=-1.7347, y=1.9200, z=0.0, yaw=2.0991),
        target_waypoint_id='farm_01_lane_02_inspect_03',
    )

    assert start_waypoint_id == 'farm_01_lane_02_north_entry'


def test_select_start_waypoint_id_avoids_opposite_direction_detour_on_same_lane() -> None:
    # select start waypoint ID avoids opposite direction detour ON same lane 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    start_waypoint_id = select_start_waypoint_id(
        patrol_plan,
        SimpleNamespace(x=0.2, y=0.0, z=0.0, yaw=0.0),
        target_waypoint_id='farm_01_lane_center_inspect_04',
    )

    assert start_waypoint_id == 'farm_01_lane_center_inspect_04'


def test_select_start_waypoint_id_uses_same_row_inspect_anchor_for_crop_side_pose() -> None:
    # select start waypoint ID uses same ROW inspect anchor FOR 작물 side 위치 자세 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    start_waypoint_id = select_start_waypoint_id(
        patrol_plan,
        SimpleNamespace(x=-1.7, y=6.0, z=0.0, yaw=3.1415),
        target_waypoint_id='farm_01_lane_center_inspect_04',
    )

    assert start_waypoint_id == 'farm_01_lane_center_inspect_06'


def test_select_route_egress_waypoint_id_prefers_matching_inspect_anchor_for_crop_side_pose() -> None:
    # select 경로 egress waypoint ID prefers matching inspect anchor FOR 작물 side 위치 자세 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())

    egress_waypoint_id = select_route_egress_waypoint_id(
        patrol_plan,
        SimpleNamespace(x=-1.7, y=6.0, z=0.0, yaw=3.1415),
    )

    assert egress_waypoint_id == 'farm_01_lane_center_inspect_06'


def test_select_route_egress_waypoint_id_handles_right_side_crop_pose_toward_center_lane() -> None:
    # select 경로 egress waypoint ID handles right side 작물 위치 자세 toward center lane 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())

    egress_waypoint_id = select_route_egress_waypoint_id(
        patrol_plan,
        SimpleNamespace(x=1.7, y=6.0, z=0.0, yaw=0.0),
    )

    assert egress_waypoint_id == 'farm_01_lane_center_inspect_06'


def test_select_route_egress_waypoint_id_skips_pose_that_is_already_on_lane_anchor() -> None:
    # select 경로 egress waypoint ID skips 위치 자세 that IS already ON lane anchor 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())

    egress_waypoint_id = select_route_egress_waypoint_id(
        patrol_plan,
        SimpleNamespace(x=0.02, y=6.01, z=0.0, yaw=0.0),
    )

    assert egress_waypoint_id is None


def test_build_manual_navigation_route_starts_from_safe_lane_anchor_when_robot_is_between_beds() -> None:
    # build manual navigation 경로 starts from safe lane anchor when robot IS between beds 동작과 회귀 여부를 검증한다.
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


def test_build_manual_navigation_route_starts_from_same_row_inspect_anchor_for_crop_side_pose() -> None:
    # build manual navigation 경로 starts from same ROW inspect anchor FOR 작물 side 위치 자세 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    route = build_manual_navigation_route(
        patrol_plan,
        current_pose=SimpleNamespace(x=-1.7, y=6.0, z=0.0, yaw=3.1415),
        target_pose=SimpleNamespace(x=0.0, y=2.0, z=0.0, yaw=1.5708),
        explicit_waypoint_id='farm_01_lane_center_inspect_04',
    )

    assert route.waypoint_ids == (
        'farm_01_lane_center_inspect_06',
        'farm_01_lane_center_inspect_05',
        'farm_01_lane_center_inspect_04',
    )


def test_build_manual_navigation_route_to_same_row_target_skips_north_turn_for_crop_side_pose() -> None:
    # build manual navigation 경로 TO same ROW target skips north turn FOR 작물 side 위치 자세 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    route = build_manual_navigation_route(
        patrol_plan,
        current_pose=SimpleNamespace(x=-1.7, y=6.0, z=0.0, yaw=3.1415),
        target_pose=SimpleNamespace(x=0.0, y=6.0, z=0.0, yaw=1.5708),
        explicit_waypoint_id='farm_01_lane_center_inspect_06',
    )

    assert route.waypoint_ids == ('farm_01_lane_center_inspect_06',)


def test_build_manual_navigation_route_from_right_crop_side_starts_from_same_row_inspect_anchor() -> None:
    # build manual navigation 경로 from right 작물 side starts from same ROW inspect anchor 동작과 회귀 여부를 검증한다.
    patrol_plan = load_patrol_plan(get_default_patrol_waypoints_path())
    route = build_manual_navigation_route(
        patrol_plan,
        current_pose=SimpleNamespace(x=1.7, y=6.0, z=0.0, yaw=0.0),
        target_pose=SimpleNamespace(x=0.0, y=2.0, z=0.0, yaw=1.5708),
        explicit_waypoint_id='farm_01_lane_center_inspect_04',
    )

    assert route.waypoint_ids == (
        'farm_01_lane_center_inspect_06',
        'farm_01_lane_center_inspect_05',
        'farm_01_lane_center_inspect_04',
    )
