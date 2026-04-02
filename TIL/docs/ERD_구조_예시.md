# AgriBot IoT 반영 ERD 구조 예시

## 1. 이번 ERD가 왜 다시 바뀌는가

`수확해조_프로젝트_개발_계획_및_협업_가이드.md`를 다시 보면,
이제 IoT는 단순히 "물 주기 버튼 한 번 누르기" 수준이 아닙니다.

프로젝트가 요구하는 흐름은 아래처럼 더 구체적입니다.

1. 로봇이 식물과 환경을 본다
2. 규칙에 따라 "어떤 장치를 움직일지" 추천한다
3. 자동 실행 가능한 것은 바로 실행한다
4. 위험하거나 설명이 필요한 것은 사용자 승인을 기다린다
5. 실제 장치 명령을 보낸다
6. 장치가 성공/실패 결과와 현재 상태를 돌려준다
7. 그 결과가 DB와 대시보드에 저장된다

그래서 이번 ERD에서는 IoT 관련 테이블을 더 세분화해야 합니다.

## 2. 비전공자용 한 줄 요약

이 ERD는 아래 4가지를 따로 관리하는 구조입니다.

- `iot_devices`: "우리 농장에 어떤 장치가 붙어 있는가"
- `actuation_recommendations`: "왜 이 장치를 움직이자고 판단했는가"
- `actuation_commands`: "실제로 어떤 명령을 보냈는가"
- `actuation_logs`: "그 명령이 실제로 어떻게 끝났는가"

쉽게 비유하면 이렇습니다.

- 장치 목록 = 사무실 비품 목록
- 추천 = 담당자가 쓴 제안서
- 명령 = 결재된 작업 지시서
- 실행 로그 = 실제 작업 결과 보고서

## 3. 공통 용어

| 용어 | 뜻 | 예시 |
| --- | --- | --- |
| `PK` | 각 행을 구분하는 고유값 | `fruit_03`, UUID |
| `FK` | 다른 테이블을 참조하는 값 | `plants.zone_id -> zones.id` |
| `BOOLEAN` | 참/거짓 | `true`, `false` |
| `JSONB` | 좌표나 범위처럼 구조가 있는 값 | `{\"x\":1.2,\"y\":3.4,\"z\":0.0}` |
| `TIMESTAMP` | 날짜와 시간 | `2026-03-16 16:20:00` |
| `ENUM처럼 쓰는 문자열` | 정해진 후보만 넣는 값 | `CRITICAL`, `AUTO_RULE`, `SUCCESS` |

## 4. 전체 구조를 먼저 이해하기

### 4-1. 공간과 대상

- `zones`: 구역
- `plants`: 식물
- `fruits`: 식물에 달린 토마토 개체

### 4-2. 로봇과 작업

- `robots`: 로봇 현재 상태
- `missions`: 순찰, 수확, 복귀 같은 작업

### 4-3. 관측과 환경

- `crop_observations`: 카메라 관측 기록
- `environment_samples`: 환경 센서 기록
- `media_assets`: 사진 파일 정보
- `alerts`: 사람이 봐야 하는 경고

### 4-4. IoT 상호작용

- `iot_devices`: 실제 제어 대상 장치
- `actuation_recommendations`: 규칙 엔진이 낸 추천
- `actuation_commands`: 실제 발행된 명령
- `actuation_logs`: 실행 성공/실패 결과

### 4-5. 최종 결과

- `harvest_events`: 수확 성공/실패 기록

## 5. IoT 때문에 꼭 생겨야 하는 흐름

```text
environment_samples / crop_observations
        ↓
actuation_recommendations
        ↓
자동 실행 또는 사용자 승인
        ↓
actuation_commands
        ↓
actuation_logs
        ↓
iot_devices.current_state 업데이트
        ↓
dashboard / API / WebSocket 반영
```

중요한 점은 "추천"과 "명령"이 다르다는 것입니다.

- 추천: 아직 실행 전, "이렇게 하는 게 좋겠다"
- 명령: 실제로 장치에 보낸 실행 요청

예를 들어 영양제는 추천은 자동으로 할 수 있지만, 실행은 사용자 승인이 필요할 수 있습니다.
그래서 둘을 한 테이블에 섞으면 나중에 설명이 어려워집니다.

## 6. 테이블별 상세 설명

### 6-1. `zones`

