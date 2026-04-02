# 이 모듈은 AI 판정 계층에서 AI 판정 서비스에서 쓰는 데이터 계약을 정의한다.
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JudgmentType = Literal["DISEASE", "RIPENESS", "HARVEST_DECISION"]
HarvestActionScope = Literal["INDIVIDUAL", "BULK"]


class AiJudgmentRecordOut(BaseModel):
    # AI 판정 결과 기록 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    id: str
    plant_id: str | None = None
    fruit_id: str | None = None
    zone_id: str | None = None
    judgment_type: JudgmentType
    model_name: str
    model_version: str
    raw_label: str
    canonical_code: str
    confidence: float
    risk_level: str | None = None
    recommended_action_code: str
    requires_approval: bool
    payload_json: dict[str, Any]
    image_url: str | None = None
    created_at: str


class RipenessJudgmentCreateRequest(BaseModel):
    # ripeness 판정 결과 create 요청 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    plant_id: str = ""
    fruit_id: str = ""
    zone_id: str = ""
    model_name: str = "ripeness_classifier_v1"
    model_version: str = "v1"
    raw_label: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    image_url: str = ""
    evidence: list[str] = Field(default_factory=list)


class RipenessJudgmentCreateResponse(BaseModel):
    # ripeness 판정 결과 create 응답 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    ripeness_judgment: AiJudgmentRecordOut
    harvest_decision: AiJudgmentRecordOut | None = None


class AiJudgmentHistoryOut(BaseModel):
    # AI 판정 결과 이력 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    items: list[AiJudgmentRecordOut]


class HarvestDecisionActionRequest(BaseModel):
    # harvest decision action 요청 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    plant_id: str = ""
    fruit_id: str = ""
    zone_id: str = ""
    requested_by: str = "frontend"


class HarvestDecisionActionOut(BaseModel):
    # harvest decision action 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    scope: HarvestActionScope
    plant_id: str | None = None
    fruit_id: str | None = None
    zone_id: str | None = None
    disease_judgment: AiJudgmentRecordOut | None = None
    ripeness_judgment: AiJudgmentRecordOut | None = None
    harvest_decision: AiJudgmentRecordOut
    disease_valid: bool
    disease_age_seconds: int | None = None
    disease_valid_window_seconds: int


class BulkHarvestDecisionRequest(BaseModel):
    # bulk harvest decision 요청 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    targets: list[HarvestDecisionActionRequest] = Field(default_factory=list)
    requested_by: str = "frontend"


class BulkHarvestDecisionResponse(BaseModel):
    # bulk harvest decision 응답 데이터를 구조적으로 다루기 위한 클래스를 정의한다.
    items: list[HarvestDecisionActionOut]
