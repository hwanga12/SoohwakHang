# AgriBot API 명세서

## 1. 문서 기준

이 문서는 현재 `backend/main.py` 에 등록된 실제 라우터와 요청 스키마를 기준으로 작성한다.

- 기준 시점: `2026-04-02`
- API 버전: `v1`
- Base path: `/api/v1`
- WebSocket path: `/ws/live`
- 인증: 현재 없음

## 2. 공통 계약

### 2.1 응답 형태

| 유형 | 설명 | 대상 |
| --- | --- | --- |
| Envelope | `{"data": ...}` 형태 | 대부분의 REST API |
| Direct model | 응답 본문이 바로 모델 | `/actuations/treatment-plan`, `/actuations/disease-treatment/dispatch`, `/inference/*` |
| File | 바이너리 또는 이미지 파일 | `/robot/map/raw`, `/media/{asset_id}`, `/camera/latest/frame` |
| WebSocket | JSON 및 text frame | `/ws/live` |

### 2.2 공통 에러 규칙

| 상태 코드 | 의미 |
| --- | --- |
| `400` | 요청 검증 실패 |
| `404` | 파일 또는 식별자 없음 |
| `409` | 중복 명령, 중복 미션, 상태 충돌 |
| `503` | 런타임 브리지 또는 모델 의존성 사용 불가 |
| `500` | 내부 오류 |

### 2.3 주요 식별자

| 식별자 | 예시 |
| --- | --- |
| `robot_id` | `AGR-02` |
| `zone_id` | `farm_01` |
| `device_id` | `farm_01_watering`, `farm_01_nutrient`, `sprinkler_1` |
| `mission_id` | UUID 또는 브리지 생성 ID |
| `command_id` | UUID 또는 브리지 생성 ID |

## 3. 엔드포인트 카탈로그

### 3.1 Dashboard

| Method | Path | 응답 | 설명 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/dashboard/summary` | Envelope | 메인 대시보드 요약 |

### 3.2 Robot

| Method | Path | 응답 | 설명 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/robot/status` | Envelope | 로봇 상태 카드 |
| `GET` | `/api/v1/robot/pose` | Envelope | 지도 위 로봇 pose |
| `GET` | `/api/v1/robot/map` | Envelope | 정적 map 메타데이터 |
| `GET` | `/api/v1/robot/map/raw` | File | 정적 map 원본 PGM |
| `GET` | `/api/v1/robot/map/layers` | Envelope | semantic layer |
| `GET` | `/api/v1/robot/navigation-preview` | Envelope | 예상 주행 경로 |
| `GET` | `/api/v1/robot/control/status` | Envelope | 현재 제어 상태 |
| `POST` | `/api/v1/robot/control/emergency-stop` | Envelope | 비상 정지 |
| `POST` | `/api/v1/robot/control/pause` | Envelope | 일시정지 |
| `POST` | `/api/v1/robot/control/resume` | Envelope | 재개 |
| `POST` | `/api/v1/robot/commands` | Envelope | 일반 로봇 명령 |
| `GET` | `/api/v1/robot/commands/latest` | Envelope | 최신 명령 상태 |

### 3.3 Missions

| Method | Path | 응답 | 설명 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/missions/patrol/start` | Envelope | 순찰 시작 |
| `POST` | `/api/v1/missions/patrol/stop` | Envelope | 순찰 중지 |
| `POST` | `/api/v1/missions/return-home` | Envelope | 홈 복귀 |
| `POST` | `/api/v1/missions/harvest` | Envelope | 수확 미션 요청 |
| `GET` | `/api/v1/missions/{mission_id}` | Envelope | 미션 상태 조회 |

### 3.4 Zones / Plants / Alerts

| Method | Path | 응답 | 설명 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/zones` | Envelope | 구역 목록 |
| `GET` | `/api/v1/plants` | Envelope | 식물 목록 |
| `GET` | `/api/v1/plants/{plant_id}` | Envelope | 식물 상세 |
| `GET` | `/api/v1/plants/{plant_id}/observations` | Envelope | 관측 이력 |
| `GET` | `/api/v1/alerts` | Envelope | 알림 목록 |
| `POST` | `/api/v1/alerts/{alert_id}/ack` | Envelope | 알림 읽음 처리 |

### 3.5 Environment / IoT / Harvest

