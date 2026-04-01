# 이 모듈은 백엔드 API 요청과 응답에 사용하는 공통 스키마를 정의.
from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiEnvelope(BaseModel, Generic[T]):
    # API 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    data: T


class Point3DOut(BaseModel):
    # point 3 D 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    x: float
    y: float
    z: float = 0.0


class PoseOut(Point3DOut):
    # 위치 자세 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    yaw: float = 0.0
    frame_id: str = "map"


class ZoneBoundsOut(BaseModel):
    # 구역 bounds 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    min_x: float | None = None
    max_x: float | None = None
    min_y: float | None = None
    max_y: float | None = None
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None


class DashboardSummaryOut(BaseModel):
    # dashboard summary 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    robot_uptime_pct: str
    active_task: str
    critical_alert_count: int
    plant_count: int
    ready_fruit_count: int
    robot_name: str


class ZoneOut(BaseModel):
    # 구역 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    name: str
    label: str
    description: str
    representative_pose: PoseOut
    bounds: ZoneBoundsOut | dict[str, Any]
    plant_count: int
    map_id: str


class EnvironmentLatestOut(BaseModel):
    # environment latest 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    zone_id: str
    temperature: float | None = None
    humidity: float | None = None
    soil_moisture: float | None = None
    temperature_delta: str = ""
    humidity_delta: str = ""
    soil_status: str = ""
    recommendation: str = ""
    recorded_at: str = ""


class EnvironmentHistoryItemOut(BaseModel):
    # environment 이력 item 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    zone_id: str
    temperature: float | None = None
    humidity: float | None = None
    soil_moisture: float | None = None
    recorded_at: str = ""


class IotDeviceOut(BaseModel):
    # IoT 장치 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    device_id: str
    zone_id: str
    device_type: str
    display_name: str
    control_mode: str
    current_state: str
    current_value: float | None = None
    value_unit: str | None = None
    is_online: bool
    last_seen_at: str = ""


class ActuationRecommendationOut(BaseModel):
    # actuation recommendation 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    title: str
    detail: str
    priority: str
    status: str
    zone_id: str
    device_id: str


class ManualActuationDispatchOut(BaseModel):
    # manual actuation dispatch 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    command_id: str
    device_id: str
    device_name: str
    command_type: str
    command_status: str
    message: str


class RecommendationApprovalOut(BaseModel):
    # recommendation approval 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    status: str
    message: str
    command: ManualActuationDispatchOut | None = None


class RecommendationRejectOut(BaseModel):
    # recommendation reject 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    status: str
    reviewed_by: str
    comment: str | None = None


class ActuationHistoryOut(BaseModel):
    # actuation 이력 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    command_id: str
    device_id: str
    device_name: str
    command_type: str
    command_status: str
    result: str
    result_message: str
    state_after: str
    actual_value: float | None = None
    value_unit: str | None = None
    started_at: str = ""
    finished_at: str = ""


class TreatmentPlanReasonOut(BaseModel):
    # 처치 계획 reason 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    reason: str = ""


class PlantObservationItemOut(BaseModel):
    # 작물 개체 관측 결과 item 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    class_name: str
    label: str
    display_label: str
    reviewed_at: str
    image_url: str = ""
    decision_source: str = ""
    health_percent: int | float = 0
    detail: str = ""
    treatment_plan: TreatmentPlanReasonOut | None = None


class PlantSummaryOut(BaseModel):
    # 작물 개체 summary 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    plant_id: str
    name: str
    crop_name: str
    target_fruit_id: str = ""
    fruit_id: str = ""
    zone_id: str
    zone_label: str
    position: PoseOut | dict[str, Any]
    last_observed_at: str = ""
    health_score: float | None = None
    health: int | float = 0
    status: str = ""
    latest_label: str = ""
    latest_display_label: str = ""
    latest_image_url: str = ""
    recommended_action: str = ""
    ready_to_harvest: bool = False
    needs_water: bool = False
    needs_nutrition: bool = False


