# 이 테스트는 백엔드의 treatment rule engine 동작과 회귀 여부를 검증한다.
from __future__ import annotations

import base64
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.actuation.rule_engine import DiseaseTreatmentRuleEngine
from services.actuation.schemas import Point3D
from services.perception.inference_service import MainInferenceService
from services.perception.schemas import ThinInferenceConfirmRequest


class _DummyPersistenceService:
    # 테스트용 저장 서비스 관련 핵심 흐름을 한곳에 모아 제공하는 서비스 클래스다.
    def persist_confirmation(self, **kwargs):
        # confirmation을 저장한다.
        del kwargs

        class _Refs:
            # refs 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
            robot_row_id = 1
            zone_row_id = 2
            plant_row_id = 3
            crop_observation_row_id = 4
            actuation_log_row_id = None

        return _Refs()


def test_powdery_mildew_selects_nearest_sprinkler() -> None:
    # powdery mildew selects nearest sprinkler 동작과 회귀 여부를 검증한다.
    engine = DiseaseTreatmentRuleEngine()

    plan = engine.evaluate(
        disease_label='tomato_powdery_mildew',
        zone_id='greenhouse_01',
        target_position=Point3D(x=8.0, y=2.0, z=0.05),
    )

    assert plan.action_required is True
    assert plan.status == 'ready'
    assert plan.treatment_type == 'pesticide_spray'
    assert plan.effect_color == 'red'
    assert plan.selected_sprinkler is not None
    assert plan.selected_sprinkler.device_id == 'sprinkler_3'
    assert plan.command_payload is not None
    assert plan.command_payload['command_type'] == 'spray_pesticide'


def test_column_aligned_plant_prefers_same_column_sprinkler() -> None:
    # column aligned 작물 개체 prefers same column sprinkler 동작과 회귀 여부를 검증한다.
    engine = DiseaseTreatmentRuleEngine()

    plan = engine.evaluate(
        disease_label='tomato_powdery_mildew_disease',
        zone_id='farm_01',
        target_position=Point3D(x=-2.0, y=4.0, z=0.75),
    )

    assert plan.action_required is True
    assert plan.status == 'ready'
    assert plan.selected_sprinkler is not None
    assert plan.selected_sprinkler.device_id == 'sprinkler_1'


def test_calcium_deficiency_without_position_waits_for_target() -> None:
    # calcium deficiency without 위치 waits FOR target 동작과 회귀 여부를 검증한다.
    engine = DiseaseTreatmentRuleEngine()

    plan = engine.evaluate(
        disease_label='tomato_calcium_deficiency',
        zone_id='farm_01',
        target_position=None,
    )

    assert plan.action_required is True
    assert plan.status == 'awaiting_target_position'
    assert plan.effect_color == 'yellow'
    assert plan.selected_sprinkler is None


def test_gray_mold_is_no_action() -> None:
    # gray mold IS NO action 동작과 회귀 여부를 검증한다.
    engine = DiseaseTreatmentRuleEngine()

    plan = engine.evaluate(
        disease_label='tomato_gray_mold',
        zone_id='farm_01',
        target_position=Point3D(x=4.0, y=3.0, z=0.05),
    )

    assert plan.action_required is False
    assert plan.status == 'no_action'
    assert plan.selected_sprinkler is None


def test_confirm_detection_embeds_treatment_plan(tmp_path, monkeypatch) -> None:
    # confirm detection embeds 처치 계획 동작과 회귀 여부를 검증한다.
    monkeypatch.setenv('AGRIBOT_BACKEND_RUNTIME_DIR', str(tmp_path))
    service = MainInferenceService()
    service._infer = lambda image_path: []  # type: ignore[method-assign]
    service._persistence_service = _DummyPersistenceService()

    request = ThinInferenceConfirmRequest(
        observation_id='rule-engine-test',
        zone_id='greenhouse_01',
        target_position=Point3D(x=8.0, y=2.0, z=0.05),
        auto_execute_treatment=False,
        preliminary_label='powdery_mildew',
        preliminary_confidence=0.81,
        image_base64=base64.b64encode(b'fake-image-bytes').decode('ascii'),
        image_format='jpg',
    )

    response = service.confirm_detection(request)

    assert response.preliminary_label == 'tomato_powdery_mildew_disease'
    assert response.final_label == 'tomato_powdery_mildew_disease'
    assert response.treatment_plan is not None
    assert response.treatment_plan.action_required is True
    assert response.treatment_plan.effect_color == 'red'
    assert response.treatment_plan.selected_sprinkler is not None
    assert response.treatment_plan.selected_sprinkler.device_id == 'sprinkler_3'
    assert response.dispatch_result is not None
    assert response.dispatch_result.status == 'skipped_auto_execute'


def test_treatment_rule_engine_accepts_standardized_disease_suffix() -> None:
    # 처치 rule engine accepts standardized disease suffix 동작과 회귀 여부를 검증한다.
    engine = DiseaseTreatmentRuleEngine()

    plan = engine.evaluate(
        disease_label='tomato_calcium_deficiency_disease',
        zone_id='farm_01',
        target_position=Point3D(x=4.0, y=3.0, z=0.05),
    )

    assert plan.action_required is True
    assert plan.status == 'ready'
    assert plan.treatment_type == 'calcium_solution_spray'