왜 필요한가:
환경값, 장치, 식물, 알림이 모두 "어느 구역인가"를 기준으로 연결됩니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `VARCHAR(50)` / `zone_A` | 구역을 고유하게 식별합니다. |
| `name` | `VARCHAR(100)` / `토마토 1구역` | 사람이 읽기 쉬운 이름입니다. |
| `bounds` | `JSONB` / `{\"x_min\":0,\"x_max\":5,\"y_min\":0,\"y_max\":3}` | 지도와 Gazebo에서 구역 범위를 표현합니다. |
| `description` | `VARCHAR(255)` / `출입문 근처` | 운영 메모입니다. |

### 6-2. `plants`

왜 필요한가:
식물은 관리의 기본 대상입니다.
대시보드에서 "이 식물의 현재 상태"를 빠르게 보여주려면 최신 상태를 따로 들고 있어야 합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `VARCHAR(50)` / `plant_101` | 식물 고유 ID입니다. |
| `zone_id` | `VARCHAR(50)` / `zone_A` | 이 식물이 어느 구역에 있는지 연결합니다. |
| `crop_name` | `VARCHAR(50)` / `tomato` | 작물 종류를 구분합니다. |
| `position` | `JSONB` / `{\"x\":1.2,\"y\":3.4,\"z\":0.0}` | 지도와 시뮬레이터 위치를 맞춥니다. |
| `health_score` | `FLOAT` / `0.82` | 현재 건강도를 한눈에 보여줍니다. |
| `growth_stage` | `FLOAT` / `0.70` | 현재 성장 정도를 표현합니다. |
| `needs_water` | `BOOLEAN` / `true` or `false` | 지금 급수가 필요한지 표시합니다. |
| `ready_to_harvest` | `BOOLEAN` / `true` or `false` | 이 식물에 수확 가능한 열매가 하나 이상 있는지 요약합니다. |
| `last_observed_at` | `TIMESTAMP` / `2026-03-16 16:05:00` | 상태가 언제 갱신됐는지 확인합니다. |

### 6-3. `fruits`

왜 필요한가:
식물 한 그루에 토마토가 여러 개 달릴 수 있으므로, "식물"과 "열매"를 나눠야 특정 토마토 수확이 가능합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `VARCHAR(50)` / `fruit_03` | 토마토 개체 고유 ID입니다. |
| `plant_id` | `VARCHAR(50)` / `plant_101` | 어느 식물에 달려 있는지 연결합니다. |
| `position` | `JSONB` / `{\"x\":1.3,\"y\":3.5,\"z\":0.8}` | 로봇이 정확히 어느 열매를 집을지 판단할 때 필요합니다. |
| `ripeness_stage` | `VARCHAR(30)` / `UNRIPE`, `TURNING`, `RIPE` | 익음 정도를 표현합니다. |
| `ready_to_harvest` | `BOOLEAN` / `true` or `false` | 지금 바로 수확 대상인지 판정합니다. |
| `current_status` | `VARCHAR(30)` / `VISIBLE`, `TARGETED`, `HARVESTED`, `LOST` | 지금 열매가 어떤 상태인지 추적합니다. |
| `last_observed_at` | `TIMESTAMP` / `2026-03-16 16:07:00` | 최근에 언제 본 열매인지 알 수 있습니다. |

### 6-4. `robots`

왜 필요한가:
사용자는 로봇이 어디 있고, 무엇을 하고 있고, 배터리가 얼마나 남았는지 알아야 합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 로봇 고유 ID입니다. |
| `name` | `VARCHAR(100)` / `agribot-01` | 화면에 표시할 이름입니다. |
| `status` | `VARCHAR(50)` / `IDLE`, `PATROL`, `HARVEST`, `ERROR` | 로봇 현재 모드입니다. |
| `battery_level` | `FLOAT` / `76.5` | 배터리 부족 여부를 판단합니다. |
| `current_zone_id` | `VARCHAR(50)` / `zone_B` | 현재 어느 구역에 있는지 빠르게 보여줍니다. |
| `current_pose` | `JSONB` / `{\"x\":2.4,\"y\":1.1,\"yaw\":1.57}` | 지도 위 현재 좌표와 방향입니다. |
| `updated_at` | `TIMESTAMP` / `2026-03-16 16:10:00` | 상태 정보가 최신인지 확인합니다. |

### 6-5. `missions`

