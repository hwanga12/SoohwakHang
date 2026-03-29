"""Gazebo 수확 데모에서 토마토를 팔 앞과 뒤 바구니로 옮길 좌표를 계산한다."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .patrol_config import Pose2D


@dataclass(frozen=True)
class WorldPose:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class HarvestAnimationConfig:
    grasp_forward_m: float = 0.31
    grasp_lateral_m: float = 0.0
    grasp_z_m: float = 0.54
    carry_forward_m: float = 0.24
    carry_lateral_m: float = 0.0
    carry_z_m: float = 0.46
    basket_forward_m: float = -0.14
    basket_lateral_m: float = 0.0
    # Keep the fruit slightly above the placeholder basket floor so it stays
    # visible after the stow animation instead of sinking into the geometry.
    basket_z_m: float = 0.455
    basket_slot_count: int = 2
    basket_slot_lateral_spacing_m: float = 0.05
    basket_slot_forward_spacing_m: float = 0.0
    basket_overflow_stack_z_m: float = 0.035


def compute_relative_world_pose(
    robot_pose: Pose2D,
    *,
    forward_offset_m: float,
    lateral_offset_m: float,
    z_m: float,
) -> WorldPose:
    cos_yaw = math.cos(robot_pose.yaw)
    sin_yaw = math.sin(robot_pose.yaw)
    return WorldPose(
        x=robot_pose.x + (forward_offset_m * cos_yaw) - (lateral_offset_m * sin_yaw),
        y=robot_pose.y + (forward_offset_m * sin_yaw) + (lateral_offset_m * cos_yaw),
        z=z_m,
    )


def compute_grasp_pose(
    robot_pose: Pose2D,
    config: HarvestAnimationConfig,
) -> WorldPose:
    return compute_relative_world_pose(
        robot_pose,
        forward_offset_m=config.grasp_forward_m,
        lateral_offset_m=config.grasp_lateral_m,
        z_m=config.grasp_z_m,
    )


def compute_carry_pose(
    robot_pose: Pose2D,
    config: HarvestAnimationConfig,
) -> WorldPose:
    return compute_relative_world_pose(
        robot_pose,
        forward_offset_m=config.carry_forward_m,
        lateral_offset_m=config.carry_lateral_m,
        z_m=config.carry_z_m,
    )


def compute_basket_pose(
    robot_pose: Pose2D,
    config: HarvestAnimationConfig,
    *,
    basket_slot_index: int = 0,
) -> WorldPose:
    slot_count = max(1, int(config.basket_slot_count))
    visual_slot_index = min(max(0, basket_slot_index), slot_count - 1)
    centered_slot_index = visual_slot_index - ((slot_count - 1) / 2.0)
    lateral_slot = centered_slot_index * config.basket_slot_lateral_spacing_m
    forward_slot = visual_slot_index * -config.basket_slot_forward_spacing_m
    overflow_level = max(0, basket_slot_index - (slot_count - 1))
    return compute_relative_world_pose(
        robot_pose,
        forward_offset_m=config.basket_forward_m + forward_slot,
        lateral_offset_m=config.basket_lateral_m + lateral_slot,
        z_m=config.basket_z_m + (overflow_level * config.basket_overflow_stack_z_m),
    )


def build_gz_pose_request(entity_name: str, pose: WorldPose) -> str:
    return (
        f'name: "{entity_name}", '
        f'position: {{x: {pose.x:.6f}, y: {pose.y:.6f}, z: {pose.z:.6f}}}, '
        'orientation: {x: 0.000000, y: 0.000000, z: 0.000000, w: 1.000000}'
    )
