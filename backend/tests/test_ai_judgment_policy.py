# 이 테스트는 백엔드의 ai judgment policy 동작과 회귀 여부를 검증한다.
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.ai_judgments.policy import (
    build_disease_interpretation,
    build_harvest_decision_interpretation,
    build_recheck_disease_interpretation,
    build_ripeness_interpretation,
)
from services.ai_judgments.service import _assess_disease_validity


def test_disease_policy_maps_powdery_mildew_to_high_risk_and_approval() -> None:
    # disease policy 지도 목록 powdery mildew TO high risk AND approval 동작과 회귀 여부를 검증한다.
    result = build_disease_interpretation("powdery_mildew", 0.91)

    assert result.canonical_code == "powdery_mildew"
    assert result.risk_level == "HIGH"
    assert result.recommended_action_code == "SPRAY_PESTICIDE"
    assert result.requires_approval is True
    assert result.payload_json["label_ko"] == "흰가루병 의심"


def test_ripeness_policy_maps_ripe_to_harvest() -> None:
    # ripeness policy 지도 목록 ripe TO harvest 동작과 회귀 여부를 검증한다.
    result = build_ripeness_interpretation("ripe", 0.88)

    assert result.canonical_code == "ripe"
    assert result.risk_level == "LOW"
    assert result.recommended_action_code == "HARVEST"
    assert result.requires_approval is True
    assert result.payload_json["label_ko"] == "수확 가능"


def test_harvest_fusion_holds_when_disease_risk_is_high() -> None:
    # harvest fusion holds when disease risk IS high 동작과 회귀 여부를 검증한다.
    result = build_harvest_decision_interpretation(
        disease_judgment={
            "canonical_code": "powdery_mildew",
            "risk_level": "HIGH",
        },
        ripeness_judgment={
            "canonical_code": "ripe",
            "risk_level": "LOW",
        },
    )

    assert result is not None
    assert result.canonical_code == "harvest_hold"
    assert result.recommended_action_code == "HOLD_HARVEST"
    assert result.requires_approval is False


def test_harvest_fusion_returns_candidate_for_ripe_and_low_disease_risk() -> None:
    # harvest fusion returns candidate FOR ripe AND LOW disease risk 동작과 회귀 여부를 검증한다.
    result = build_harvest_decision_interpretation(
        disease_judgment={
            "canonical_code": "normal",
            "risk_level": "LOW",
        },
        ripeness_judgment={
            "canonical_code": "ripe",
            "risk_level": "LOW",
        },
    )

    assert result is not None
    assert result.canonical_code == "harvest_candidate"
    assert result.recommended_action_code == "HARVEST"
    assert result.requires_approval is True


def test_disease_policy_payload_includes_possible_factors() -> None:
    # disease policy payload includes possible factors 동작과 회귀 여부를 검증한다.
    result = build_disease_interpretation("calcium_deficiency", 0.83)

    assert result.payload_json["possible_factors"]
    assert "칼슘 공급 부족" in result.payload_json["possible_factors"]


def test_recheck_disease_policy_marks_expired_disease_as_recheck() -> None:
    # recheck disease policy marks expired disease AS recheck 동작과 회귀 여부를 검증한다.
    result = build_recheck_disease_interpretation(
        disease_judgment={
            "canonical_code": "powdery_mildew",
            "risk_level": "HIGH",
        },
        ripeness_judgment={
            "canonical_code": "ripe",
            "risk_level": "LOW",
        },
        reason_text="질병 판단 유효 시간이 지나 다시 확인해야 합니다.",
        evidence=["적용 유효 시간 300초", "마지막 질병 판단 경과 420초"],
    )

    assert result.canonical_code == "recheck_disease"
    assert result.recommended_action_code == "RECHECK_DISEASE"
    assert result.requires_approval is False
    assert result.payload_json["decision_reason"] == "질병 판단 유효 시간이 지나 다시 확인해야 합니다."
    assert result.payload_json["fusion_inputs"]["disease_canonical_code"] == "powdery_mildew"


def test_assess_disease_validity_returns_false_when_judgment_is_stale() -> None:
    # assess disease validity returns false when 판정 결과 IS stale 동작과 회귀 여부를 검증한다.
    judgment = SimpleNamespace(created_at=datetime(2026, 3, 27, 10, 0, 0))

    is_valid, age_seconds = _assess_disease_validity(
        judgment,
        reference_time=datetime(2026, 3, 27, 10, 7, 0),
        window_seconds=300,
    )

    assert is_valid is False
    assert age_seconds == 420
