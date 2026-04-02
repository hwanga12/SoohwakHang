# 이 테스트는 자율주행과 경로 계획 패키지의 patrol batching 동작을 검증한다.
from agribot_navigation.patrol_config import Pose2D, Waypoint
from agribot_navigation.patrol_node import (
    build_intermediate_segment_poses,
    collect_batch_goal_end_index,
    is_pose_within_xy_tolerance,
    resolve_effective_waypoint_pose,
    should_treat_soft_completed_navigation_as_success,
)


def make_waypoint(
    waypoint_id: str,
    *,
    purpose: str,
    batchable: bool,
    observe_here: bool,
    lane_id: str = 'lane',
) -> Waypoint:
    # waypoint를 새로 만들어 다음 처리 단계로 넘긴다.
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
    # collect batch 목표 END index batches NON 관측 결과 segments IN same lane 동작과 회귀 여부를 검증한다.
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
    # collect batch 목표 END index stops ON 관측 결과 waypoints 동작과 회귀 여부를 검증한다.
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
    # collect batch 목표 END index does NOT cross lane boundaries 동작과 회귀 여부를 검증한다.
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
    # collect batch 목표 END index stops when lane ID IS missing 동작과 회귀 여부를 검증한다.
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


def test_collect_batch_goal_end_index_respects_max_batch_path_length() -> None:
    # collect batch 목표 END index respects MAX batch 경로 length 동작과 회귀 여부를 검증한다.
    waypoint_ids = ('lane_south', 'lane_north')
    waypoints = {
        'lane_south': Waypoint(
            waypoint_id='lane_south',
            display_name='Lane South',
            purpose='entry',
            description='entry',
            pose=Pose2D(x=-9.0, y=-9.0, z=0.0, yaw=1.5708),
            lane_id='sweep_01',
            batchable=True,
            observe_here=False,
        ),
        'lane_north': Waypoint(
            waypoint_id='lane_north',
            display_name='Lane North',
            purpose='inspect',
            description='inspect',
            pose=Pose2D(x=-9.0, y=9.0, z=0.0, yaw=1.5708),
            lane_id='sweep_01',
            batchable=True,
            observe_here=False,
        ),
    }

    end_index = collect_batch_goal_end_index(
        waypoint_ids,
        waypoints,
        0,
        observe_on_waypoints=True,
        inspect_dwell_sec=0.0,
        max_batch_path_length_m=6.0,
    )

    assert end_index == 0


def test_build_intermediate_segment_poses_returns_no_pose_for_short_hops() -> None:
    # build intermediate segment 위치 자세 목록 returns NO 위치 자세 FOR short hops 동작과 회귀 여부를 검증한다.
    start = Pose2D(x=-10.0, y=14.0, z=0.0, yaw=3.1416)
    end = Pose2D(x=-10.0, y=30.0, z=0.0, yaw=3.1416)

    segment_poses = build_intermediate_segment_poses(
        start,
        end,
        max_segment_length_m=24.0,
    )

    assert segment_poses == ()


def test_build_intermediate_segment_poses_splits_long_lane_travel() -> None:
    # build intermediate segment 위치 자세 목록 splits long lane travel 동작과 회귀 여부를 검증한다.
    start = Pose2D(x=-10.0, y=42.0, z=0.0, yaw=3.1416)
    end = Pose2D(x=-10.0, y=114.0, z=0.0, yaw=3.1416)

    segment_poses = build_intermediate_segment_poses(
        start,
        end,
        max_segment_length_m=24.0,
    )

    assert len(segment_poses) == 2
    assert segment_poses[0].x == -10.0
    assert segment_poses[0].y == 66.0
    assert segment_poses[1].x == -10.0
    assert segment_poses[1].y == 90.0
    assert segment_poses[0].yaw == 1.5707963267948966


def test_should_treat_soft_completed_navigation_as_success_requires_current_pose_near_target() -> None:
    # should treat soft completed navigation AS success requires current 위치 자세 near target 동작과 회귀 여부를 검증한다.
    assert not should_treat_soft_completed_navigation_as_success(
        Pose2D(x=4.3, y=1.4, z=0.0, yaw=0.0),
        Pose2D(x=0.0, y=6.8, z=0.0, yaw=0.0),
        goal_soft_completed=True,
        xy_tolerance_m=0.9,
    )


