# 이 모듈은 AI 판정 계층에서 AI 판정 결과를 읽고 조합하는 서비스 로직을 제공한다.
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from database import SessionLocal
from models import AiJudgment

from .policy import (
    build_disease_interpretation,
    build_harvest_decision_interpretation,
    build_recheck_disease_interpretation,
    build_ripeness_interpretation,
)
from .schemas import (
    AiJudgmentRecordOut,
    AiJudgmentHistoryOut,
    BulkHarvestDecisionRequest,
    BulkHarvestDecisionResponse,
    HarvestActionScope,
    HarvestDecisionActionOut,
    HarvestDecisionActionRequest,
    RipenessJudgmentCreateRequest,
    RipenessJudgmentCreateResponse,
)


DEFAULT_DISEASE_MODEL_NAME = "tomato_disease_detector"
DEFAULT_DISEASE_MODEL_VERSION = "v1"
DEFAULT_HARVEST_MODEL_NAME = "harvest_decision_fusion"
DEFAULT_HARVEST_MODEL_VERSION = "v1"
DISEASE_VALIDITY_WINDOW_BY_SCOPE = {
    "INDIVIDUAL": 5 * 60,
    "BULK": 10 * 60,
}


class AiJudgmentService:
    # AI 판정 서비스 관련 핵심 흐름을 한곳에 모아 제공하는 서비스 클래스다.
    def get_latest_judgment(
        self,
        *,
        plant_id: str = "",
        fruit_id: str = "",
        judgment_type: str | None = None,
    ) -> AiJudgmentRecordOut | None:
        # latest 판정 결과를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        normalized_plant_id = _normalize_optional_id(plant_id)
        normalized_fruit_id = _normalize_optional_id(fruit_id)
        _ensure_target_identifier(normalized_plant_id, normalized_fruit_id)
        db = SessionLocal()
        try:
            record = self._get_latest_judgment(
                db,
                judgment_type=judgment_type,
                plant_id=normalized_plant_id or "",
                fruit_id=normalized_fruit_id or "",
            )
            return None if record is None else _serialize_judgment(record)
        finally:
            db.close()

    def get_judgment_history(
        self,
        *,
        plant_id: str = "",
        fruit_id: str = "",
        judgment_type: str | None = None,
        limit: int = 20,
    ) -> AiJudgmentHistoryOut:
        # 판정 결과 이력를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        normalized_plant_id = _normalize_optional_id(plant_id)
        normalized_fruit_id = _normalize_optional_id(fruit_id)
        _ensure_target_identifier(normalized_plant_id, normalized_fruit_id)
        db = SessionLocal()
        try:
            items = [
                _serialize_judgment(record)
                for record in self._query_judgments(
                    db,
                    plant_id=normalized_plant_id or "",
                    fruit_id=normalized_fruit_id or "",
                    judgment_type=judgment_type,
                    limit=limit,
                )
            ]
            return AiJudgmentHistoryOut(items=items)
        finally:
            db.close()

    def create_disease_judgment(
        self,
        *,
        db: Session | None = None,
        plant_id: str = "",
        fruit_id: str = "",
        zone_id: str = "",
        model_name: str = DEFAULT_DISEASE_MODEL_NAME,
        model_version: str = DEFAULT_DISEASE_MODEL_VERSION,
        raw_label: str,
        confidence: float,
        image_url: str = "",
        created_at: datetime | None = None,
        evidence: list[str] | None = None,
    ) -> AiJudgmentRecordOut:
        # disease 판정 결과를 새로 만들어 다음 처리 단계로 넘긴다.
        interpretation = build_disease_interpretation(
            raw_label,
            confidence,
            extra_evidence=evidence,
        )
        return self._store_judgment(
            db=db,
            plant_id=plant_id,
            fruit_id=fruit_id,
            zone_id=zone_id,
            judgment_type="DISEASE",
            model_name=model_name,
            model_version=model_version,
            raw_label=raw_label,
            confidence=confidence,
            image_url=image_url,
            created_at=created_at,
            interpretation=interpretation,
        )

    def create_ripeness_judgment(
        self,
        *,
        db: Session | None = None,
        plant_id: str = "",
        fruit_id: str = "",
        zone_id: str = "",
        model_name: str,
        model_version: str,
        raw_label: str,
        confidence: float,
        image_url: str = "",
        created_at: datetime | None = None,
        evidence: list[str] | None = None,
    ) -> AiJudgmentRecordOut:
        # ripeness 판정 결과를 새로 만들어 다음 처리 단계로 넘긴다.
        interpretation = build_ripeness_interpretation(
            raw_label,
            confidence,
            extra_evidence=evidence,
        )
        return self._store_judgment(
            db=db,
            plant_id=plant_id,
            fruit_id=fruit_id,
            zone_id=zone_id,
            judgment_type="RIPENESS",
            model_name=model_name,
            model_version=model_version,
            raw_label=raw_label,
            confidence=confidence,
            image_url=image_url,
            created_at=created_at,
            interpretation=interpretation,
        )

    def maybe_create_harvest_decision(
        self,
        *,
        db: Session | None = None,
        plant_id: str = "",
        fruit_id: str = "",
        zone_id: str = "",
        model_name: str = DEFAULT_HARVEST_MODEL_NAME,
        model_version: str = DEFAULT_HARVEST_MODEL_VERSION,
        created_at: datetime | None = None,
        scope: HarvestActionScope = "INDIVIDUAL",
    ) -> AiJudgmentRecordOut | None:
        # maybe 생성 수확 decision 정보를 계산해 반환한다.
        owned_db = db is None
        session = db or SessionLocal()
        try:
            normalized_plant_id = _normalize_optional_id(plant_id)
            normalized_fruit_id = _normalize_optional_id(fruit_id)
            normalized_zone_id = _normalize_optional_id(zone_id)
            reference_time = _coerce_created_at(created_at)
            latest_ripeness = self._get_latest_judgment(
                session,
                judgment_type="RIPENESS",
                plant_id=normalized_plant_id or "",
                fruit_id=normalized_fruit_id or "",
            )
            if latest_ripeness is None:
                if owned_db:
                    session.rollback()
                return None

            latest_disease = self._get_latest_judgment(
                session,
                judgment_type="DISEASE",
                plant_id=normalized_plant_id or "",
                fruit_id=normalized_fruit_id or "",
            )
            disease_valid_window_seconds = DISEASE_VALIDITY_WINDOW_BY_SCOPE[scope]
            disease_valid, disease_age_seconds = _assess_disease_validity(
                latest_disease,
                reference_time=reference_time,
                window_seconds=disease_valid_window_seconds,
            )
            if latest_disease is None or not disease_valid:
                reason_text = (
                    "질병 판단이 아직 없어서 수확 전 질병 재확인이 필요합니다."
                    if latest_disease is None
                    else "질병 판단 유효 시간이 지나 수확 전 질병 재확인이 필요합니다."
                )
                evidence = [
                    f"적용 유효 시간 {disease_valid_window_seconds}초",
                    f"현재 scope {scope}",
                ]
                if disease_age_seconds is not None:
                    evidence.append(f"마지막 질병 판단 경과 {disease_age_seconds}초")
                interpretation = build_recheck_disease_interpretation(
                    disease_judgment=latest_disease,
                    ripeness_judgment=latest_ripeness,
                    reason_text=reason_text,
                    evidence=evidence,
                )
            else:
                interpretation = build_harvest_decision_interpretation(
                    disease_judgment=latest_disease,
                    ripeness_judgment=latest_ripeness,
                )
                if interpretation is None:
                    if owned_db:
                        session.rollback()
                    return None

            serialized = self._store_judgment(
                db=session,
                plant_id=normalized_plant_id or _read_value(latest_ripeness, "plant_id"),
                fruit_id=normalized_fruit_id or _read_value(latest_ripeness, "fruit_id"),
                zone_id=normalized_zone_id or _read_value(latest_ripeness, "zone_id"),
                judgment_type="HARVEST_DECISION",
                model_name=model_name,
                model_version=model_version,
                raw_label=interpretation.canonical_code,
                confidence=_derive_harvest_confidence(
                    disease_judgment=latest_disease if disease_valid else None,
                    ripeness_judgment=latest_ripeness,
                ),
                image_url=_read_value(latest_ripeness, "image_url"),
                created_at=reference_time,
                interpretation=interpretation,
            )
            if owned_db:
                session.commit()
            return serialized
        except Exception:
            if owned_db:
                session.rollback()
            raise
        finally:
            if owned_db:
                session.close()

    def create_ripeness_and_fuse(
        self,
        request: RipenessJudgmentCreateRequest,
    ) -> RipenessJudgmentCreateResponse:
        # ripeness AND fuse를 새로 만들어 다음 처리 단계로 넘긴다.
        db = SessionLocal()
        try:
            ripeness_judgment = self.create_ripeness_judgment(
                db=db,
                plant_id=request.plant_id,
                fruit_id=request.fruit_id,
                zone_id=request.zone_id,
                model_name=request.model_name,
                model_version=request.model_version,
                raw_label=request.raw_label,
                confidence=request.confidence,
                image_url=request.image_url,
                evidence=request.evidence,
            )
            harvest_decision = self.maybe_create_harvest_decision(
                db=db,
                plant_id=request.plant_id,
                fruit_id=request.fruit_id,
                zone_id=request.zone_id,
            )
            db.commit()
            return RipenessJudgmentCreateResponse(
                ripeness_judgment=ripeness_judgment,
                harvest_decision=harvest_decision,
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create_individual_harvest_action(
        self,
        request: HarvestDecisionActionRequest,
    ) -> HarvestDecisionActionOut:
        # individual harvest action를 새로 만들어 다음 처리 단계로 넘긴다.
        return self._create_harvest_action(
            request=request,
            scope="INDIVIDUAL",
        )

    def create_bulk_harvest_action(
        self,
        request: BulkHarvestDecisionRequest,
    ) -> BulkHarvestDecisionResponse:
        # bulk harvest action를 새로 만들어 다음 처리 단계로 넘긴다.
        items = []
        for target in request.targets:
            effective_request = HarvestDecisionActionRequest(
                plant_id=target.plant_id,
                fruit_id=target.fruit_id,
                zone_id=target.zone_id,
                requested_by=target.requested_by or request.requested_by,
            )
            items.append(
                self._create_harvest_action(
                    request=effective_request,
                    scope="BULK",
                )
            )
        return BulkHarvestDecisionResponse(items=items)

    def _create_harvest_action(
        self,
        *,
        request: HarvestDecisionActionRequest,
        scope: HarvestActionScope,
    ) -> HarvestDecisionActionOut:
        # harvest action를 새로 만들어 다음 처리 단계로 넘긴다.
        normalized_plant_id = _normalize_optional_id(request.plant_id)
        normalized_fruit_id = _normalize_optional_id(request.fruit_id)
        normalized_zone_id = _normalize_optional_id(request.zone_id)
        _ensure_target_identifier(normalized_plant_id, normalized_fruit_id)

        db = SessionLocal()
        try:
            reference_time = _coerce_created_at(None)
            ripeness = self._get_latest_judgment(
                db,
                judgment_type="RIPENESS",
                plant_id=normalized_plant_id or "",
                fruit_id=normalized_fruit_id or "",
            )
            if ripeness is None:
                raise ValueError("최신 ripeness judgment가 없습니다. 먼저 숙도 판단을 저장해야 합니다.")

            disease = self._get_latest_judgment(
                db,
                judgment_type="DISEASE",
                plant_id=normalized_plant_id or "",
                fruit_id=normalized_fruit_id or "",
            )
            disease_valid_window_seconds = DISEASE_VALIDITY_WINDOW_BY_SCOPE[scope]
            disease_valid, disease_age_seconds = _assess_disease_validity(
                disease,
                reference_time=reference_time,
                window_seconds=disease_valid_window_seconds,
            )

            if disease is None or not disease_valid:
                reason_text = (
                    "질병 판단이 아직 없어서 수확 전 질병 재확인이 필요합니다."
                    if disease is None
                    else "질병 판단 유효 시간이 지나 수확 전 질병 재확인이 필요합니다."
                )
                evidence = [
                    f"적용 유효 시간 {disease_valid_window_seconds}초",
                    f"현재 scope {scope}",
                ]
                if disease_age_seconds is not None:
                    evidence.append(f"마지막 질병 판단 경과 {disease_age_seconds}초")
                interpretation = build_recheck_disease_interpretation(
                    disease_judgment=disease,
                    ripeness_judgment=ripeness,
                    reason_text=reason_text,
                    evidence=evidence,
                )
            else:
                interpretation = build_harvest_decision_interpretation(
                    disease_judgment=disease,
                    ripeness_judgment=ripeness,
                )
                if interpretation is None:
                    raise ValueError("harvest decision을 생성할 수 없습니다.")

            harvest_decision = self._store_judgment(
                db=db,
                plant_id=normalized_plant_id or _read_value(ripeness, "plant_id"),
                fruit_id=normalized_fruit_id or _read_value(ripeness, "fruit_id"),
                zone_id=normalized_zone_id or _read_value(ripeness, "zone_id"),
                judgment_type="HARVEST_DECISION",
                model_name=DEFAULT_HARVEST_MODEL_NAME,
                model_version=DEFAULT_HARVEST_MODEL_VERSION,
                raw_label=interpretation.canonical_code,
                confidence=_derive_harvest_confidence(
                    disease_judgment=disease if disease_valid else None,
                    ripeness_judgment=ripeness,
                ),
                image_url=_read_value(ripeness, "image_url"),
                created_at=reference_time,
                interpretation=interpretation,
            )
            db.commit()
            return HarvestDecisionActionOut(
                scope=scope,
                plant_id=harvest_decision.plant_id,
                fruit_id=harvest_decision.fruit_id,
                zone_id=harvest_decision.zone_id,
                disease_judgment=None if disease is None else _serialize_judgment(disease),
                ripeness_judgment=_serialize_judgment(ripeness),
                harvest_decision=harvest_decision,
                disease_valid=bool(disease_valid),
                disease_age_seconds=disease_age_seconds,
                disease_valid_window_seconds=disease_valid_window_seconds,
            )
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _store_judgment(
        self,
        *,
        db: Session | None,
        plant_id: str,
        fruit_id: str,
        zone_id: str,
        judgment_type: str,
        model_name: str,
        model_version: str,
        raw_label: str,
        confidence: float,
        image_url: str,
        created_at: datetime | None,
        interpretation: Any,
    ) -> AiJudgmentRecordOut:
        # judgment을 저장한다.
        owned_db = db is None
        session = db or SessionLocal()
        try:
            record = AiJudgment(
                plant_id=_normalize_optional_id(plant_id),
                fruit_id=_normalize_optional_id(fruit_id),
                zone_id=_normalize_optional_id(zone_id),
                judgment_type=judgment_type,
                model_name=model_name,
                model_version=model_version,
                raw_label=raw_label.strip(),
                canonical_code=interpretation.canonical_code,
                confidence=float(confidence),
                risk_level=interpretation.risk_level,
                recommended_action_code=interpretation.recommended_action_code,
                requires_approval=interpretation.requires_approval,
                payload_json=interpretation.payload_json,
                image_url=_normalize_optional_id(image_url),
                created_at=_coerce_created_at(created_at),
            )
            session.add(record)
            session.flush()

            serialized = _serialize_judgment(record)
            if owned_db:
                session.commit()
            return serialized
        except Exception:
            if owned_db:
                session.rollback()
            raise
        finally:
            if owned_db:
                session.close()

    def _get_latest_judgment(
        self,
        db: Session,
        *,
        judgment_type: str | None,
        plant_id: str = "",
        fruit_id: str = "",
    ) -> AiJudgment | None:
        # latest 판정 결과를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        items = self._query_judgments(
            db,
            plant_id=plant_id,
            fruit_id=fruit_id,
            judgment_type=judgment_type,
            limit=1,
        )
        return items[0] if items else None

    def _query_judgments(
        self,
        db: Session,
        *,
        plant_id: str = "",
        fruit_id: str = "",
        judgment_type: str | None = None,
        limit: int = 20,
    ) -> list[AiJudgment]:
        # 조회 judgments 정보를 계산해 반환한다.
        normalized_fruit_id = _normalize_optional_id(fruit_id)
        normalized_plant_id = _normalize_optional_id(plant_id)
        normalized_limit = max(1, min(int(limit), 200))

        if normalized_fruit_id:
            query = db.query(AiJudgment).filter(AiJudgment.fruit_id == normalized_fruit_id)
        elif normalized_plant_id:
            query = db.query(AiJudgment).filter(AiJudgment.plant_id == normalized_plant_id)
        else:
            query = db.query(AiJudgment)

        if judgment_type:
            query = query.filter(AiJudgment.judgment_type == judgment_type)

        return query.order_by(AiJudgment.created_at.desc()).limit(normalized_limit).all()


