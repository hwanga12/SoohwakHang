# Environment / Disease Rulebook

`S14P-406` 기준선용 규칙표입니다.  
목적은 환경 센서값과 병해 관측 결과를 보고 어떤 장치를 우선 후보로 올릴지 팀 내 기준을 통일하는 것입니다.

## 적용 범위

- 입력
  - 토양 수분 `soil_moisture`
  - 온도 `temperature`
  - 습도 `humidity`
  - 조도 `light_level`
  - 병해 관측 라벨 `class_name`, `disease_name`
  - 반복 관측 횟수 `repeat_count`
  - 성장 단계 `growth_stage`
- 출력
  - 급수 `watering`
  - 천장 커튼 `curtain`
  - 환기팬 `fan`
  - 영양제 `nutrient`
  - 급수 보류 `hold_watering`

## 규칙표

| Rule ID | 조건 | 권장 장치/동작 | 실행 방식 | 이유 |
| --- | --- | --- | --- | --- |
| `R-WATER-LOW-SOIL-AUTO` | `soil_moisture < 22` | 급수 `900 ml` | 자동 실행 | 토양 수분이 매우 낮아 즉시 보완 필요 |
| `R-WATER-MID-SOIL-REVIEW` | `22 <= soil_moisture < 30` | 급수 `600 ml` | 승인 후 실행 | 마른 편이지만 과급수 위험을 피하기 위해 사람 확인 우선 |
| `R-CURTAIN-HOT-BRIGHT-STRONG` | `temperature >= 32` and `light_level >= 35000` | 커튼 `60%` 닫힘 | 자동 실행 | 고온 + 강한 조도 동시 완화 |
| `R-CURTAIN-HOT-BRIGHT-MODERATE` | `temperature >= 29` and `light_level >= 25000` | 커튼 `35%` 닫힘 | 자동 실행 | 중간 수준 고온/고조도 대응 |
| `R-FAN-HOT-HUMID` | `humidity >= 75` and `temperature >= 30` | 환기팬 `level 2` | 자동 실행 | 공기 순환 강화 |
| `R-FAN-HUMID-FUNGAL` | `humidity >= 80` and 곰팡이 계열 질병 반복 관측 `repeat_count >= 2` | 환기팬 `level 3` | 자동 실행 | 고습도 곰팡이 리스크 완화 |
| `R-HOLD-WATER-HUMID-FUNGAL` | `humidity >= 80` and 곰팡이 계열 질병 반복 관측 `repeat_count >= 2` | 급수 보류 | 자동 적용 | 고습도 상황에서 급수 추가 악화 방지 |
| `R-NUTRIENT-CALCIUM-FRUITING` | `growth_stage`가 착화/과실기이고 칼슘 결핍/배꼽썩음 계열 징후 | 칼슘 보강제 `250 ml` | 승인 후 실행 | 병해 사진만으로 즉시 투여하지 않고 사람 확인 후 실행 |

## 곰팡이 계열 라벨 기준

AI 브랜치와 현재 perception codebook에서 확인되는 병해 명칭을 기준으로 아래 키워드를 곰팡이 계열로 봅니다.

- `tomato_powdery_mildew`
- `tomato_gray_mold`
- `powdery_mildew`
- `gray_mold`
- `mold`
- `fungal`
- `흰가루`
- `곰팡이`

## 영양제 추천 기준

영양제는 아래처럼 보수적으로 다룹니다.

- 성장 단계가 착화/과실기일 때만 후보로 올립니다.
- `blossom_end_rot`, `calcium_deficiency`, `배꼽썩음`, `칼슘결핍` 계열만 칼슘 보강제 대상으로 봅니다.
- 기본 정책은 `승인 후 실행`입니다.
- 즉, 잎 사진 한 번만 보고 영양제를 자동 투여하지 않습니다.

## 예시 입력 표

| 예시 | 입력 | 결과 |
| --- | --- | --- |
| `A` 매우 건조 | `soil_moisture=18`, `temperature=24`, `humidity=58`, 정상 잎 | 급수 `900 ml` 자동 실행 |
| `B` 고온/강한 조도 | `temperature=33`, `light_level=38000`, `soil_moisture=42` | 커튼 `60%` 닫힘 자동 실행 |
| `C` 고습도 곰팡이 반복 | `humidity=84`, `soil_moisture=20`, `class_name=tomato_gray_mold`, `repeat_count=2` | 급수 보류 + 환기팬 `level 3` 자동 실행 |
| `D` 착화/과실기 칼슘 결핍 의심 | `growth_stage=flowering_fruiting_stage`, `class_name=blossom_end_rot` | 칼슘 보강제 `250 ml` 승인 후 실행 |

## 구현 메모

- 현재 코드 기준 구현 위치는 `agribot_control.environment_disease_rules` 입니다.
- 이 규칙표는 다음 티켓의 입력으로 사용됩니다.
  - `S14P-407` 급수 실행 판단 로직
  - `S14P-408` 커튼·환기 실행 판단 로직
- 장치별 세부 payload는 이 규칙표를 바탕으로 후속 티켓에서 구체화합니다.
