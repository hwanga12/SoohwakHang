from agribot_navigation.patrol_config import Pose2D, Waypoint
from agribot_navigation.patrol_node import collect_batch_goal_end_index


def make_waypoint(
    waypoint_id: str,
    *,
    purpose: str,
    batchable: bool,
    observe_here: bool,
) -> Waypoint:
    return Waypoint(
        waypoint_id=waypoint_id,
        display_name=waypoint_id,
        purpose=purpose,
        description=waypoint_id,
        pose=Pose2D(x=0.0, y=0.0, z=0.0, yaw=0.0),
        lane_id='lane',
        batchable=batchable,
        observe_here=observe_here,
    )


def test_collect_batch_goal_end_index_batches_non_observation_segments() -> None:
    waypoint_ids = ('home', 'front_connector', 'left_entry', 'left_front_inspect')
    waypoints = {
        'home': make_waypoint('home', purpose='home', batchable=True, observe_here=False),
        'front_connector': make_waypoint(
            'front_connector',
            purpose='connector',
            batchable=True,
            observe_here=False,
        ),
        'left_entry': make_waypoint(
            'left_entry',
            purpose='entry',
            batchable=True,
            observe_here=False,
        ),
        'left_front_inspect': make_waypoint(
            'left_front_inspect',
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

    assert end_index == 2


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
