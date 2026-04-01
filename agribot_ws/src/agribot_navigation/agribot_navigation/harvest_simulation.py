# 이 모듈은 자율주행과 경로 계획 패키지에서 harvest simulation 기능을 담당한다.
from __future__ import annotations

from dataclasses import dataclass
import math

from .patrol_config import Pose2D


@dataclass(frozen=True)
class WorldPose:
    # 월드 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class HarvestAnimationConfig:
    # harvest animation 실행 설정을 한 번에 묶어 다루기 위한 클래스를 정의한다.
    grasp_forward_m: float = -0.31
    grasp_lateral_m: float = 0.0
    grasp_z_m: float = 0.54
    carry_forward_m: float = -0.24
    carry_lateral_m: float = 0.0
    carry_z_m: float = 0.46
    basket_forward_m: float = -0.14
    basket_lateral_m: float = 0.0
    # The basket floor sits near z=0.23 in world coordinates when base_link is
    # on the ground, so keep the tomato center just above it.
    basket_z_m: float = 0.26
    basket_slot_count: int = 2
    basket_slot_lateral_spacing_m: float = 0.05
    basket_slot_forward_spacing_m: float = 0.0
    basket_overflow_stack_z_m: float = 0.035
    hidden_x_m: float = 999.0
    hidden_y_m: float = 999.0
    hidden_z_m: float = -10.0


def compute_relative_world_pose(
    robot_pose: Pose2D,
    *,
    forward_offset_m: float,
    lateral_offset_m: float,
    z_m: float,
) -> WorldPose:
    # 현재 입력 조건을 바탕으로 relative 월드 위치 자세를 계산하거나 결정한다.
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
    # 현재 입력 조건을 바탕으로 grasp 위치 자세를 계산하거나 결정한다.
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
    # 현재 입력 조건을 바탕으로 carry 위치 자세를 계산하거나 결정한다.
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
    # 현재 입력 조건을 바탕으로 basket 위치 자세를 계산하거나 결정한다.
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


def compute_hidden_pose(
    source_pose: Pose2D,
    config: HarvestAnimationConfig,
) -> WorldPose:
    # 현재 입력 조건을 바탕으로 hidden 위치 자세를 계산하거나 결정한다.
    return WorldPose(
        x=config.hidden_x_m,
        y=config.hidden_y_m,
        z=config.hidden_z_m,
    )


def build_gz_pose_request(entity_name: str, pose: WorldPose) -> str:
    # GZ 위치 자세 요청 데이터를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    return (
        f'name: "{entity_name}", '
        f'position: {{x: {pose.x:.6f}, y: {pose.y:.6f}, z: {pose.z:.6f}}}, '
        'orientation: {x: 0.000000, y: 0.000000, z: 0.000000, w: 1.000000}'
    )