class PlantDetailOut(BaseModel):
    # 작물 개체 detail 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    plant_id: str
    name: str
    zone_id: str
    zone_label: str
    position: PoseOut | dict[str, Any]
    latest_observation: PlantObservationItemOut | None = None
    observation_count: int = 0
    target_fruit_id: str | None = None


class PlantObservationFeedOut(BaseModel):
    # 작물 개체 관측 결과 feed 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    plant_id: str
    plant_name: str
    zone_id: str
    zone_label: str
    items: list[PlantObservationItemOut]


class AlertOut(BaseModel):
    # alert 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    observation_id: str = ""
    severity: str
    level: str
    title: str
    message: str
    detail: str
    description: str
    action: str = ""
    location: str = ""
    zone_id: str = ""
    plant_id: str = ""
    label: str = ""
    display_label: str = ""
    image_url: str = ""
    detected_at: str = ""
    created_at: str = ""
    time: str = ""
    is_acked: bool = False
    acknowledged_at: str = ""
    acknowledged_by: str = ""


class AlertAckOut(BaseModel):
    # alert ACK 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    acknowledged_by: str
    acknowledged_at: str


class HarvestHistoryOut(BaseModel):
    # harvest 이력 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    route_id: str
    batch_id: str
    name: str
    summary: str
    detail: str
    state: str
    status: str
    mission_id: str = ""
    fruit_id: str | None = None
    plant_id: str | None = None
    current_phase: str = ""
    updated_at: str = ""
    basket_count: int | None = None
    success: bool | None = None


class HarvestStatsOut(BaseModel):
    # harvest stats 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    today_weight_kg: str
    today_harvest_kg: str
    basket_fill_rate: str
    basket_state: str
    success_rate: str
    failed_count: str
    next_swap_eta: str
    basket_count: int
    remaining_ready_count: int
    last_harvested_fruit_id: str = ""
    mission_status: str = ""
    current_phase: str = ""
    active_mission_id: str = ""
    active_target_id: str = ""
    detail_message: str = ""
    loaded_fruit_ids: list[str]


class RobotControlStateOut(BaseModel):
    # robot control 상태 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    source: str
    available: bool
    mode: str
    is_latched: bool
    active_activity: str
    blocking_reason: str | None = None
    message: str
    resume_available: bool
    resume_context: dict[str, Any] | None = None
    updated_at: str


class RobotCommandStatusOut(BaseModel):
    # robot 명령 상태 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    source: str
    available: bool
    command_id: str | None = None
    requested_command_type: str | None = None
    command_type: str | None = None
    robot_id: str | None = None
    requested_by: str | None = None
    map_id: str | None = None
    frame_id: str | None = None
    status: str
    message: str
    error: str | None = None
    result: str | None = None
    target_pose: PoseOut | dict[str, Any] | None = None
    route_target_pose: PoseOut | dict[str, Any] | None = None
    final_target_pose: PoseOut | dict[str, Any] | None = None
    target_waypoint_id: str | None = None
    navigation_phase: str | None = None
    target_zone_id: str | None = None
    home_waypoint_id: str | None = None
    preempt_current_navigation: bool = False
    received_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str
    control_state: RobotControlStateOut | None = None
    control_mode: str | None = None
    control_is_latched: bool | None = None
    control_active_activity: str | None = None
    control_blocking_reason: str | None = None
    control_message: str | None = None
    control_resume_available: bool | None = None
    control_updated_at: str | None = None


class RobotStatusOut(BaseModel):
    # robot 상태 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    source: str
    robot_id: str
    status: str
    mission_state: str
    mode: str
    battery: str | None = None
    battery_level: float | None = None
    battery_eta: str | None = None
    speed_mps: str
    speed_mps_value: float
    mission_progress_pct: int | float | None = None
    eta: str | None = None
    waypoint_id: str | None = None
    next_waypoint: str | None = None
    next_target_crop_id: str | None = None
    current_zone_id: str
    zone_label: str
    updated_at: str
    note: str = ""
    pose_source: str = ""
    current_control_state: RobotControlStateOut
    control_mode: str
    control_is_latched: bool
    control_active_activity: str
    control_blocking_reason: str | None = None
    control_resume_available: bool
    control_message: str
    control_updated_at: str
    latest_command: RobotCommandStatusOut
    latest_command_id: str | None = None
    latest_command_status: str | None = None
    latest_command_type: str | None = None
    latest_requested_command_type: str | None = None
    latest_command_message: str | None = None


