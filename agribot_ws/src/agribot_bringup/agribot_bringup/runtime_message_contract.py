# Structured ROS message conversion helpers for backend/runtime bridge traffic.
from __future__ import annotations

from typing import Any

from agribot_interfaces.msg import (
    MissionBridgeStatus,
    MissionRequest,
    ObservationGoalCandidate,
    RobotCommand,
    RobotCommandStatus,
    RobotControlState,
    TargetPose,
)


def _normalize_string(value: Any) -> str:
    # Normalize arbitrary values into a transport-safe string.
    return str(value).strip() if value is not None else ''


def _payload_has_value(payload: dict[str, Any] | None) -> bool:
    # Return whether the payload contains at least one meaningful field.
    if not isinstance(payload, dict):
        return False
    return any(value not in {None, ''} for value in payload.values())


def target_pose_message_from_payload(payload: dict[str, Any] | None) -> TargetPose:
    # Build a TargetPose message from a normalized payload map.
    message = TargetPose()
    if not isinstance(payload, dict):
        return message
    message.x = float(payload.get('x', 0.0) or 0.0)
    message.y = float(payload.get('y', 0.0) or 0.0)
    message.z = float(payload.get('z', 0.0) or 0.0)
    message.yaw = float(payload.get('yaw', 0.0) or 0.0)
    message.frame_id = _normalize_string(payload.get('frame_id'))
    return message


def target_pose_payload_from_message(message: TargetPose) -> dict[str, Any]:
    # Convert a TargetPose message into the backend/runtime JSON contract.
    return {
        'x': float(message.x),
        'y': float(message.y),
        'z': float(message.z),
        'yaw': float(message.yaw),
        'frame_id': _normalize_string(message.frame_id),
    }


def observation_candidate_message_from_payload(
    payload: dict[str, Any],
) -> ObservationGoalCandidate:
    # Build an observation candidate message from a normalized payload map.
    message = ObservationGoalCandidate()
    message.inspect_waypoint_id = _normalize_string(payload.get('inspect_waypoint_id'))
    message.inspect_waypoint_name = _normalize_string(payload.get('inspect_waypoint_name'))
    navigation_pose = payload.get('navigation_pose')
    message.has_navigation_pose = _payload_has_value(navigation_pose)
    message.navigation_pose = target_pose_message_from_payload(
        navigation_pose if isinstance(navigation_pose, dict) else None
    )
    message.final_target_pose = target_pose_message_from_payload(
        payload.get('final_target_pose') if isinstance(payload.get('final_target_pose'), dict) else None
    )
    return message


def observation_candidate_payload_from_message(
    message: ObservationGoalCandidate,
) -> dict[str, Any]:
    # Convert an observation candidate message into the runtime JSON contract.
    payload = {
        'inspect_waypoint_id': _normalize_string(message.inspect_waypoint_id),
        'final_target_pose': target_pose_payload_from_message(message.final_target_pose),
    }
    inspect_waypoint_name = _normalize_string(message.inspect_waypoint_name)
    if inspect_waypoint_name:
        payload['inspect_waypoint_name'] = inspect_waypoint_name
    if bool(message.has_navigation_pose):
        payload['navigation_pose'] = target_pose_payload_from_message(message.navigation_pose)
    return payload


def robot_command_message_from_payload(
    payload: dict[str, Any],
    *,
    stamp=None,
) -> RobotCommand:
    # Build a typed RobotCommand message from the backend bridge payload.
    message = RobotCommand()
    if stamp is not None:
        message.header.stamp = stamp
    nested_payload = payload.get('payload') if isinstance(payload.get('payload'), dict) else {}
    message.command_id = _normalize_string(payload.get('command_id'))
    message.requested_command_type = (
        _normalize_string(payload.get('requested_command_type'))
        or _normalize_string(payload.get('command_type'))
    )
    message.command_type = _normalize_string(payload.get('command_type'))
    message.robot_id = _normalize_string(payload.get('robot_id'))
    message.requested_by = _normalize_string(payload.get('requested_by'))
    message.preempt_current_navigation = bool(payload.get('preempt_current_navigation'))
    message.map_id = _normalize_string(payload.get('map_id'))
    message.target_zone_id = _normalize_string(payload.get('target_zone_id'))
    message.plant_id = _normalize_string(nested_payload.get('plant_id'))
    message.inspect_waypoint_id = _normalize_string(nested_payload.get('inspect_waypoint_id'))
    message.inspect_waypoint_ids = [
        _normalize_string(item)
        for item in nested_payload.get('inspect_waypoint_ids', [])
        if _normalize_string(item)
    ]
    message.home_waypoint_id = _normalize_string(nested_payload.get('home_waypoint_id'))
    target_pose = (
        nested_payload.get('target_pose')
        if isinstance(nested_payload.get('target_pose'), dict)
        else payload.get('target_pose')
    )
    message.has_target_pose = _payload_has_value(target_pose if isinstance(target_pose, dict) else None)
    message.target_pose = target_pose_message_from_payload(
        target_pose if isinstance(target_pose, dict) else None
    )
    message.observation_candidates = [
        observation_candidate_message_from_payload(candidate)
        for candidate in nested_payload.get('observation_candidates', [])
        if isinstance(candidate, dict)
    ]
    return message


