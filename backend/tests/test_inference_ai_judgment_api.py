# 이 테스트는 백엔드의 inference ai judgment api 동작과 회귀 여부를 검증한다.
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers import inference
from services.ai_judgments.schemas import (
    AiJudgmentHistoryOut,
    AiJudgmentRecordOut,
    BulkHarvestDecisionRequest,
    BulkHarvestDecisionResponse,
    HarvestDecisionActionOut,
    HarvestDecisionActionRequest,
)


def _sample_judgment(*, judgment_type: str, canonical_code: str) -> AiJudgmentRecordOut:
    # sample judgment 정보를 계산해 반환한다.
    return AiJudgmentRecordOut(
        id=f"{judgment_type.lower()}-001",
        plant_id="farm01_plant_03",
        fruit_id="farm01_plant_03_tomato_01",
        zone_id="farm_01",
        judgment_type=judgment_type,  # type: ignore[arg-type]
        model_name="demo-model",
        model_version="v1",
        raw_label=canonical_code,
        canonical_code=canonical_code,
        confidence=0.91,
        risk_level="LOW",
        recommended_action_code="REOBSERVE",
        requires_approval=False,
        payload_json={
            "label_ko": "데모 판단",
            "summary_text": "데모 판단 요약",
            "evidence": ["근거 1"],
            "possible_factors": [],
        },
        image_url="/mock-images/disease-closeup.png",
        created_at="2026-03-27T10:00:00+00:00",
    )


def _sample_harvest_action_out() -> HarvestDecisionActionOut:
    # sample 수확 action out 정보를 계산해 반환한다.
    return HarvestDecisionActionOut(
        scope="INDIVIDUAL",
        plant_id="farm01_plant_03",
        fruit_id="farm01_plant_03_tomato_01",
        zone_id="farm_01",
        disease_judgment=_sample_judgment(
            judgment_type="DISEASE",
            canonical_code="powdery_mildew",
        ),
        ripeness_judgment=_sample_judgment(
            judgment_type="RIPENESS",
            canonical_code="ripe",
        ),
        harvest_decision=_sample_judgment(
            judgment_type="HARVEST_DECISION",
            canonical_code="recheck_disease",
        ),
        disease_valid=False,
        disease_age_seconds=420,
        disease_valid_window_seconds=300,
    )


def test_latest_judgment_endpoint_returns_service_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    # latest 판정 결과 endpoint returns 서비스 payload 동작과 회귀 여부를 검증한다.
    expected = _sample_judgment(judgment_type="DISEASE", canonical_code="powdery_mildew")

    class StubService:
        # 대체 구현 서비스 관련 핵심 흐름을 한곳에 모아 제공하는 서비스 클래스다.
        def get_latest_judgment(self, **kwargs):
            # latest 판정 결과를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
            assert kwargs["plant_id"] == "farm01_plant_03"
            assert kwargs["fruit_id"] == ""
            assert kwargs["judgment_type"] == "DISEASE"
            return expected

    monkeypatch.setattr(inference, "_ai_judgment_service", StubService())

    response = inference.get_latest_ai_judgment(
        plant_id="farm01_plant_03",
        fruit_id="",
        judgment_type="DISEASE",
    )

    assert response is not None
    assert response.id == expected.id
    assert response.payload_json["summary_text"] == "데모 판단 요약"


def test_history_endpoint_returns_recent_items(monkeypatch: pytest.MonkeyPatch) -> None:
    # 이력 endpoint returns recent items 동작과 회귀 여부를 검증한다.
    expected = AiJudgmentHistoryOut(
        items=[
            _sample_judgment(judgment_type="HARVEST_DECISION", canonical_code="harvest_candidate"),
            _sample_judgment(judgment_type="RIPENESS", canonical_code="ripe"),
        ]
    )

    class StubService:
        # 대체 구현 서비스 관련 핵심 흐름을 한곳에 모아 제공하는 서비스 클래스다.
        def get_judgment_history(self, **kwargs):
            # 판정 결과 이력를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
            assert kwargs["fruit_id"] == "farm01_plant_03_tomato_01"
            assert kwargs["limit"] == 5
            return expected

    monkeypatch.setattr(inference, "_ai_judgment_service", StubService())

    response = inference.get_ai_judgment_history(
        plant_id="",
        fruit_id="farm01_plant_03_tomato_01",
        judgment_type=None,
        limit=5,
    )

    assert len(response.items) == 2
    assert response.items[0].judgment_type == "HARVEST_DECISION"