class RobotPoseOut(BaseModel):
    # robot 위치 자세 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    source: str
    robot_id: str
    map_id: str
    current_zone_id: str
    current_zone_label: str
    pose: PoseOut
    linear_speed_mps: float
    updated_at: str
    note: str = ""


class RobotMapOut(BaseModel):
    # robot 지도 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    source: str
    map_id: str
    image_url: str
    resolution: float
    origin: PoseOut
    width: int
    height: int
    bounds: ZoneBoundsOut


class RobotGuideLineOut(BaseModel):
    # robot guide line 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    axis: Literal["x", "y"]
    value: float
    label: str


class RobotAssetOut(BaseModel):
    # robot asset 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    linked_id: str | None = None
    kind: Literal["plant", "sprinkler"]
    label: str
    short_label: str
    zone_id: str
    description: str
    position: Point3DOut
    navigation_pose: PoseOut | None = None
    approach_pose: PoseOut | None = None
    inspect_waypoint_id: str | None = None
    inspect_waypoint_name: str | None = None
    status: str


class RobotMapLayersOut(BaseModel):
    # robot 지도 layers 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    source: str
    map_id: str
    bounds: ZoneBoundsOut
    row_guides: list[RobotGuideLineOut]
    lane_guides: list[RobotGuideLineOut]
    assets: list[RobotAssetOut]
    counts: dict[str, int]


class RequestReceiptOut(BaseModel):
    # 요청 데이터 receipt 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    accepted: bool
    status: str
    message: str
    requested_at: str


class RobotTargetZoneOut(BaseModel):
    # robot target 구역 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    name: str
    representative_waypoint_id: str | None = None


class RobotCommandDispatchOut(BaseModel):
    # robot 명령 dispatch 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    accepted: bool
    request_status: str
    message: str
    command_id: str
    requested_command_type: str
    command_type: str
    robot_id: str
    requested_by: str
    map_id: str | None = None
    bridge_file: str
    status_endpoint: str
    control_status_endpoint: str | None = None
    target_pose: PoseOut | None = None
    target_zone_id: str | None = None
    preempt_current_navigation: bool = False
    request: RequestReceiptOut
    current_control_state: RobotControlStateOut | None = None
    target_zone: RobotTargetZoneOut | None = None


class MissionDispatchOut(BaseModel):
    # 미션 dispatch 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    accepted: bool
    request_status: str
    message: str
    operator_message: str
    mission_id: str
    command_id: str
    request_type: str
    requested_type: str
    robot_id: str
    requested_by: str
    bridge_file: str
    status_endpoint: str
    request: RequestReceiptOut
    zone_ids: list[str] = Field(default_factory=list)
    loop_count: int | None = None
    patrol_mode: str = ""
    plant_id: str | None = None
    fruit_id: str | None = None
    tomato_id: str | None = None


class MissionStatusOut(BaseModel):
    # 미션 상태 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    available: bool
    mission_id: str
    command_id: str
    mission_type: str
    request_type: str
    requested_type: str
    status: str
    state: str
    current_phase: str = ""
    progress_pct: int | None = None
    retry_count: int | None = None
    message: str
    operator_message: str
    detail_message: str
    error: str = ""
    result: str = ""
    updated_at: str = ""
    zone_ids: list[str] = Field(default_factory=list)
    loop_count: int | None = None
    patrol_mode: str = ""
    plant_id: str | None = None
    fruit_id: str | None = None
    tomato_id: str | None = None
    zone_id: str | None = None
    target_id: str | None = None
    received_at: str = ""
    started_at: str = ""
    completed_at: str = ""