def robot_command_payload_from_message(message: RobotCommand) -> dict[str, Any]:
    # Convert a typed RobotCommand message into the legacy payload contract.
    payload: dict[str, Any] = {
        'command_id': _normalize_string(message.command_id),
        'requested_command_type': (
            _normalize_string(message.requested_command_type)
            or _normalize_string(message.command_type)
        ),
        'command_type': _normalize_string(message.command_type),
        'robot_id': _normalize_string(message.robot_id),
        'requested_by': _normalize_string(message.requested_by),
        'preempt_current_navigation': bool(message.preempt_current_navigation),
        'map_id': _normalize_string(message.map_id),
        'target_zone_id': _normalize_string(message.target_zone_id),
        'payload': {},
    }
    nested_payload: dict[str, Any] = payload['payload']
    if bool(message.has_target_pose):
        nested_payload['target_pose'] = target_pose_payload_from_message(message.target_pose)
    plant_id = _normalize_string(message.plant_id)
    if plant_id:
        nested_payload['plant_id'] = plant_id
    inspect_waypoint_id = _normalize_string(message.inspect_waypoint_id)
    if inspect_waypoint_id:
        nested_payload['inspect_waypoint_id'] = inspect_waypoint_id
    inspect_waypoint_ids = [
        _normalize_string(item)
        for item in message.inspect_waypoint_ids
        if _normalize_string(item)
    ]
    if inspect_waypoint_ids:
        nested_payload['inspect_waypoint_ids'] = inspect_waypoint_ids
    home_waypoint_id = _normalize_string(message.home_waypoint_id)
    if home_waypoint_id:
        nested_payload['home_waypoint_id'] = home_waypoint_id
    observation_candidates = [
        observation_candidate_payload_from_message(candidate)
        for candidate in message.observation_candidates
        if _normalize_string(candidate.inspect_waypoint_id)
    ]
    if observation_candidates:
        nested_payload['observation_candidates'] = observation_candidates
    return payload


def robot_command_status_message_from_payload(
    payload: dict[str, Any],
    *,
    stamp=None,
) -> RobotCommandStatus:
    # Build a typed RobotCommandStatus message from the runtime payload.
    message = RobotCommandStatus()
    if stamp is not None:
        message.header.stamp = stamp
    message.command_id = _normalize_string(payload.get('command_id'))
    message.requested_command_type = (
        _normalize_string(payload.get('requested_command_type'))
        or _normalize_string(payload.get('command_type'))
    )
    message.command_type = _normalize_string(payload.get('command_type'))
    message.robot_id = _normalize_string(payload.get('robot_id'))
    message.requested_by = _normalize_string(payload.get('requested_by'))
    message.map_id = _normalize_string(payload.get('map_id'))
    message.frame_id = _normalize_string(payload.get('frame_id'))
    message.status = _normalize_string(payload.get('status'))
    message.message = _normalize_string(payload.get('message'))
    message.error = _normalize_string(payload.get('error'))
    message.result = _normalize_string(payload.get('result'))
    message.target_zone_id = _normalize_string(payload.get('target_zone_id'))
    message.home_waypoint_id = _normalize_string(payload.get('home_waypoint_id'))
    message.target_waypoint_id = _normalize_string(payload.get('target_waypoint_id'))
    message.navigation_phase = _normalize_string(payload.get('navigation_phase'))
    message.preempt_current_navigation = bool(payload.get('preempt_current_navigation'))
    message.has_target_pose = _payload_has_value(
        payload.get('target_pose') if isinstance(payload.get('target_pose'), dict) else None
    )
    message.target_pose = target_pose_message_from_payload(
        payload.get('target_pose') if isinstance(payload.get('target_pose'), dict) else None
    )
    message.has_route_target_pose = _payload_has_value(
        payload.get('route_target_pose') if isinstance(payload.get('route_target_pose'), dict) else None
    )
    message.route_target_pose = target_pose_message_from_payload(
        payload.get('route_target_pose') if isinstance(payload.get('route_target_pose'), dict) else None
    )
    message.has_final_target_pose = _payload_has_value(
        payload.get('final_target_pose') if isinstance(payload.get('final_target_pose'), dict) else None
    )
    message.final_target_pose = target_pose_message_from_payload(
        payload.get('final_target_pose') if isinstance(payload.get('final_target_pose'), dict) else None
    )
    message.received_at = _normalize_string(payload.get('received_at'))
    message.started_at = _normalize_string(payload.get('started_at'))
    message.completed_at = _normalize_string(payload.get('completed_at'))
    message.updated_at = _normalize_string(payload.get('updated_at'))
    return message


