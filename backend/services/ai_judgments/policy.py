from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_ACTION_LABELS_KO = {
    "NONE": "조치 없음",
    "SPRAY_PESTICIDE": "약제 살포",
    "REOBSERVE": "재관측",
    "RECHECK_DISEASE": "질병 재확인",
    "CHECK_NUTRIENT": "영양 점검",
    "HARVEST": "수확",
    "HOLD_HARVEST": "수확 보류",
}

_RISK_LABELS_KO = {
    "LOW": "낮음",
    "MEDIUM": "중간",
    "HIGH": "높음",
}

_DISEASE_LABEL_KO = {
    "normal": "정상",
    "powdery_mildew": "흰가루병 의심",
    "gray_mold": "잿빛곰팡이병 의심",
    "fruit_cracking": "열과 의심",
    "calcium_deficiency": "칼슘 결핍 의심",
    "macro_npk_deficiency": "다량원소 결핍 의심",
}

_DISEASE_ACTIONS = {
    "normal": "NONE",
    "powdery_mildew": "SPRAY_PESTICIDE",
    "gray_mold": "REOBSERVE",
    "fruit_cracking": "REOBSERVE",
    "calcium_deficiency": "CHECK_NUTRIENT",
    "macro_npk_deficiency": "CHECK_NUTRIENT",
}

_DISEASE_POSSIBLE_FACTORS = {
    "normal": [],
    "powdery_mildew": ["고습 환경", "밀집 재배", "환기 부족"],
    "gray_mold": ["고습 지속", "과밀 환경", "저환기 조건"],
    "fruit_cracking": ["급격한 수분 변화", "온도 스트레스", "과실 비대기 환경 변화"],
    "calcium_deficiency": ["칼슘 공급 부족", "수분 이동 불균형", "과실 비대기 영양 불균형"],
    "macro_npk_deficiency": ["양액 불균형", "비료 공급 부족", "생육 단계와 공급량 불일치"],
}

_DISEASE_ALIASES = {
    "": "normal",
    "healthy": "normal",
    "healthy_leaf": "normal",
    "normal": "normal",
    "normal_leaf": "normal",
    "unknown": "normal",
    "powdery_mildew": "powdery_mildew",
    "response_powdery_mildew": "powdery_mildew",
    "tomato_powdery_mildew": "powdery_mildew",
    "tomato_powdery_mildew_disease": "powdery_mildew",
    "gray_mold": "gray_mold",
    "response_gray_mold": "gray_mold",
    "tomato_gray_mold": "gray_mold",
    "tomato_gray_mold_disease": "gray_mold",
    "fruit_cracking": "fruit_cracking",
    "fruit_crack": "fruit_cracking",
    "crack": "fruit_cracking",
    "tomato_crack": "fruit_cracking",
    "tomato_fruit_cracking": "fruit_cracking",
    "tomato_fruit_cracking_disease": "fruit_cracking",
    "calcium_deficiency": "calcium_deficiency",
    "tomato_calcium_deficiency": "calcium_deficiency",
    "tomato_calcium_deficiency_disease": "calcium_deficiency",
    "blossom_end_rot": "calcium_deficiency",
    "tomato_blossom_end_rot": "calcium_deficiency",
    "macro_n_deficiency": "macro_npk_deficiency",
    "macro_p_deficiency": "macro_npk_deficiency",
    "macro_k_deficiency": "macro_npk_deficiency",
    "macro_npk_deficiency": "macro_npk_deficiency",
    "tomato_macro_npk_deficiency": "macro_npk_deficiency",
    "tomato_macro_npk_deficiency_disease": "macro_npk_deficiency",
}

_RIPENESS_LABEL_KO = {
    "unripe": "미숙",
    "turning": "착색 진행 중",
    "ripe": "수확 가능",
}

_RIPENESS_ACTIONS = {
    "unripe": "HOLD_HARVEST",
    "turning": "REOBSERVE",
    "ripe": "HARVEST",
}

