# 이 테스트는 인지와 추론 패키지의 model runner 동작을 검증한다.
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agribot_perception import model_runner


def test_normalize_detection_label_maps_ai_branch_labels_to_canonical_names() -> None:
    # normalize detection 라벨 지도 목록 AI branch 라벨 목록 TO canonical 이름 목록 동작과 회귀 여부를 검증한다.
    assert (
        model_runner.normalize_detection_label('gray_mold')
        == 'tomato_gray_mold_disease'
    )
    assert (
        model_runner.normalize_detection_label('powdery mildew')
        == 'tomato_powdery_mildew_disease'
    )
    assert (
        model_runner.normalize_detection_label('fruit_cracking')
        == 'tomato_fruit_cracking_disease'
    )
    assert (
        model_runner.normalize_detection_label('calcium_deficiency')
        == 'tomato_calcium_deficiency_disease'
    )
    assert (
        model_runner.normalize_detection_label('response_powdery_mildew')
        == 'tomato_powdery_mildew_disease'
    )


def test_parse_label_list_normalizes_case_and_spacing() -> None:
    # parse 라벨 list normalizes case AND spacing 동작과 회귀 여부를 검증한다.
    parsed = model_runner.parse_label_list(' Gray Mold, healthy_leaf, Tomato-Powdery-Mildew ')

    assert parsed == {
        'gray_mold',
        'healthy_leaf',
        'tomato_powdery_mildew',
    }


def test_resolve_inference_device_uses_cuda_when_available(monkeypatch) -> None:
    # resolve inference 장치 uses cuda when 사용 가능 상태 동작과 회귀 여부를 검증한다.
    monkeypatch.setattr(model_runner, '_cuda_available', lambda: True)

    assert model_runner.resolve_inference_device('auto') == 'cuda:0'


def test_resolve_inference_device_falls_back_to_cpu_when_cuda_is_unavailable(monkeypatch) -> None:
    # resolve inference 장치 falls back TO CPU when cuda IS unavailable 동작과 회귀 여부를 검증한다.
    monkeypatch.setattr(model_runner, '_cuda_available', lambda: False)

    assert model_runner.resolve_inference_device('auto') == 'cpu'