def robot_command_status_payload_from_message(
    message: RobotCommandStatus,
) -> dict[str, Any]:
    # Convert a RobotCommandStatus message into the backend JSON contract.
    payload = {
        'command_id': _normalize_string(message.command_id),
        'requested_command_type': _normalize_string(message.requested_command_type),
        'command_type': _normalize_string(message.command_type),
        'robot_id': _normalize_string(message.robot_id),
        'requested_by': _normalize_string(message.requested_by),
        'map_id': _normalize_string(message.map_id),
        'frame_id': _normalize_string(message.frame_id),
        'status': _normalize_string(message.status),
        'message': _normalize_string(message.message),
        'error': _normalize_string(message.error),
        'result': _normalize_string(message.result),
        'target_zone_id': _normalize_string(message.target_zone_id) or None,
        'home_waypoint_id': _normalize_string(message.home_waypoint_id) or None,
        'target_waypoint_id': _normalize_string(message.target_waypoint_id) or None,
        'navigation_phase': _normalize_string(message.navigation_phase) or None,
        'preempt_current_navigation': bool(message.preempt_current_navigation),
        'received_at': _normalize_string(message.received_at),
        'started_at': _normalize_string(message.started_at),
        'completed_at': _normalize_string(message.completed_at),
        'updated_at': _normalize_string(message.updated_at),
    }
    if bool(message.has_target_pose):
        payload['target_pose'] = target_pose_payload_from_message(message.target_pose)
    if bool(message.has_route_target_pose):
        payload['route_target_pose'] = target_pose_payload_from_message(message.route_target_pose)
    if bool(message.has_final_target_pose):
        payload['final_target_pose'] = target_pose_payload_from_message(message.final_target_pose)
    return payload


def robot_control_state_message_from_payload(
    payload: dict[str, Any],
    *,
    stamp=None,
) -> RobotControlState:
    # Build a typed RobotControlState message from the runtime payload.
    message = RobotControlState()
    if stamp is not None:
        message.header.stamp = stamp
    message.mode = _normalize_string(payload.get('mode'))
    message.active_activity = _normalize_string(payload.get('active_activity'))
    message.blocking_reason = _normalize_string(payload.get('blocking_reason'))
    message.message = _normalize_string(payload.get('message'))
    message.is_latched = bool(payload.get('is_latched'))
    message.resume_available = bool(payload.get('resume_available'))
    message.updated_at = _normalize_string(payload.get('updated_at'))
    resume_context = payload.get('resume_context') if isinstance(payload.get('resume_context'), dict) else {}
    message.resume_context_type = _normalize_string(resume_context.get('context_type'))
    message.resume_context_command_id = _normalize_string(resume_context.get('command_id'))
    message.resume_context_command_type = _normalize_string(resume_context.get('command_type'))
    message.resume_context_navigation_phase = _normalize_string(resume_context.get('navigation_phase'))
    message.resume_context_target_waypoint_id = _normalize_string(
        resume_context.get('target_waypoint_id')
    )
    message.resume_context_home_waypoint_id = _normalize_string(
        resume_context.get('home_waypoint_id')
    )
    target_pose = resume_context.get('target_pose') if isinstance(resume_context.get('target_pose'), dict) else None
    route_target_pose = (
        resume_context.get('route_target_pose')
        if isinstance(resume_context.get('route_target_pose'), dict)
        else None
    )
    final_target_pose = (
        resume_context.get('final_target_pose')
        if isinstance(resume_context.get('final_target_pose'), dict)
        else None
    )
    message.has_resume_context_target_pose = _payload_has_value(target_pose)
    message.resume_context_target_pose = target_pose_message_from_payload(target_pose)
    message.has_resume_context_route_target_pose = _payload_has_value(route_target_pose)
    message.resume_context_route_target_pose = target_pose_message_from_payload(route_target_pose)
    message.has_resume_context_final_target_pose = _payload_has_value(final_target_pose)
    message.resume_context_final_target_pose = target_pose_message_from_payload(final_target_pose)
    return message