_RIPENESS_ALIASES = {
    "unripe": "unripe",
    "green": "unripe",
    "immature": "unripe",
    "turning": "turning",
    "breaker": "turning",
    "half_ripe": "turning",
    "ripe": "ripe",
    "ripe_tomato": "ripe",
    "harvestable": "ripe",
}


@dataclass(frozen=True)
class JudgmentInterpretation:
    canonical_code: str
    risk_level: str | None
    recommended_action_code: str
    requires_approval: bool
    payload_json: dict[str, Any]


def requires_approval_for(action_code: str) -> bool:
    return action_code in {"SPRAY_PESTICIDE", "CHECK_NUTRIENT", "HARVEST"}


def normalize_disease_label(raw_label: str) -> str:
    normalized = raw_label.strip().lower()
    return _DISEASE_ALIASES.get(normalized, normalized or "normal")


def normalize_ripeness_label(raw_label: str) -> str:
    normalized = raw_label.strip().lower()
    canonical_code = _RIPENESS_ALIASES.get(normalized)
    if canonical_code is None:
        raise ValueError(f"Unsupported ripeness label: {raw_label}")
    return canonical_code


def build_disease_interpretation(
    raw_label: str,
    confidence: float,
    *,
    extra_evidence: list[str] | None = None,
) -> JudgmentInterpretation:
    canonical_code = normalize_disease_label(raw_label)
    risk_level = _disease_risk_level(canonical_code, confidence)
    action_code = _DISEASE_ACTIONS.get(canonical_code, "REOBSERVE")
    evidence = [
        f"질병 라벨 {canonical_code}",
        f"모델 신뢰도 {confidence:.2f}",
    ]
    if extra_evidence:
        evidence.extend(item for item in extra_evidence if item)

    label_ko = _DISEASE_LABEL_KO.get(canonical_code, "판단 필요")
    summary_text = _disease_summary_text(canonical_code, risk_level)
    payload_json = _build_payload_json(
        label_ko=label_ko,
        summary_text=summary_text,
        evidence=evidence,
        recommended_action_code=action_code,
        risk_level=risk_level,
        possible_factors=_DISEASE_POSSIBLE_FACTORS.get(canonical_code, []),
    )
    return JudgmentInterpretation(
        canonical_code=canonical_code,
        risk_level=risk_level,
        recommended_action_code=action_code,
        requires_approval=requires_approval_for(action_code),
        payload_json=payload_json,
    )


def build_ripeness_interpretation(
    raw_label: str,
    confidence: float,
    *,
    extra_evidence: list[str] | None = None,
) -> JudgmentInterpretation:
    canonical_code = normalize_ripeness_label(raw_label)
    action_code = _RIPENESS_ACTIONS[canonical_code]
    evidence = [
        f"숙도 라벨 {canonical_code}",
        f"모델 신뢰도 {confidence:.2f}",
    ]
    if extra_evidence:
        evidence.extend(item for item in extra_evidence if item)

    label_ko = _RIPENESS_LABEL_KO[canonical_code]
    summary_text = _ripeness_summary_text(canonical_code)
    payload_json = _build_payload_json(
        label_ko=label_ko,
        summary_text=summary_text,
        evidence=evidence,
        recommended_action_code=action_code,
        risk_level="LOW",
        possible_factors=[],
    )
    return JudgmentInterpretation(
        canonical_code=canonical_code,
        risk_level="LOW",
        recommended_action_code=action_code,
        requires_approval=requires_approval_for(action_code),
        payload_json=payload_json,
    )


