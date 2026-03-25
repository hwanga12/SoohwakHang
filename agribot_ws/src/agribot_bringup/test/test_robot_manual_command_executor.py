from agribot_bringup.robot_manual_command_executor import (
    CommandValidationError,
    describe_manual_navigation_label,
    parse_manual_command_payload,
    resolve_return_home_target,
    should_retry_goal_rejection,
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
