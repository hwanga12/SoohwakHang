# Shared Tomato Disease Model

이 폴더는 병해 진단 런타임이 함께 쓰는 공용 계약입니다.

기본 파일:
- `best.pt`: 병해 YOLO 가중치
- `label_contract.json`: 라벨 표준화와 backend rule alias 계약
- `samples/597124_20211019_2_1_a5_3_2_12_2_75.jpg`: 최소 실행 검증용 샘플 이미지

두 런타임은 같은 가중치와 같은 라벨 계약을 읽습니다.
- ROS thin inference: `agribot_perception.thin_inference_node`
- Backend confirmation: `POST /api/v1/inference/confirm`

기본 모델 경로:
- `artifacts/models/tomato_disease/v1/best.pt`

환경 변수:
- `AGRIBOT_TOMATO_DISEASE_MODEL_PATH`: 기본 경로 대신 다른 모델 파일을 쓸 때 사용
- `AGRIBOT_TOMATO_DISEASE_DEVICE`: `auto`, `cpu`, `cuda:0` 같은 추론 디바이스 지정
- 이전 이름인 `AGRIBOT_TOMATO_MODEL_PATH`도 하위 호환으로 계속 읽습니다.

GPU 사용 권장:
- `AGRIBOT_TOMATO_DISEASE_DEVICE=auto`가 기본입니다.
- CUDA를 사용할 수 있으면 자동으로 `cuda:0`를 고르고, 아니면 `cpu`로 내려갑니다.
- 팀원 PC에서도 같은 결과를 내려면 먼저 PyTorch CUDA 환경을 맞춘 뒤 `ultralytics`를 설치하세요.

검증 예시:
```bash
cd /home/ssafy/SSAFY/S14P21A602
export AGRIBOT_TOMATO_DISEASE_DEVICE=auto
backend/.venv/bin/python - <<'PY'
import base64
from pathlib import Path
import sys

sys.path.insert(0, '/home/ssafy/SSAFY/S14P21A602/backend')

from services.perception.inference_service import MainInferenceService
from services.perception.schemas import ThinInferenceConfirmRequest

class DummyPersistence:
    def persist_confirmation(self, **kwargs):
        class Refs:
            robot_row_id = 1
            zone_row_id = 1
            plant_row_id = 1
            crop_observation_row_id = 1
            actuation_log_row_id = None
        return Refs()

service = MainInferenceService()
service._persistence_service = DummyPersistence()
sample_path = Path('artifacts/models/tomato_disease/v1/samples/597124_20211019_2_1_a5_3_2_12_2_75.jpg')
request = ThinInferenceConfirmRequest(
    observation_id='readme-sample',
    robot_id='agribot',
    zone_id='greenhouse_01',
    plant_id='farm01_plant_06',
    requested_by='readme',
    preliminary_label='tomato_gray_mold_disease',
    preliminary_confidence=0.9,
    image_base64=base64.b64encode(sample_path.read_bytes()).decode('ascii'),
    image_format='jpg',
)
response = service.confirm_detection(request)
print(response.final_label, response.final_confidence, response.decision_source)
PY
```