def build_harvest_decision_interpretation(
    *,
    disease_judgment: Any | None,
    ripeness_judgment: Any | None,
) -> JudgmentInterpretation | None:
    if disease_judgment is None and ripeness_judgment is None:
        return None

    disease_code = _get_value(disease_judgment, "canonical_code", "normal")
    disease_risk = _get_value(disease_judgment, "risk_level", "LOW")
    ripeness_code = _get_value(ripeness_judgment, "canonical_code", "")

    evidence: list[str] = []
    if disease_judgment is not None:
        evidence.append(f"질병 판단 {disease_code} / 위험도 {disease_risk or 'LOW'}")
    if ripeness_judgment is not None:
        evidence.append(f"숙도 판단 {ripeness_code}")

    if disease_risk == "HIGH":
        canonical_code = "harvest_hold"
        action_code = "HOLD_HARVEST"
        risk_level = "HIGH"
        label_ko = "수확 보류"
        summary_text = "질병 위험도가 높아 현재 수확을 보류합니다."
        decision_reason = "질병 위험도가 높아 수확보다 안전 확보와 재평가가 우선입니다."
    elif ripeness_code == "ripe" and disease_risk in {"", None, "LOW"}:
        canonical_code = "harvest_candidate"
        action_code = "HARVEST"
        risk_level = "LOW"
        label_ko = "수확 후보"
        summary_text = "숙도와 질병 상태를 함께 보면 수확 후보로 판단할 수 있습니다."
        decision_reason = "익음 상태이면서 질병 위험이 낮아 수확 진행 조건을 만족했습니다."
    elif ripeness_code == "turning":
        canonical_code = "reobserve"
        action_code = "REOBSERVE"
        risk_level = "LOW"
        label_ko = "재관측"
        summary_text = "착색이 진행 중이라 즉시 수확보다 재관측이 적절합니다."
        decision_reason = "숙도가 아직 진행 중이라 다음 관측 후 수확 여부를 판단해야 합니다."
    elif ripeness_code == "unripe":
        canonical_code = "harvest_hold"
        action_code = "HOLD_HARVEST"
        risk_level = "LOW"
        label_ko = "수확 보류"
        summary_text = "미숙 단계라 현재는 수확을 보류합니다."
        decision_reason = "미숙 상태라 수확 기준에 도달하지 않았습니다."
    elif ripeness_code == "ripe":
        canonical_code = "reobserve"
        action_code = "REOBSERVE"
        risk_level = "MEDIUM"
        label_ko = "재관측"
        summary_text = "익음 상태이지만 질병 위험을 더 확인한 뒤 수확 여부를 결정해야 합니다."
        decision_reason = "익음 상태이지만 질병 위험이 낮다고 보기 어려워 재확인이 필요합니다."
    else:
        canonical_code = "reobserve"
        action_code = "REOBSERVE"
        risk_level = "LOW"
        label_ko = "재관측"
        summary_text = "숙도 판단이 부족해 재관측 후 수확 여부를 결정합니다."
        evidence.append("숙도 판단이 아직 충분하지 않습니다.")
        decision_reason = "숙도 판단 정보가 부족해 보수적으로 재관측을 선택했습니다."

    payload_json = _build_payload_json(
        label_ko=label_ko,
        summary_text=summary_text,
        evidence=evidence,
        recommended_action_code=action_code,
        risk_level=risk_level,
        possible_factors=[],
    )
    payload_json["decision_reason"] = decision_reason
    payload_json["fusion_inputs"] = {
        "disease_canonical_code": disease_code,
        "disease_risk_level": disease_risk,
        "ripeness_canonical_code": ripeness_code,
    }
    return JudgmentInterpretation(
        canonical_code=canonical_code,
        risk_level=risk_level,
        recommended_action_code=action_code,
        requires_approval=requires_approval_for(action_code),
        payload_json=payload_json,
    )