def test_individual_harvest_endpoint_returns_structured_action(monkeypatch: pytest.MonkeyPatch) -> None:
    # individual harvest endpoint returns structured action 동작과 회귀 여부를 검증한다.
    expected = _sample_harvest_action_out()

    class StubService:
        # 대체 구현 서비스 관련 핵심 흐름을 한곳에 모아 제공하는 서비스 클래스다.
        def create_individual_harvest_action(self, request: HarvestDecisionActionRequest):
            # individual harvest action를 새로 만들어 다음 처리 단계로 넘긴다.
            assert request.fruit_id == "farm01_plant_03_tomato_01"
            return expected

    monkeypatch.setattr(inference, "_ai_judgment_service", StubService())

    response = inference.create_individual_harvest_action(
        HarvestDecisionActionRequest(
            plant_id="farm01_plant_03",
            fruit_id="farm01_plant_03_tomato_01",
            zone_id="farm_01",
            requested_by="frontend",
        )
    )

    assert response.scope == "INDIVIDUAL"
    assert response.disease_valid is False
    assert response.harvest_decision.canonical_code == "recheck_disease"


def test_bulk_harvest_endpoint_maps_value_error_to_http_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # bulk harvest endpoint 지도 목록 value error TO http 400 동작과 회귀 여부를 검증한다.
    class StubService:
        # 대체 구현 서비스 관련 핵심 흐름을 한곳에 모아 제공하는 서비스 클래스다.
        def create_bulk_harvest_action(self, request: BulkHarvestDecisionRequest):
            # bulk harvest action를 새로 만들어 다음 처리 단계로 넘긴다.
            raise ValueError("최신 ripeness judgment가 없습니다.")

    monkeypatch.setattr(inference, "_ai_judgment_service", StubService())

    with pytest.raises(HTTPException) as exc_info:
        inference.create_bulk_harvest_action(
            BulkHarvestDecisionRequest(
                targets=[
                    HarvestDecisionActionRequest(
                        plant_id="farm01_plant_03",
                        fruit_id="farm01_plant_03_tomato_01",
                        zone_id="farm_01",
                        requested_by="frontend",
                    )
                ],
                requested_by="frontend",
            )
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "최신 ripeness judgment가 없습니다."


def test_bulk_harvest_endpoint_returns_batch_results(monkeypatch: pytest.MonkeyPatch) -> None:
    # bulk harvest endpoint returns batch 결과 목록 동작과 회귀 여부를 검증한다.
    expected_item = _sample_harvest_action_out()
    expected = BulkHarvestDecisionResponse(items=[expected_item])

    class StubService:
        # 대체 구현 서비스 관련 핵심 흐름을 한곳에 모아 제공하는 서비스 클래스다.
        def create_bulk_harvest_action(self, request: BulkHarvestDecisionRequest):
            # bulk harvest action를 새로 만들어 다음 처리 단계로 넘긴다.
            assert len(request.targets) == 1
            return expected

    monkeypatch.setattr(inference, "_ai_judgment_service", StubService())

    response = inference.create_bulk_harvest_action(
        BulkHarvestDecisionRequest(
            targets=[
                HarvestDecisionActionRequest(
                    plant_id="farm01_plant_03",
                    fruit_id="farm01_plant_03_tomato_01",
                    zone_id="farm_01",
                    requested_by="frontend",
                )
            ],
            requested_by="frontend",
        )
    )

    assert len(response.items) == 1
    assert response.items[0].harvest_decision.canonical_code == "recheck_disease"
