# 이 테스트는 자율주행과 경로 계획 패키지의 harvest simulation 동작을 검증한다.
import math
import pytest

from agribot_navigation.harvest_simulation import (
    HarvestAnimationConfig,
    WorldPose,
    build_gz_pose_request,
    compute_basket_pose,
    compute_carry_pose,
    compute_grasp_pose,
    compute_hidden_pose,
    compute_relative_world_pose,
)
from agribot_navigation.patrol_config import Pose2D


def test_compute_relative_world_pose_honors_robot_heading() -> None:
    # compute relative 월드 위치 자세 honors robot heading 동작과 회귀 여부를 검증한다.
    pose = Pose2D(x=1.0, y=2.0, z=0.0, yaw=math.pi / 2.0)

    world_pose = compute_relative_world_pose(
        pose,
        forward_offset_m=0.5,
        lateral_offset_m=0.1,
        z_m=0.42,
    )

    assert world_pose == WorldPose(x=0.9, y=2.5, z=0.42)


def test_compute_basket_pose_caps_visual_slots_to_two_and_stacks_overflow() -> None:
    # compute basket 위치 자세 caps visual slots TO TWO AND stacks overflow 동작과 회귀 여부를 검증한다.
    pose = Pose2D(x=0.0, y=0.0, z=0.0, yaw=0.0)
    config = HarvestAnimationConfig()

    first_pose = compute_basket_pose(pose, config, basket_slot_index=0)
    second_pose = compute_basket_pose(pose, config, basket_slot_index=1)
    third_pose = compute_basket_pose(pose, config, basket_slot_index=2)

    assert first_pose.y < second_pose.y
    assert third_pose.x == second_pose.x
    assert third_pose.y == second_pose.y
    assert third_pose.z > second_pose.z
    assert first_pose.z == second_pose.z == 0.26


def test_compute_basket_pose_default_height_keeps_tomato_above_placeholder_floor() -> None:
    # compute basket 위치 자세 default height keeps tomato above placeholder floor 동작과 회귀 여부를 검증한다.
    pose = Pose2D(x=-2.0, y=4.0, z=0.0, yaw=0.0)

    basket_pose = compute_basket_pose(pose, HarvestAnimationConfig(), basket_slot_index=0)

    assert basket_pose.x == pytest.approx(-2.14)
    assert basket_pose.y == pytest.approx(3.975)
    assert basket_pose.z == pytest.approx(0.26)


def test_build_gz_pose_request_formats_pose_for_set_pose_service() -> None:
    # build GZ 위치 자세 요청 데이터 formats 위치 자세 FOR SET 위치 자세 서비스 동작과 회귀 여부를 검증한다.
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
    # compute carry 위치 자세 uses animation 설정 defaults 동작과 회귀 여부를 검증한다.
    pose = Pose2D(x=-2.0, y=4.0, z=0.0, yaw=0.0)

    carry_pose = compute_carry_pose(pose, HarvestAnimationConfig())

    assert carry_pose == WorldPose(x=-2.24, y=4.0, z=0.46)


def test_compute_grasp_pose_places_tomato_near_gripper_fingers() -> None:
    # compute grasp 위치 자세 places tomato near gripper fingers 동작과 회귀 여부를 검증한다.
    pose = Pose2D(x=-2.0, y=4.0, z=0.0, yaw=0.0)

    grasp_pose = compute_grasp_pose(pose, HarvestAnimationConfig())

    assert grasp_pose == WorldPose(x=-2.31, y=4.0, z=0.54)


def test_compute_hidden_pose_drops_harvested_tomato_below_world_floor() -> None:
    # compute hidden 위치 자세 drops harvested tomato below 월드 floor 동작과 회귀 여부를 검증한다.
    pose = Pose2D(x=-2.0, y=4.0, z=0.82, yaw=0.0)

    hidden_pose = compute_hidden_pose(
        pose,
        HarvestAnimationConfig(hidden_x_m=120.0, hidden_y_m=-45.0, hidden_z_m=-10.0),
    )

    assert hidden_pose == WorldPose(x=120.0, y=-45.0, z=-10.0)