왜 필요한가:
로봇은 계속 움직이므로 "무슨 목적으로 움직이는지"를 따로 기록해야 합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 미션 고유 ID입니다. |
| `robot_id` | `UUID` | 어느 로봇의 미션인지 연결합니다. |
| `mission_type` | `VARCHAR(50)` / `PATROL`, `HARVEST`, `RETURN_HOME`, `IOT_ACTION` | 작업 종류를 구분합니다. |
| `target_zone_id` | `VARCHAR(50)` / `zone_A` | 어느 구역을 목표로 하는지 저장합니다. |
| `target_plant_id` | `VARCHAR(50)` / `plant_101` | 특정 식물 미션에 필요합니다. |
| `target_fruit_id` | `VARCHAR(50)` / `fruit_03` | 특정 토마토 수확 미션에 필요합니다. |
| `status` | `VARCHAR(50)` / `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELED` | 진행 상태입니다. |
| `progress_percent` | `INT` / `40` | 대시보드 진행률용입니다. |
| `started_at` | `TIMESTAMP` | 시작 시각입니다. |
| `completed_at` | `TIMESTAMP` or `NULL` | 종료 시각입니다. |

### 6-6. `crop_observations`

왜 필요한가:
식물의 현재 상태만 있으면 "언제 병이 생겼는지", "지난번보다 나아졌는지"를 알 수 없습니다.
그래서 관측은 이력으로 쌓아야 합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 관측 1건의 ID입니다. |
| `plant_id` | `VARCHAR(50)` | 어떤 식물 관측인지 연결합니다. |
| `fruit_id` | `VARCHAR(50)` or `NULL` | 특정 토마토 관측이면 연결합니다. 잎사귀 관측이면 `NULL`일 수 있습니다. |
| `mission_id` | `UUID` or `NULL` | 어느 미션 중 관측했는지 남깁니다. |
| `class_name` | `VARCHAR(50)` / `healthy_leaf`, `leaf_mold`, `ripe_tomato` | AI가 본 대상을 기록합니다. |
| `confidence` | `FLOAT` / `0.94` | AI 확신도입니다. |
| `health_score` | `FLOAT` / `0.76` | 관측 시점 건강도입니다. |
| `needs_water` | `BOOLEAN` / `true` or `false` | 관측 시점 기준 급수 필요 판정입니다. |
| `ready_to_harvest` | `BOOLEAN` / `true` or `false` | 관측 시점 기준 수확 가능 판정입니다. |
| `observed_at` | `TIMESTAMP` | 관측 시각입니다. |

### 6-7. `environment_samples`

왜 필요한가:
IoT 장치 자동 제어는 환경 데이터가 없으면 불가능합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 환경 샘플 1건의 ID입니다. |
| `zone_id` | `VARCHAR(50)` / `zone_A` | 어느 구역 환경인지 연결합니다. |
| `temperature` | `FLOAT` / `24.5` | 온도입니다. |
| `humidity` | `FLOAT` / `58.2` | 습도입니다. |
| `soil_moisture` | `FLOAT` / `31.0` | 급수 판단 핵심 값입니다. |
| `light_level` | `FLOAT` / `8500` | 조도입니다. 커튼 제어 판단에 쓰입니다. |
| `co2_level` | `FLOAT` / `620` | 환경 제어 확장값입니다. |
| `recorded_at` | `TIMESTAMP` | 측정 시각입니다. |

### 6-8. `iot_devices`

왜 필요한가:
이제 장치 자체가 데이터 모델의 주인공입니다.
구역마다 급수 펌프, 영양제 디스펜서, 스프링클러가 무엇인지 알아야 명령을 보낼 수 있습니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `VARCHAR(50)` / `sprinkler_1` | 장치 고유 ID입니다. |
| `zone_id` | `VARCHAR(50)` / `zone_A` | 어느 구역 장치인지 연결합니다. |
| `device_type` | `VARCHAR(30)` / `WATER_PUMP`, `NUTRIENT`, `SPRINKLER` | 장치 종류를 구분합니다. |
| `display_name` | `VARCHAR(100)` / `A구역 스프링클러 1` | 사람이 읽는 장치 이름입니다. |
| `control_mode` | `VARCHAR(30)` / `AUTO`, `MANUAL`, `MANUAL_OVERRIDE`, `DISABLED` | 자동 제어 중인지, 수동이 우선인지 표현합니다. |
| `current_state` | `VARCHAR(30)` / `OFF`, `ON`, `RUNNING`, `ERROR` | 장치 현재 상태입니다. |
| `current_value` | `FLOAT` / `3` | 급수량, 영양제량, 살포 시간 등 현재 수치입니다. |
| `value_unit` | `VARCHAR(20)` / `ml`, `sec` | 현재 수치의 단위입니다. |
| `is_online` | `BOOLEAN` / `true` or `false` | 장치가 현재 연결돼 있는지 표시합니다. |
| `last_seen_at` | `TIMESTAMP` | 마지막 상태 수신 시각입니다. |