def robot_control_state_payload_from_message(
    message: RobotControlState,
) -> dict[str, Any]:
    # Convert a RobotControlState message into the backend JSON contract.
    resume_context_type = _normalize_string(message.resume_context_type)
    resume_context: dict[str, Any] | None = None
    if resume_context_type:
        resume_context = {
            'context_type': resume_context_type,
            'command_id': _normalize_string(message.resume_context_command_id) or None,
            'command_type': _normalize_string(message.resume_context_command_type) or None,
            'navigation_phase': _normalize_string(message.resume_context_navigation_phase) or None,
            'target_waypoint_id': _normalize_string(message.resume_context_target_waypoint_id) or None,
            'home_waypoint_id': _normalize_string(message.resume_context_home_waypoint_id) or None,
        }
        if bool(message.has_resume_context_target_pose):
            resume_context['target_pose'] = target_pose_payload_from_message(
                message.resume_context_target_pose
            )
        if bool(message.has_resume_context_route_target_pose):
            resume_context['route_target_pose'] = target_pose_payload_from_message(
                message.resume_context_route_target_pose
            )
        if bool(message.has_resume_context_final_target_pose):
            resume_context['final_target_pose'] = target_pose_payload_from_message(
                message.resume_context_final_target_pose
            )
    return {
        'mode': _normalize_string(message.mode),
        'is_latched': bool(message.is_latched),
        'active_activity': _normalize_string(message.active_activity),
        'blocking_reason': _normalize_string(message.blocking_reason) or None,
        'message': _normalize_string(message.message),
        'resume_available': bool(message.resume_available),
        'resume_context': resume_context,
        'updated_at': _normalize_string(message.updated_at),
    }


def mission_request_message_from_payload(
    payload: dict[str, Any],
    *,
    stamp=None,
) -> MissionRequest:
    # Build a typed MissionRequest message from the backend bridge payload.
    message = MissionRequest()
    if stamp is not None:
        message.header.stamp = stamp
    nested_payload = payload.get('payload') if isinstance(payload.get('payload'), dict) else {}
    message.command_id = _normalize_string(payload.get('command_id'))
    message.mission_id = _normalize_string(payload.get('mission_id')) or message.command_id
    message.request_type = (
        _normalize_string(payload.get('request_type'))
        or _normalize_string(payload.get('command_type'))
    )
    message.robot_id = _normalize_string(payload.get('robot_id'))
    message.requested_by = _normalize_string(payload.get('requested_by'))
    message.zone_ids = [
        _normalize_string(item)
        for item in payload.get('zone_ids', [])
        if _normalize_string(item)
    ]
    loop_count = payload.get('loop_count', nested_payload.get('loop_count', 0))
    message.loop_count = max(0, int(loop_count or 0))
    message.patrol_mode = (
        _normalize_string(payload.get('patrol_mode'))
        or _normalize_string(nested_payload.get('patrol_mode'))
    )
    message.plant_id = _normalize_string(payload.get('plant_id') or nested_payload.get('plant_id'))
    message.fruit_id = _normalize_string(payload.get('fruit_id') or nested_payload.get('fruit_id'))
    message.tomato_id = _normalize_string(payload.get('tomato_id') or nested_payload.get('tomato_id'))
    message.inspect_waypoint_id = _normalize_string(
        payload.get('inspect_waypoint_id') or nested_payload.get('inspect_waypoint_id')
    )
    message.inspect_waypoint_ids = [
        _normalize_string(item)
        for item in (
            payload.get('inspect_waypoint_ids')
            or nested_payload.get('inspect_waypoint_ids')
            or []
        )
        if _normalize_string(item)
    ]
    return message