| Method | Path | 응답 | 설명 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/environment/latest` | Envelope | 최신 환경값 |
| `GET` | `/api/v1/environment/history` | Envelope | 환경 이력 |
| `GET` | `/api/v1/iot/devices` | Envelope | 장치 상태 목록 |
| `GET` | `/api/v1/actuations/recommendations` | Envelope | 파생 추천 목록 |
| `POST` | `/api/v1/actuations/recommendations/{id}/approve` | Envelope | 추천 승인 |
| `POST` | `/api/v1/actuations/recommendations/{id}/reject` | Envelope | 추천 거절 |
| `POST` | `/api/v1/actuations/watering` | Envelope | 급수 수동 제어 |
| `POST` | `/api/v1/actuations/nutrients` | Envelope | 영양제 수동 제어 |
| `POST` | `/api/v1/actuations/treatment-plan` | Direct model | 병해 처리 계획 계산 |
| `POST` | `/api/v1/actuations/disease-treatment/dispatch` | Direct model | 병해 처리 dispatch |
| `GET` | `/api/v1/actuations/history` | Envelope | 장치 실행 이력 |
| `GET` | `/api/v1/harvests` | Envelope | 수확 이력 |
| `GET` | `/api/v1/harvests/stats` | Envelope | 수확 통계 |

### 3.6 Media / Camera / Inference / Realtime

| Method | Path | 응답 | 설명 |
| --- | --- | --- | --- |
| `GET` | `/api/v1/media/{asset_id}` | File | 관측 이미지 파일 |
| `GET` | `/api/v1/camera/latest` | Envelope | 최신 카메라 메타데이터 |
| `GET` | `/api/v1/camera/latest/frame` | File | 최신 카메라 이미지 |
| `POST` | `/api/v1/inference/confirm` | Direct model | 병해 확인 inference |
| `POST` | `/api/v1/inference/demo/confirm` | Direct model | 데모 입력 기반 확인 |
| `POST` | `/api/v1/inference/ripeness` | Direct model | 숙도 판단 저장 |
| `GET` | `/api/v1/inference/judgments/latest` | Direct model | 최신 AI 판단 |
| `GET` | `/api/v1/inference/judgments/history` | Direct model | AI 판단 이력 |
| `POST` | `/api/v1/inference/harvest/individual` | Direct model | 개별 수확 판단 |
| `POST` | `/api/v1/inference/harvest/bulk` | Direct model | 일괄 수확 판단 |
| `WS` | `/ws/live` | WebSocket | 연결 확인 및 echo |

## 4. 요청 스키마

이 절에서는 중복을 줄이기 위해 `/api/v1` 기준 상대 경로를 사용한다.

### 4.1 Robot Control Request

`POST /robot/control/emergency-stop`, `POST /robot/control/pause`, `POST /robot/control/resume`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `command_id` | `string` | 선택 | 중복 방지용 식별자 |
| `robot_id` | `string` | 필수 | 대상 로봇 ID |
| `requested_by` | `string` | 필수 | 요청 주체 |

### 4.2 Robot Command Request

`POST /robot/commands`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `command_id` | `string` | 선택 | 중복 방지용 식별자 |
| `robot_id` | `string` | 필수 | 대상 로봇 |
| `command_type` | `string` | 필수 | 아래 지원 값 참조 |
| `requested_by` | `string` | 필수 | 요청 주체 |
| `target_zone_id` | `string` | 선택 | `move_to_zone` 대상 |
| `map_id` | `string` | 선택 | 지도 기준 ID |
| `target_pose` | `object` | 선택 | `navigate_to_pose` 목표 pose |
| `payload` | `object` | 선택 | 추가 파라미터 |
| `preempt_current_navigation` | `bool` | 선택 | 현재 주행 선점 여부 |

지원 `command_type`

- `emergency_stop`
- `navigate_to_pose`
- `pause`
- `pause_motion`
- `pause_patrol`
- `resume`
- `resume_motion`
- `resume_patrol`
- `return_home`
- `move_to_zone`

`target_pose` 예시

```json
{
  "x": 0.0,
  "y": -8.6,
  "yaw": 1.5708,
  "frame_id": "map"
}
```

### 4.3 Mission Requests

#### 순찰 시작

`POST /missions/patrol/start`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `mission_id` | `string` | 선택 | 중복 방지용 식별자 |
| `robot_id` | `string` | 필수 | 대상 로봇 |
| `zone_ids` | `string[]` | 필수 | 순찰 구역 목록 |
| `loop_count` | `int` | 선택 | 반복 횟수, 기본 `1` |
| `requested_by` | `string` | 필수 | 요청 주체 |
| `patrol_mode` | `diagnosis \| harvest` | 선택 | 기본 `diagnosis` |

#### 순찰 중지

`POST /missions/patrol/stop`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `command_id` | `string` | 선택 | 중복 방지용 식별자 |
| `robot_id` | `string` | 필수 | 대상 로봇 |
| `requested_by` | `string` | 필수 | 요청 주체 |
| `reason` | `string` | 필수 | 중지 사유 |

#### 홈 복귀

`POST /missions/return-home`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `command_id` | `string` | 선택 | 중복 방지용 식별자 |
| `robot_id` | `string` | 필수 | 대상 로봇 |
| `requested_by` | `string` | 필수 | 요청 주체 |
| `home_waypoint_id` | `string` | 선택 | 홈 waypoint override |

#### 수확 미션

`POST /missions/harvest`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `mission_id` | `string` | 선택 | 중복 방지용 식별자 |
| `robot_id` | `string` | 필수 | 대상 로봇 |
| `plant_id` | `string` | 필수 | 대상 식물 |
| `fruit_id` | `string` | 필수 | 대상 과실 |
| `requested_by` | `string` | 필수 | 요청 주체 |
| `inspect_waypoint_id` | `string` | 선택 | 대표 inspection waypoint |
| `inspect_waypoint_ids` | `string[]` | 선택 | inspection waypoint 목록 |

### 4.4 Alerts

`POST /alerts/{alert_id}/ack`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `acknowledged_by` | `string` | 필수 | 읽음 처리자 |

### 4.5 Actuation Requests

#### 추천 승인

`POST /actuations/recommendations/{id}/approve`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `reviewed_by` | `string` | 필수 | 승인자 |
| `auto_execute` | `bool` | 선택 | 즉시 실행 여부, 기본 `true` |

#### 추천 거절

`POST /actuations/recommendations/{id}/reject`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `reviewed_by` | `string` | 필수 | 처리자 |
| `comment` | `string` | 선택 | 거절 사유 |

#### 급수

`POST /actuations/watering`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `zone_id` | `string` | 필수 | 대상 구역 |
| `device_id` | `string` | 필수 | 대상 장치 |
| `target_value` | `float` | 필수 | 목표값 |
| `value_unit` | `string` | 선택 | 기본 `ml` |
| `requested_by` | `string` | 필수 | 요청 주체 |
| `request_source` | `string` | 필수 | 요청 출처 |
| `recommendation_id` | `string` | 선택 | 추천 연계 ID |

#### 영양제

`POST /actuations/nutrients`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `zone_id` | `string` | 필수 | 대상 구역 |
| `device_id` | `string` | 필수 | 대상 장치 |
| `target_value` | `float` | 필수 | 목표값 |
| `value_unit` | `string` | 선택 | 기본 `ml` |
| `requested_by` | `string` | 필수 | 요청 주체 |
| `request_source` | `string` | 필수 | 요청 출처 |
| `recommendation_id` | `string` | 선택 | 추천 연계 ID |
| `command_payload` | `object` | 선택 | 확장용 payload |

#### 병해 처리 계획

`POST /actuations/treatment-plan`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `zone_id` | `string` | 필수 | 대상 구역 |
| `disease_label` | `string` | 필수 | 병해 라벨 |
| `target_position` | `object` | 선택 | 대상 좌표 |

#### 병해 처리 dispatch

`POST /actuations/disease-treatment/dispatch`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `observation_id` | `string` | 선택 | 관측 식별자 |
| `zone_id` | `string` | 필수 | 대상 구역 |
| `disease_label` | `string` | 필수 | 병해 라벨 |
| `target_position` | `object` | 선택 | 대상 좌표 |
| `requested_by` | `string` | 필수 | 요청 주체 |
| `auto_execute` | `bool` | 선택 | 즉시 실행 여부, 기본 `true` |

### 4.6 Inference Requests

#### 병해 확인

`POST /inference/confirm`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `observation_id` | `string` | 선택 | 관측 식별자 |
| `robot_id` | `string` | 선택 | 로봇 ID |
| `zone_id` | `string` | 선택 | 구역 ID |
| `plant_id` | `string` | 선택 | 식물 ID |
| `fruit_id` | `string` | 선택 | 과실 ID |
| `frame_id` | `string` | 선택 | 프레임 ID |
| `target_position` | `object` | 선택 | 대상 좌표 |
| `requested_by` | `string` | 선택 | 요청 주체 |
| `auto_execute_treatment` | `bool` | 선택 | 처치 자동 실행 여부 |
| `preliminary_label` | `string` | 선택 | 1차 라벨 |
| `preliminary_confidence` | `float` | 선택 | 1차 신뢰도 |
| `test_override_final_label` | `string` | 선택 | 테스트용 override |
| `test_override_final_confidence` | `float` | 선택 | 테스트용 confidence |
| `image_base64` | `string` | 필수 | 입력 이미지 |
| `image_format` | `string` | 선택 | 기본 `jpg` |
| `bbox` | `object` | 선택 | bounding box |

#### 데모 병해 확인

`POST /inference/demo/confirm`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `plant_id` | `string` | 필수 | 데모 매핑 대상 식물 |
| `fruit_id` | `string` | 선택 | 과실 ID |
| `robot_id` | `string` | 선택 | 기본 `AGR-02` |
| `zone_id` | `string` | 선택 | 기본 `farm_01` |
| `requested_by` | `string` | 선택 | 기본 `frontend-demo` |
| `target_position` | `object` | 선택 | 처리 계획 계산용 좌표 |
| `auto_execute_treatment` | `bool` | 선택 | 처치 자동 실행 여부 |

#### 숙도 판단 저장

`POST /inference/ripeness`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `plant_id` | `string` | 선택 | 식물 ID |
| `fruit_id` | `string` | 선택 | 과실 ID |
| `zone_id` | `string` | 선택 | 구역 ID |
| `model_name` | `string` | 선택 | 기본 `ripeness_classifier_v1` |
| `model_version` | `string` | 선택 | 기본 `v1` |
| `raw_label` | `string` | 필수 | 원본 라벨 |
| `confidence` | `float` | 선택 | `0.0`~`1.0` |
| `image_url` | `string` | 선택 | 이미지 경로 |
| `evidence` | `string[]` | 선택 | 근거 목록 |

#### 개별 수확 판단

`POST /inference/harvest/individual`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `plant_id` | `string` | 선택 | 식물 ID |
| `fruit_id` | `string` | 선택 | 과실 ID |
| `zone_id` | `string` | 선택 | 구역 ID |
| `requested_by` | `string` | 선택 | 기본 `frontend` |

#### 일괄 수확 판단

`POST /inference/harvest/bulk`

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `targets` | `object[]` | 선택 | 개별 수확 판단 대상 목록 |
| `requested_by` | `string` | 선택 | 기본 `frontend` |

## 5. 대표 응답 필드

이 절에서도 `/api/v1` 기준 상대 경로를 사용한다.

### 5.1 Dashboard Summary

`GET /dashboard/summary`

- `robot_uptime_pct`
- `active_task`
- `critical_alert_count`
- `plant_count`
- `ready_fruit_count`
- `robot_name`

### 5.2 Robot Status

`GET /robot/status`

- `robot_id`
- `status`
- `mission_state`
- `mode`
- `battery_level`
- `current_zone_id`
- `updated_at`
- `current_control_state`
- `latest_command`

### 5.3 Mission Status

`GET /missions/{mission_id}`

- `mission_id`
- `mission_type`
- `status`
- `state`
- `progress_pct`
- `zone_ids`
- `plant_id`
- `fruit_id`
- `target_id`
- `started_at`
- `completed_at`

### 5.4 IoT Recommendation / Dispatch

`GET /actuations/recommendations`

- `id`
- `title`
- `detail`
- `priority`
- `status`
- `zone_id`
- `device_id`

`POST /actuations/watering`, `POST /actuations/nutrients`

- `command_id`
- `device_id`
- `device_name`
- `command_type`
- `command_status`
- `message`

### 5.5 Disease Treatment Plan

`POST /actuations/treatment-plan`

- `disease_label`
- `normalized_disease_label`
- `action_required`
- `status`
- `rule_id`
- `treatment_type`
- `selected_sprinkler`
- `command_payload`
- `reason`

### 5.6 Thin Inference Confirm

`POST /inference/confirm`, `POST /inference/demo/confirm`

- `observation_id`
- `preliminary_label`
- `preliminary_confidence`
- `final_label`
- `final_confidence`
- `image_path`
- `reviewed_at`
- `decision_source`
- `treatment_plan`
- `dispatch_result`
- `disease_judgment_id`
- `harvest_decision_id`

## 6. 구현 유의사항

- 대부분의 운영 조회 API는 envelope 응답을 사용하지만, `inference` 와 일부 `actuations` API는 direct model 응답이다.
- `GET /missions/{mission_id}`, `GET /harvests`, `GET /harvests/stats` 는 런타임 상태 파일이 존재하면 이를 우선 사용한다.
- `POST /actuations/watering`, `POST /actuations/nutrients` 는 사용자 논리 명령을 받아 장치 종류에 따라 실제 dispatch 명령으로 변환한다.
- `GET /robot/map/raw`, `GET /media/{asset_id}`, `GET /camera/latest/frame` 는 파일 기반 응답이므로 대상 파일이 없으면 `404`를 반환한다.
- `WS /ws/live` 는 현재 연결 확인과 echo 수준이며, 실시간 푸시 채널로 확장 가능한 경로 계약을 유지한다.