### 6-9. `actuation_recommendations`

왜 필요한가:
IoT에서 가장 중요하게 추가된 테이블입니다.
"왜 이 장치를 움직이자고 판단했는가"를 남기지 않으면 자동 제어를 설명할 수 없습니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 추천 1건 ID입니다. |
| `zone_id` | `VARCHAR(50)` / `zone_A` | 어느 구역에 대한 추천인지 저장합니다. |
| `plant_id` | `VARCHAR(50)` or `NULL` | 특정 식물에서 시작된 추천이면 연결합니다. |
| `device_id` | `VARCHAR(50)` or `NULL` | 어떤 장치를 추천 대상으로 보는지 연결합니다. |
| `recommendation_type` | `VARCHAR(30)` / `WATERING`, `NUTRIENTS` | 추천 종류입니다. |
| `reason_code` | `VARCHAR(50)` / `LOW_SOIL_MOISTURE`, `HIGH_TEMP_LIGHT`, `HIGH_HUMIDITY_DISEASE` | 머신이 이해하기 쉬운 추천 이유 코드입니다. |
| `reason_text` | `TEXT` / `토양수분이 기준보다 낮아 급수 추천` | 사람이 이해하기 쉬운 설명입니다. |
| `suggested_value` | `FLOAT` / `300` | 추천량 또는 목표값입니다. |
| `value_unit` | `VARCHAR(20)` / `ml`, `percent`, `level` | 추천값 단위입니다. |
| `priority` | `VARCHAR(20)` / `LOW`, `MEDIUM`, `HIGH` | 어떤 추천을 먼저 처리할지 정합니다. |
| `approval_required` | `BOOLEAN` / `true` or `false` | 사용자 승인 필요 여부입니다. 영양제는 보통 `true`입니다. |
| `status` | `VARCHAR(30)` / `PENDING`, `APPROVED`, `REJECTED`, `AUTO_EXECUTED`, `EXPIRED` | 추천이 현재 어떤 상태인지 추적합니다. |
| `reviewed_by` | `VARCHAR(100)` / `user:dashboard` or `NULL` | 누가 승인/거절했는지 남깁니다. |
| `reviewed_at` | `TIMESTAMP` or `NULL` | 언제 승인/거절했는지 기록합니다. |

#### 왜 `recommendations`가 `commands`와 따로 있어야 하나

- 추천은 아직 실행 전 판단입니다.
- 명령은 실제 장치에 보낸 요청입니다.
- 영양제처럼 "추천은 자동, 실행은 승인 후"인 기능은 추천 테이블이 없으면 표현이 안 됩니다.
- 나중에 "왜 급수는 자동 실행됐는데 영양제는 대기했나?"를 설명할 수 있어야 합니다.

### 6-10. `actuation_commands`

왜 필요한가:
추천이 실제 실행으로 이어졌는지, 아니면 사용자가 직접 눌렀는지를 구분해야 합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 명령 1건 ID입니다. |
| `recommendation_id` | `UUID` or `NULL` | 추천에서 이어진 명령이면 연결합니다. 수동 버튼이면 `NULL`일 수 있습니다. |
| `device_id` | `VARCHAR(50)` / `sprinkler_1` | 어느 장치에 보낸 명령인지 기록합니다. |
| `zone_id` | `VARCHAR(50)` / `zone_A` | 어느 구역 명령인지 빠르게 조회합니다. |
| `mission_id` | `UUID` or `NULL` | 특정 미션 흐름 중 생성된 명령이면 연결합니다. |
| `requested_by` | `VARCHAR(100)` / `system`, `user:dashboard` | 누가 요청했는지 표시합니다. |
| `request_source` | `VARCHAR(30)` / `AUTO_RULE`, `USER_BUTTON`, `MISSION_FLOW` | 왜 이 명령이 생겼는지 구분합니다. |
| `command_type` | `VARCHAR(30)` / `WATERING`, `NUTRIENTS`, `STOP` | 명령 종류입니다. |
| `target_value` | `FLOAT` / `300`, `50`, `2` | 장치가 목표로 해야 할 값입니다. |
| `value_unit` | `VARCHAR(20)` / `ml`, `sec` | 목표값 단위입니다. |
| `command_status` | `VARCHAR(30)` / `REQUESTED`, `SENT`, `ACKED`, `COMPLETED`, `FAILED`, `CANCELED` | 명령 진행 상태입니다. |
| `requested_at` | `TIMESTAMP` | 명령 생성 시각입니다. |

