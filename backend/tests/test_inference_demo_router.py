from __future__ import annotations

import base64
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routers import inference
from services.perception.schemas import ThinInferenceConfirmResponse


def test_confirm_demo_diagnosis_uses_manifest_preliminary_label(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "healthy-demo.jpg"
    image_path.write_bytes(b"fake-image-bytes")

    monkeypatch.setattr(
        inference,
        "_resolve_demo_input",
        lambda plant_id: {
            "image_path": image_path,
            "fruit_id": "farm01_plant_18_tomato_01",
            "preliminary_label": "healthy_leaf",
            "preliminary_confidence": 0.95,
        },
    )

    captured: dict[str, object] = {}

    def _fake_confirm_detection(request):
        captured["request"] = request
        return ThinInferenceConfirmResponse(
            observation_id="demo-observation",
            preliminary_label=request.preliminary_label,
            preliminary_confidence=request.preliminary_confidence,
            final_label="healthy_leaf",
            final_confidence=0.95,
            image_path=str(image_path),
            reviewed_at="2026-03-27T00:00:00+00:00",
            decision_source="preliminary_fallback",
            treatment_plan=None,
            dispatch_result=None,
        )

    monkeypatch.setattr(inference._service, "confirm_detection", _fake_confirm_detection)

    response = inference.confirm_demo_diagnosis(
        inference.DemoDiagnosisRequest(
            plant_id="farm01_plant_18",
            requested_by="pytest",
            auto_execute_treatment=False,
        )
    )

    assert response.final_label == "healthy_leaf"
    request = captured["request"]
    assert request.preliminary_label == "healthy_leaf"
    assert request.preliminary_confidence == 0.95
    assert request.fruit_id == "farm01_plant_18_tomato_01"
    assert base64.b64decode(request.image_base64) == b"fake-image-bytes"