def build_recheck_disease_interpretation(
    *,
    disease_judgment: Any | None,
    ripeness_judgment: Any | None,
    reason_text: str,
    evidence: list[str] | None = None,
) -> JudgmentInterpretation:
    disease_code = _get_value(disease_judgment, "canonical_code", "")
    ripeness_code = _get_value(ripeness_judgment, "canonical_code", "")
    summary_text = (
        "질병 판단 정보가 없어 현재 수확 판단 전에 질병을 다시 확인해야 합니다."
        if disease_judgment is None
        else "질병 판단 유효 시간이 지나 현재 수확 판단 전에 질병을 다시 확인해야 합니다."
    )
    payload_json = _build_payload_json(
        label_ko="질병 재확인 필요",
        summary_text=summary_text,
        evidence=evidence or [],
        recommended_action_code="RECHECK_DISEASE",
        risk_level="MEDIUM",
        possible_factors=["질병 관측 시간 경과", "개체 상태 변화 가능성"],
    )
    payload_json["decision_reason"] = reason_text
    payload_json["fusion_inputs"] = {
        "disease_canonical_code": disease_code,
        "ripeness_canonical_code": ripeness_code,
    }
    return JudgmentInterpretation(
        canonical_code="recheck_disease",
        risk_level="MEDIUM",
        recommended_action_code="RECHECK_DISEASE",
        requires_approval=False,
        payload_json=payload_json,
    )


def _disease_risk_level(canonical_code: str, confidence: float) -> str:
    if canonical_code in {"powdery_mildew", "gray_mold"}:
        if confidence >= 0.80:
            return "HIGH"
        if confidence >= 0.60:
            return "MEDIUM"
        return "LOW"
    if canonical_code in {"calcium_deficiency", "macro_npk_deficiency", "fruit_cracking"}:
        return "MEDIUM" if confidence >= 0.80 else "LOW"
    return "LOW"


def _disease_summary_text(canonical_code: str, risk_level: str | None) -> str:
    if canonical_code == "normal":
        return "현재 프레임에서 뚜렷한 병해 징후는 확인되지 않았습니다."
    if canonical_code == "powdery_mildew":
        return (
            f"흰가루병 의심 개체로 판단되어 위험도 {_risk_label_ko(risk_level)} "
            "수준으로 관리가 필요합니다."
        )
    if canonical_code == "gray_mold":
        return (
            f"잿빛곰팡이병 의심 개체로 판단되어 위험도 {_risk_label_ko(risk_level)} "
            "수준으로 재확인이 필요합니다."
        )
    if canonical_code == "fruit_cracking":
        return "열과가 의심되어 즉시 분사보다 재배 환경과 과실 상태 점검이 우선입니다."
    if canonical_code == "calcium_deficiency":
        return "칼슘 결핍 의심 징후가 있어 영양 상태를 점검하는 것이 좋습니다."
    if canonical_code == "macro_npk_deficiency":
        return "다량원소 결핍 의심 징후가 있어 양액과 비료 공급 상태를 확인해야 합니다."
    return "추가 해석이 필요한 AI 판단입니다."


def _ripeness_summary_text(canonical_code: str) -> str:
    if canonical_code == "ripe":
        return "익음 상태가 확인되어 수확 후보로 판단했습니다."
    if canonical_code == "turning":
        return "착색 진행 단계로 보여 조금 더 관찰하는 편이 좋습니다."
    return "미숙 단계라 아직 수확 시점은 아닙니다."


def _build_payload_json(
    *,
    label_ko: str,
    summary_text: str,
    evidence: list[str],
    recommended_action_code: str,
    risk_level: str | None,
    possible_factors: list[str],
) -> dict[str, Any]:
    return {
        "label_ko": label_ko,
        "summary_text": summary_text,
        "evidence": evidence,
        "possible_factors": possible_factors,
        "risk_level": risk_level,
        "risk_label_ko": _risk_label_ko(risk_level),
        "recommended_action": {
            "code": recommended_action_code,
            "label_ko": _ACTION_LABELS_KO.get(recommended_action_code, recommended_action_code),
            "requires_approval": requires_approval_for(recommended_action_code),
        },
    }


def _risk_label_ko(risk_level: str | None) -> str:
    if risk_level is None:
        return ""
    return _RISK_LABELS_KO.get(risk_level, risk_level)


def _get_value(target: Any | None, field_name: str, default: Any) -> Any:
    if target is None:
        return default
    if hasattr(target, field_name):
        return getattr(target, field_name)
    if isinstance(target, dict):
        return target.get(field_name, default)
    return default
