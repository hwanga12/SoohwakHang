"""수확 데모 좌표 계산이 로봇 heading과 바구니 슬롯 규칙을 올바르게 반영하는지 검증한다."""

import math

from agribot_navigation.harvest_simulation import (
    HarvestAnimationConfig,
    WorldPose,
    build_gz_pose_request,
    compute_basket_pose,
    compute_carry_pose,
    compute_relative_world_pose,
)
from agribot_navigation.patrol_config import Pose2D


def test_compute_relative_world_pose_honors_robot_heading() -> None:
    pose = Pose2D(x=1.0, y=2.0, z=0.0, yaw=math.pi / 2.0)

    world_pose = compute_relative_world_pose(
        pose,
        forward_offset_m=0.5,
        lateral_offset_m=0.1,
        z_m=0.42,
    )

    assert world_pose == WorldPose(x=0.9, y=2.5, z=0.42)


def test_compute_basket_pose_spreads_loaded_tomatoes_across_slots() -> None:
    pose = Pose2D(x=0.0, y=0.0, z=0.0, yaw=0.0)
    config = HarvestAnimationConfig()

    first_pose = compute_basket_pose(pose, config, basket_slot_index=0)
    third_pose = compute_basket_pose(pose, config, basket_slot_index=2)
    fourth_pose = compute_basket_pose(pose, config, basket_slot_index=3)

    assert first_pose.y < third_pose.y
    assert fourth_pose.x < first_pose.x


def test_build_gz_pose_request_formats_pose_for_set_pose_service() -> None:
    request = build_gz_pose_request(
        'farm01_plant_01_tomato_01',
        WorldPose(x=1.25, y=-0.5, z=0.42),
    )

    assert request == (
        'name: "farm01_plant_01_tomato_01", '
        'position: {x: 1.250000, y: -0.500000, z: 0.420000}, '
        'orientation: {x: 0.000000, y: 0.000000, z: 0.000000, w: 1.000000}'
    )


def test_compute_carry_pose_uses_animation_config_defaults() -> None:
    pose = Pose2D(x=-2.0, y=4.0, z=0.0, yaw=0.0)

    carry_pose = compute_carry_pose(pose, HarvestAnimationConfig())

    assert carry_pose == WorldPose(x=-1.76, y=4.0, z=0.46)