def test_should_treat_soft_completed_navigation_as_success_accepts_nearby_pose() -> None:
    # should treat soft completed navigation AS success accepts nearby 위치 자세 동작과 회귀 여부를 검증한다.
    assert should_treat_soft_completed_navigation_as_success(
        Pose2D(x=0.2, y=6.2, z=0.0, yaw=0.0),
        Pose2D(x=0.0, y=6.8, z=0.0, yaw=0.0),
        goal_soft_completed=True,
        xy_tolerance_m=0.9,
    )


def test_resolve_effective_waypoint_pose_keeps_lane_heading_for_inspect_waypoint() -> None:
    # resolve effective waypoint 위치 자세 keeps lane heading FOR inspect waypoint 동작과 회귀 여부를 검증한다.
    waypoint_ids = ('left_entry', 'left_front_inspect')
    waypoints = {
        'left_entry': Waypoint(
            waypoint_id='left_entry',
            display_name='Left Entry',
            purpose='entry',
            description='entry',
            pose=Pose2D(x=-10.0, y=12.0, z=0.0, yaw=1.5708),
            lane_id='left_lane',
            batchable=True,
            observe_here=False,
        ),
        'left_front_inspect': Waypoint(
            waypoint_id='left_front_inspect',
            display_name='Left Front Inspect',
            purpose='inspect',
            description='inspect',
            pose=Pose2D(x=-10.0, y=14.0, z=0.0, yaw=3.1416),
            lane_id='left_lane',
            batchable=False,
            observe_here=True,
        ),
    }

    pose = resolve_effective_waypoint_pose(
        waypoint_ids,
        waypoints,
        1,
        prefer_lane_heading_on_inspect_waypoints=True,
    )

    assert pose.x == -10.0
    assert pose.y == 14.0
    assert pose.yaw == 1.5707963267948966


def test_resolve_effective_waypoint_pose_preserves_original_yaw_when_disabled() -> None:
    # resolve effective waypoint 위치 자세 preserves original YAW when disabled 동작과 회귀 여부를 검증한다.
    waypoint_ids = ('left_entry', 'left_front_inspect')
    waypoints = {
        'left_entry': Waypoint(
            waypoint_id='left_entry',
            display_name='Left Entry',
            purpose='entry',
            description='entry',
            pose=Pose2D(x=-10.0, y=12.0, z=0.0, yaw=1.5708),
            lane_id='left_lane',
            batchable=True,
            observe_here=False,
        ),
        'left_front_inspect': Waypoint(
            waypoint_id='left_front_inspect',
            display_name='Left Front Inspect',
            purpose='inspect',
            description='inspect',
            pose=Pose2D(x=-10.0, y=14.0, z=0.0, yaw=3.1416),
            lane_id='left_lane',
            batchable=False,
            observe_here=True,
        ),
    }

    pose = resolve_effective_waypoint_pose(
        waypoint_ids,
        waypoints,
        1,
        prefer_lane_heading_on_inspect_waypoints=False,
    )

    assert pose.yaw == 3.1416


def test_is_pose_within_xy_tolerance_returns_true_near_target() -> None:
    # IS 위치 자세 within XY tolerance returns true near target 동작과 회귀 여부를 검증한다.
    current = Pose2D(x=0.02, y=1.83, z=0.0, yaw=0.0)
    target = Pose2D(x=0.0, y=2.0, z=0.0, yaw=1.5708)

    assert is_pose_within_xy_tolerance(current, target, xy_tolerance_m=0.2)


def test_is_pose_within_xy_tolerance_returns_false_outside_radius() -> None:
    # IS 위치 자세 within XY tolerance returns false outside radius 동작과 회귀 여부를 검증한다.
    current = Pose2D(x=-8.5, y=14.0, z=0.0, yaw=1.5708)
    target = Pose2D(x=-8.5, y=42.0, z=0.0, yaw=1.5708)

    assert not is_pose_within_xy_tolerance(current, target, xy_tolerance_m=0.5)