### 6-11. `actuation_logs`

왜 필요한가:
명령과 실제 결과는 다를 수 있습니다.
그래서 "보낸 명령"과 "돌아온 결과"를 분리해야 디버깅이 쉽습니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 실행 로그 1건 ID입니다. |
| `command_id` | `UUID` | 어떤 명령의 결과인지 연결합니다. |
| `device_id` | `VARCHAR(50)` | 어느 장치가 실행했는지 연결합니다. |
| `result` | `VARCHAR(20)` / `SUCCESS`, `FAILED`, `TIMEOUT` | 결과가 성공인지 실패인지 표현합니다. |
| `result_message` | `TEXT` / `pump timeout`, `manual lock active` | 실패 이유나 실행 결과 설명입니다. |
| `state_after` | `VARCHAR(30)` / `ON`, `RUNNING`, `ERROR` | 실행 후 장치 상태를 요약합니다. |
| `actual_value` | `FLOAT` / `280`, `50`, `2` | 실제 적용된 값입니다. |
| `value_unit` | `VARCHAR(20)` / `ml`, `percent`, `level` | 실제 적용값 단위입니다. |
| `started_at` | `TIMESTAMP` | 실행 시작 시각입니다. |
| `finished_at` | `TIMESTAMP` | 실행 완료 시각입니다. |

#### 왜 `commands`와 `logs`를 나누나

- `commands`는 "이렇게 해달라고 요청한 것"
- `logs`는 "실제로 이렇게 됐다고 돌아온 것"

예를 들어 300ml 급수를 요청했어도,
실제로는 280ml만 나갔거나, 아예 타임아웃으로 실패했을 수 있습니다.

### 6-12. `alerts`

왜 필요한가:
사람이 즉시 봐야 하는 사건을 따로 관리해야 합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 알림 1건 ID입니다. |
| `robot_id` | `UUID` or `NULL` | 어느 로봇에서 나온 알림인지 연결합니다. |
| `zone_id` | `VARCHAR(50)` or `NULL` | 어느 구역 문제인지 연결합니다. |
| `plant_id` | `VARCHAR(50)` or `NULL` | 특정 식물 문제인지 연결합니다. |
| `observation_id` | `UUID` or `NULL` | 어떤 관측에서 파생됐는지 추적합니다. |
| `alert_type` | `VARCHAR(30)` / `DISEASE`, `SENSOR_ERROR`, `ROBOT_ERROR`, `DEVICE_ERROR`, `STOP` | 문제 종류입니다. |
| `severity` | `VARCHAR(20)` / `INFO`, `WARNING`, `CRITICAL` | 얼마나 급한지 표현합니다. 정렬, 색상, 푸시 여부 판단에 필요합니다. |
| `message` | `TEXT` | 사람이 바로 이해할 수 있는 설명입니다. |
| `acknowledged_at` | `TIMESTAMP` or `NULL` | 사용자가 확인했는지, 언제 확인했는지 기록합니다. |
| `detected_at` | `TIMESTAMP` | 알림 발생 시각입니다. |

### 6-13. `harvest_events`

왜 필요한가:
수확은 성공뿐 아니라 실패도 기록해야 개선이 가능합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 수확 이벤트 1건 ID입니다. |
| `fruit_id` | `VARCHAR(50)` / `fruit_03` | 어떤 토마토를 수확했는지 기록합니다. |
| `plant_id` | `VARCHAR(50)` / `plant_101` | 어떤 식물에서 나온 토마토인지 기록합니다. |
| `robot_id` | `UUID` | 어떤 로봇이 수확했는지 남깁니다. |
| `mission_id` | `UUID` | 어떤 수확 미션의 결과인지 연결합니다. |
| `success` | `BOOLEAN` / `true` or `false` | 수확 성공 여부입니다. |
| `fail_reason` | `TEXT` / `target_lost`, `gripper_miss` or `NULL` | 실패 원인 분석용입니다. |
| `basket_count` | `INT` / `7` | 이 시점까지 바구니에 누적된 수량입니다. |
| `harvested_at` | `TIMESTAMP` | 수확 시각입니다. |