def _serialize_judgment(record: AiJudgment) -> AiJudgmentRecordOut:
    # 판정 결과를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    return AiJudgmentRecordOut(
        id=str(record.id),
        plant_id=record.plant_id,
        fruit_id=record.fruit_id,
        zone_id=record.zone_id,
        judgment_type=record.judgment_type,
        model_name=record.model_name,
        model_version=record.model_version,
        raw_label=record.raw_label,
        canonical_code=record.canonical_code,
        confidence=float(record.confidence),
        risk_level=record.risk_level,
        recommended_action_code=record.recommended_action_code,
        requires_approval=bool(record.requires_approval),
        payload_json=dict(record.payload_json or {}),
        image_url=record.image_url,
        created_at=_coerce_created_at(record.created_at).isoformat(),
    )


def _normalize_optional_id(value: str | None) -> str | None:
    # optional ID를 다른 계층에서 쓰기 쉬운 형태로 변환한다.
    normalized = str(value or "").strip()
    return normalized or None


def _ensure_target_identifier(
    plant_id: str | None,
    fruit_id: str | None,
) -> None:
    # target identifier가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
    if plant_id is None and fruit_id is None:
        raise ValueError("plant_id 또는 fruit_id 중 하나는 필요합니다.")


def _assess_disease_validity(
    judgment: AiJudgment | None,
    *,
    reference_time: datetime,
    window_seconds: int,
) -> tuple[bool, int | None]:
    # assess disease validity 정보를 계산해 반환한다.
    if judgment is None:
        return False, None

    judgment_time = _coerce_created_at(judgment.created_at)
    age_seconds = max(0, int((reference_time - judgment_time).total_seconds()))
    return age_seconds <= window_seconds, age_seconds


def _derive_harvest_confidence(
    *,
    disease_judgment: AiJudgment | None,
    ripeness_judgment: AiJudgment,
) -> float:
    # derive 수확 confidence 정보를 계산해 반환한다.
    ripeness_confidence = float(ripeness_judgment.confidence or 0.0)
    if disease_judgment is None:
        return ripeness_confidence
    disease_confidence = float(disease_judgment.confidence or 0.0)
    return min(ripeness_confidence, disease_confidence)


def _coerce_created_at(value: datetime | None) -> datetime:
    # coerce created at 정보를 계산해 반환한다.
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _read_value(target: Any, field_name: str) -> str:
    # value를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    if hasattr(target, field_name):
        value = getattr(target, field_name)
        return "" if value is None else str(value)
    if isinstance(target, dict):
        value = target.get(field_name)
        return "" if value is None else str(value)
    return ""
