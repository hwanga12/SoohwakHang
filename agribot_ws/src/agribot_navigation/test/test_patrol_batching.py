from agribot_navigation.patrol_config import Pose2D, Waypoint
from agribot_navigation.patrol_node import collect_batch_goal_end_index


def make_waypoint(
    waypoint_id: str,
    *,
    purpose: str,
    batchable: bool,
    observe_here: bool,
    lane_id: str = 'lane',
) -> Waypoint:
    return Waypoint(
        waypoint_id=waypoint_id,
        display_name=waypoint_id,
        purpose=purpose,
        description=waypoint_id,
        pose=Pose2D(x=0.0, y=0.0, z=0.0, yaw=0.0),
        lane_id=lane_id,
        batchable=batchable,
        observe_here=observe_here,
    )


def test_collect_batch_goal_end_index_batches_non_observation_segments_in_same_lane() -> None:
    waypoint_ids = ('home', 'front_connector', 'left_entry', 'left_front_inspect')
    waypoints = {
        'home': make_waypoint(
            'home',
            purpose='home',
            batchable=True,
            observe_here=False,
            lane_id='front_transfer',
        ),
        'front_connector': make_waypoint(
            'front_connector',
            purpose='connector',
            batchable=True,
            observe_here=False,
            lane_id='front_transfer',
        ),
        'left_entry': make_waypoint(
            'left_entry',
            purpose='entry',
            batchable=True,
            observe_here=False,
            lane_id='left_lane',
        ),
        'left_front_inspect': make_waypoint(
            'left_front_inspect',
            purpose='inspect',
            batchable=False,
            observe_here=True,
            lane_id='left_lane',
        ),
    }

    end_index = collect_batch_goal_end_index(
        waypoint_ids,
        waypoints,
        0,
        observe_on_waypoints=True,
        inspect_dwell_sec=0.5,
    )

    assert end_index == 1


def test_collect_batch_goal_end_index_stops_on_observation_waypoints() -> None:
    waypoint_ids = ('left_front_inspect', 'left_mid_inspect')
    waypoints = {
        'left_front_inspect': make_waypoint(
            'left_front_inspect',
            purpose='inspect',
            batchable=False,
            observe_here=True,
        ),
        'left_mid_inspect': make_waypoint(
            'left_mid_inspect',
            purpose='inspect',
            batchable=False,
            observe_here=True,
        ),
    }

    end_index = collect_batch_goal_end_index(
        waypoint_ids,
        waypoints,
        0,
        observe_on_waypoints=True,
        inspect_dwell_sec=0.5,
    )

    assert end_index == 0


def test_collect_batch_goal_end_index_does_not_cross_lane_boundaries() -> None:
    waypoint_ids = ('home', 'front_connector', 'left_entry')
    waypoints = {
        'home': make_waypoint(
            'home',
            purpose='home',
            batchable=True,
            observe_here=False,
            lane_id='staging',
        ),
        'front_connector': make_waypoint(
            'front_connector',
            purpose='connector',
            batchable=True,
            observe_here=False,
            lane_id='transfer_front',
        ),
        'left_entry': make_waypoint(
            'left_entry',
            purpose='entry',
            batchable=True,
            observe_here=False,
            lane_id='left_lane',
        ),
    }

    end_index = collect_batch_goal_end_index(
        waypoint_ids,
        waypoints,
        0,
        observe_on_waypoints=True,
        inspect_dwell_sec=0.5,
    )

    assert end_index == 0


def test_collect_batch_goal_end_index_stops_when_lane_id_is_missing() -> None:
    waypoint_ids = ('home', 'front_connector')
    waypoints = {
        'home': make_waypoint(
            'home',
            purpose='home',
            batchable=True,
            observe_here=False,
            lane_id='',
        ),
        'front_connector': make_waypoint(
            'front_connector',
            purpose='connector',
            batchable=True,
            observe_here=False,
            lane_id='front_transfer',
        ),
    }

    end_index = collect_batch_goal_end_index(
        waypoint_ids,
        waypoints,
        0,
        observe_on_waypoints=True,
        inspect_dwell_sec=0.5,
    )

    assert end_index == 0