### 6-14. `media_assets`

왜 필요한가:
병든 잎 사진, 관측 스냅샷, 증거 이미지를 따로 관리해야 합니다.

| 컬럼 | 타입 / 예시값 | 왜 필요한가 |
| --- | --- | --- |
| `id` | `UUID` | 파일 1건 ID입니다. |
| `observation_id` | `UUID` or `NULL` | 관측 이미지면 연결합니다. |
| `alert_id` | `UUID` or `NULL` | 알림에 붙은 이미지면 연결합니다. |
| `file_path` | `VARCHAR(255)` / `/media/obs_001.jpg` | 실제 파일 경로입니다. |
| `media_type` | `VARCHAR(50)` / `image/jpeg` | 파일 종류입니다. |
| `captured_at` | `TIMESTAMP` | 언제 찍힌 파일인지 기록합니다. |

## 7. 비전공자가 가장 많이 헷갈리는 부분

### 7-1. 왜 장치 현재 상태와 실행 로그를 둘 다 저장하나

- `iot_devices.current_state`는 "지금 현재 상태"
- `actuation_logs`는 "과거에 무슨 일이 있었는지"

비유하면 이렇습니다.

- 현재 상태: 지금 방 안 불이 켜져 있는가
- 실행 로그: 누가 언제 스위치를 눌렀고 성공했는가

둘은 역할이 다릅니다.

### 7-2. 왜 추천과 명령을 나누나

추천은 생각이고, 명령은 행동입니다.

예시:

- 토양수분이 낮다 → 급수 추천 생성
- 급수는 자동 실행 가능 → 바로 명령 생성
- 영양제는 승인 필요 → 추천만 남고 명령은 나중에 생성

### 7-3. `severity`는 왜 필요한가

`alert_type`은 문제 종류,
`severity`는 문제 심각도입니다.

예시:

| 상황 | alert_type | severity |
| --- | --- | --- |
| 잎 한 장에서 약한 병징 | `DISEASE` | `WARNING` |
| 여러 구역 장치 동시 오류 | `DEVICE_ERROR` | `CRITICAL` |
| 센서 1회 끊김 | `SENSOR_ERROR` | `INFO` |

### 7-4. `control_mode`는 왜 필요한가

IoT는 자동 제어만 있지 않습니다.
문서에서 "수동 우선", "중복 명령 방지", "안전 잠금"이 중요하다고 했기 때문에
장치가 지금 자동 모드인지, 수동 개입 중인지 알아야 합니다.

예시:

- `AUTO`: 자동 규칙 허용
- `MANUAL`: 사용자가 직접 조작 중
- `MANUAL_OVERRIDE`: 자동보다 수동이 우선
- `DISABLED`: 장치 사용 중지

## 8. 이번 ERD에서 이전 버전보다 달라진 핵심

- `iot_devices`를 정식 핵심 엔티티로 올렸습니다.
- `actuation_recommendations`를 추가해서 추천과 실행을 분리했습니다.
- `actuation_commands`와 `actuation_logs`를 분리했습니다.
- `fruits`를 추가해서 특정 토마토 수확 흐름을 자연스럽게 만들었습니다.
- 이미지 경로는 `media_assets`로 분리했습니다.

## 9. 최종 한 줄 정리

이번 ERD는 "식물과 로봇을 보는 시스템"에서 끝나지 않고,
"환경을 보고 장치를 추천하고, 승인하고, 실행하고, 결과를 남기는 시스템"으로 확장된 구조입니다.

즉, IoT 상호작용이 들어가면서
"장치", "추천", "명령", "실행 결과"가 모두 독립 엔티티가 되어야 합니다.

## 10. 함께 제공하는 이미지

같은 위치에 SVG 다이어그램을 함께 둡니다.

- `ERD_구조_예시.svg`

이 SVG에는 각 테이블의 핵심 필드, 예시값, 왜 필요한지가 짧게 함께 들어가 있습니다.
