from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agribot_perception import model_runner


def test_normalize_detection_label_maps_ai_branch_labels_to_canonical_names() -> None:
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
    parsed = model_runner.parse_label_list(' Gray Mold, healthy_leaf, Tomato-Powdery-Mildew ')

    assert parsed == {
        'gray_mold',
        'healthy_leaf',
        'tomato_powdery_mildew',
    }


def test_resolve_inference_device_uses_cuda_when_available(monkeypatch) -> None:
    monkeypatch.setattr(model_runner, '_cuda_available', lambda: True)

    assert model_runner.resolve_inference_device('auto') == 'cuda:0'


def test_resolve_inference_device_falls_back_to_cpu_when_cuda_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(model_runner, '_cuda_available', lambda: False)

    assert model_runner.resolve_inference_device('auto') == 'cpu'