def mission_request_payload_from_message(message: MissionRequest) -> dict[str, Any]:
    # Convert a MissionRequest message into the legacy backend JSON contract.
    payload: dict[str, Any] = {
        'command_id': _normalize_string(message.command_id),
        'mission_id': _normalize_string(message.mission_id) or _normalize_string(message.command_id),
        'request_type': _normalize_string(message.request_type),
        'robot_id': _normalize_string(message.robot_id),
        'requested_by': _normalize_string(message.requested_by),
        'zone_ids': [
            _normalize_string(item)
            for item in message.zone_ids
            if _normalize_string(item)
        ],
        'loop_count': int(message.loop_count),
        'patrol_mode': _normalize_string(message.patrol_mode),
        'payload': {},
    }
    nested_payload: dict[str, Any] = payload['payload']
    for field_name, value in (
        ('plant_id', _normalize_string(message.plant_id)),
        ('fruit_id', _normalize_string(message.fruit_id)),
        ('tomato_id', _normalize_string(message.tomato_id)),
        ('inspect_waypoint_id', _normalize_string(message.inspect_waypoint_id)),
    ):
        if value:
            payload[field_name] = value
            nested_payload[field_name] = value
    inspect_waypoint_ids = [
        _normalize_string(item)
        for item in message.inspect_waypoint_ids
        if _normalize_string(item)
    ]
    if inspect_waypoint_ids:
        payload['inspect_waypoint_ids'] = inspect_waypoint_ids
        nested_payload['inspect_waypoint_ids'] = inspect_waypoint_ids
    return payload


def mission_bridge_status_message_from_payload(
    payload: dict[str, Any],
    *,
    stamp=None,
) -> MissionBridgeStatus:
    # Build a typed MissionBridgeStatus message from the runtime payload.
    message = MissionBridgeStatus()
    if stamp is not None:
        message.header.stamp = stamp
    message.mission_id = _normalize_string(payload.get('mission_id'))
    message.command_id = _normalize_string(payload.get('command_id'))
    message.request_type = _normalize_string(payload.get('request_type'))
    message.robot_id = _normalize_string(payload.get('robot_id'))
    message.requested_by = _normalize_string(payload.get('requested_by'))
    message.status = _normalize_string(payload.get('status'))
    message.message = _normalize_string(payload.get('message'))
    message.error = _normalize_string(payload.get('error'))
    message.result = _normalize_string(payload.get('result'))
    message.zone_ids = [
        _normalize_string(item)
        for item in payload.get('zone_ids', [])
        if _normalize_string(item)
    ]
    message.has_loop_count = payload.get('loop_count') is not None
    message.loop_count = max(0, int(payload.get('loop_count', 0) or 0))
    message.patrol_mode = _normalize_string(payload.get('patrol_mode'))
    message.plant_id = _normalize_string(payload.get('plant_id'))
    message.fruit_id = _normalize_string(payload.get('fruit_id'))
    message.tomato_id = _normalize_string(payload.get('tomato_id'))
    message.inspect_waypoint_id = _normalize_string(payload.get('inspect_waypoint_id'))
    message.inspect_waypoint_ids = [
        _normalize_string(item)
        for item in payload.get('inspect_waypoint_ids', [])
        if _normalize_string(item)
    ]
    message.received_at = _normalize_string(payload.get('received_at'))
    message.started_at = _normalize_string(payload.get('started_at'))
    message.completed_at = _normalize_string(payload.get('completed_at'))
    message.updated_at = _normalize_string(payload.get('updated_at'))
    return message


def mission_bridge_status_payload_from_message(
    message: MissionBridgeStatus,
) -> dict[str, Any]:
    # Convert a MissionBridgeStatus message into the backend JSON contract.
    payload = {
        'mission_id': _normalize_string(message.mission_id),
        'command_id': _normalize_string(message.command_id),
        'request_type': _normalize_string(message.request_type),
        'robot_id': _normalize_string(message.robot_id),
        'requested_by': _normalize_string(message.requested_by),
        'status': _normalize_string(message.status),
        'message': _normalize_string(message.message),
        'error': _normalize_string(message.error),
        'result': _normalize_string(message.result),
        'zone_ids': [
            _normalize_string(item)
            for item in message.zone_ids
            if _normalize_string(item)
        ],
        'loop_count': int(message.loop_count) if bool(message.has_loop_count) else None,
        'patrol_mode': _normalize_string(message.patrol_mode) or None,
        'plant_id': _normalize_string(message.plant_id) or None,
        'fruit_id': _normalize_string(message.fruit_id) or None,
        'tomato_id': _normalize_string(message.tomato_id) or None,
        'inspect_waypoint_id': _normalize_string(message.inspect_waypoint_id) or None,
        'inspect_waypoint_ids': [
            _normalize_string(item)
            for item in message.inspect_waypoint_ids
            if _normalize_string(item)
        ],
        'received_at': _normalize_string(message.received_at),
        'started_at': _normalize_string(message.started_at),
        'completed_at': _normalize_string(message.completed_at),
        'updated_at': _normalize_string(message.updated_at),
    }
    return payload
