from agribot_bringup.robot_manual_command_executor import (
    CommandValidationError,
    parse_manual_command_payload,
    resolve_return_home_target,
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
