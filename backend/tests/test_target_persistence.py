from __future__ import annotations

import base64
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.actuation.schemas import Point3D
from services.actuation.schemas import ActuationDispatchResult
from services.perception.inference_service import MainInferenceService
from services.perception.schemas import ThinInferenceConfirmRequest


class _DummyPersistenceService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def persist_confirmation(self, **kwargs):
        self.calls.append(kwargs)

        class _Refs:
            robot_row_id = 1
            zone_row_id = 2
            plant_row_id = 3
            crop_observation_row_id = 4
            actuation_log_row_id = 5

        return _Refs()


def test_confirm_detection_uses_test_override_and_persists(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv('AGRIBOT_BACKEND_RUNTIME_DIR', str(tmp_path))
    service = MainInferenceService()

    def _fail_if_infer_called(image_path):
        raise AssertionError(f'_infer should not run during test_override flow: {image_path}')

    service._infer = _fail_if_infer_called  # type: ignore[method-assign]
    service._treatment_dispatcher.dispatch_plan = lambda *args, **kwargs: ActuationDispatchResult(  # type: ignore[method-assign]
        dispatched=True,
        status='completed',
        command_id='cmd-1',
        topic='/iot/commands/manual',
        device_id='sprinkler_0',
        device_type='sprinkler',
        method='ros2_cli',
        detail_message='ok',
    )
    dummy_persistence = _DummyPersistenceService()
    service._persistence_service = dummy_persistence

    request = ThinInferenceConfirmRequest(
        observation_id='override-test',
        robot_id='agribot',
        zone_id='farm_01',
        plant_id='farm01_plant_10',
        target_position=Point3D(x=-6.0, y=-6.0, z=0.75),
        requested_by='pytest',
        preliminary_label='tomato_gray_mold',
        preliminary_confidence=0.2,
        test_override_final_label='tomato_powdery_mildew',
        test_override_final_confidence=0.97,
        image_base64=base64.b64encode(b'fake-image-bytes').decode('ascii'),
        image_format='jpg',
    )

    response = service.confirm_detection(request)

    assert response.final_label == 'tomato_powdery_mildew'
    assert response.decision_source == 'test_override'
    assert len(dummy_persistence.calls) == 1
    persisted = dummy_persistence.calls[0]
    assert persisted['final_label'] == 'tomato_powdery_mildew'
    assert persisted['request'].plant_id == 'farm01_plant_10'
