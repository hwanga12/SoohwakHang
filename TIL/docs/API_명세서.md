# AgriBot API Spec Draft

## 1. 문서 목적

이 문서는 아래 두 기준을 합쳐서 만든 API 초안입니다.

- `수확해조_프로젝트_개발_계획_및_협업_가이드.md`에 나온 필수 API
- `ERD_구조_예시.md`, `DB_SCHEMA_DRAFT.sql`에 반영된 IoT 추천/승인/실행 흐름

즉, 이 문서는 "화면에서 무엇을 눌렀을 때 서버가 어떤 데이터를 읽고 쓰는가"를 팀이 공통으로 맞추기 위한 기준 문서입니다.

## 2. 범위

이 문서는 P0~P0+ 범위의 서버 API를 다룹니다.

- 로봇 상태 조회
- 순찰/수확/복귀 명령
- 식물/관측/알림 조회
- 환경값 조회
- IoT 장치 상태 조회
- IoT 추천 조회 및 승인
- 급수/커튼/환기팬/영양제 제어
- 수확 이력/통계
- WebSocket 실시간 이벤트

## 3. 공통 규칙

### 3-1. Base URL

```text
REST: /api/v1
WebSocket: /ws/live
```

### 3-2. Content Type

- 요청: `application/json`
- 응답: `application/json`

### 3-3. 시간 형식

- 모든 시간은 ISO 8601 + timezone 형식 사용
- 예: `2026-03-16T16:20:00+09:00`

### 3-4. 성공 응답 형식

```json
{
  "data": {},
  "meta": {
    "request_id": "optional-request-id"
  }
}
```

### 3-5. 오류 응답 형식

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "target_value must be greater than 0",
    "details": {}
  }
}
```

### 3-6. 페이지네이션 규칙

목록 API는 기본적으로 아래 쿼리 파라미터를 지원합니다.

- `page`: 기본값 `1`
- `size`: 기본값 `20`
- `sort`: 예) `detected_at:desc`

### 3-7. 인증 범위

P0 단계에서는 로그인/권한 기능을 필수 범위에서 제외합니다.
따라서 누가 요청했는지는 우선 문자열로 남깁니다.

예:

- `requested_by = "system"`
- `requested_by = "user:dashboard"`
- `reviewed_by = "user:admin"`

## 4. 주요 상태값

| 항목 | 후보 값 |
| --- | --- |
| `robot.status` | `IDLE`, `PATROL`, `OBSERVE`, `HARVEST`, `RETURN_HOME`, `IOT_ACTION`, `ERROR`, `STOPPED` |
| `missions.status` | `PENDING`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`, `CANCELED` |
| `fruits.ripeness_stage` | `UNRIPE`, `TURNING`, `RIPE` |
| `iot_devices.device_type` | `WATER_PUMP`, `NUTRIENT`, `SPRINKLER` |
| `iot_devices.control_mode` | `AUTO`, `MANUAL`, `MANUAL_OVERRIDE`, `DISABLED` |
| `iot_devices.current_state` | `IDLE`, `OFF`, `ON`, `RUNNING`, `ERROR` |
| `actuation_recommendations.status` | `PENDING`, `APPROVED`, `REJECTED`, `AUTO_EXECUTED`, `EXPIRED` |
| `actuation_commands.command_status` | `REQUESTED`, `SENT`, `ACKED`, `COMPLETED`, `FAILED`, `CANCELED` |
| `actuation_logs.result` | `SUCCESS`, `FAILED`, `TIMEOUT`, `REJECTED` |
| `alerts.alert_type` | `DISEASE`, `SENSOR_ERROR`, `ROBOT_ERROR`, `DEVICE_ERROR`, `STOP` |
| `alerts.severity` | `INFO`, `WARNING`, `CRITICAL` |

## 5. 엔드포인트 요약

| 구분 | Method | Path | 목적 |
| --- | --- | --- | --- |
| Dashboard | `GET` | `/api/v1/dashboard/summary` | 메인 화면 요약 |
| Robot | `GET` | `/api/v1/robot/status` | 로봇 현재 상태 |
| Robot | `GET` | `/api/v1/robot/pose` | 지도 좌표 위치 |
| Robot | `POST` | `/api/v1/robot/commands` | 긴급 정지, 재개, 수동 이동 |
| Mission | `POST` | `/api/v1/missions/patrol/start` | 순찰 시작 |
| Mission | `POST` | `/api/v1/missions/patrol/stop` | 순찰 중지 |
| Mission | `POST` | `/api/v1/missions/return-home` | 홈 복귀 |
| Mission | `POST` | `/api/v1/missions/harvest` | 특정 fruit 수확 요청 |
| Mission | `GET` | `/api/v1/missions/{mission_id}` | 미션 상태 조회 |
| Zone | `GET` | `/api/v1/zones` | 구역 목록 |
| Plant | `GET` | `/api/v1/plants` | 식물 목록 |
| Plant | `GET` | `/api/v1/plants/{plant_id}` | 식물 상세 |
| Plant | `GET` | `/api/v1/plants/{plant_id}/observations` | 식물 관측 이력 |
| Alert | `GET` | `/api/v1/alerts` | 알림 목록 |
| Alert | `POST` | `/api/v1/alerts/{alert_id}/ack` | 알림 읽음 처리 |
| Environment | `GET` | `/api/v1/environment/latest` | 최신 환경값 |
| Environment | `GET` | `/api/v1/environment/history` | 환경 시계열 |
| IoT | `GET` | `/api/v1/iot/devices` | 장치 현재 상태 |
| IoT | `GET` | `/api/v1/actuations/recommendations` | 추천 목록 조회 |
| IoT | `POST` | `/api/v1/actuations/recommendations/{id}/approve` | 추천 승인 |
| IoT | `POST` | `/api/v1/actuations/recommendations/{id}/reject` | 추천 거절 |
| IoT | `POST` | `/api/v1/actuations/watering` | 급수 명령 |
| IoT | `POST` | `/api/v1/actuations/nutrients` | 영양제 명령 |
| IoT | `GET` | `/api/v1/actuations/history` | 장치 실행 이력 |
| Harvest | `GET` | `/api/v1/harvests` | 수확 이력 |
| Harvest | `GET` | `/api/v1/harvests/stats` | 수확 통계 |
| Media | `GET` | `/api/v1/media/{asset_id}` | 이미지 메타/다운로드 정보 |
| Realtime | `WS` | `/ws/live` | 실시간 이벤트 구독 |

## 6. 상세 명세

### 6-1. `GET /api/v1/dashboard/summary`

목적:
메인 대시보드 카드에 필요한 요약값을 한 번에 내려줍니다.

주요 조회 테이블:

- `robots`
- `missions`
- `alerts`
- `environment_samples`
- `iot_devices`
- `harvest_events`

응답 예시:

```json
{
  "data": {
    "robot": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "status": "PATROL",
      "battery_level": 76.5,
      "current_zone_id": "zone_A"
    },
    "missions": {
      "active_count": 1,
      "current": {
        "id": "d4d69b93-e6cf-455f-95ec-f4c6a0f366f3",
        "mission_type": "PATROL",
        "status": "RUNNING",
        "progress_percent": 35
      }
    },
    "alerts": {
      "unacked_count": 2,
      "critical_count": 1
    },
    "environment": {
      "zone_count": 3,
      "latest_recorded_at": "2026-03-16T16:20:00+09:00"
    },
    "iot": {
      "online_count": 8,
      "error_count": 1
    },
    "harvest": {
      "today_success_count": 12,
      "today_failure_count": 1,
      "basket_count": 7
    }
  }
}
```

### 6-2. `GET /api/v1/robot/status`

목적:
현재 로봇 상태 카드와 실시간 상태 화면용 데이터 조회

응답 핵심 필드:

- `id`
- `name`
- `status`
- `battery_level`
- `current_zone_id`
- `speed_mps`
- `error_message`
- `updated_at`

### 6-3. `GET /api/v1/robot/pose`

목적:
지도 위에 로봇 위치와 방향 표시

응답 예시:

```json
{
  "data": {
    "robot_id": "550e8400-e29b-41d4-a716-446655440000",
    "pose": {
      "x": 2.4,
      "y": 1.1,
      "yaw": 1.57,
      "frame_id": "map"
    },
    "current_zone_id": "zone_B",
    "updated_at": "2026-03-16T16:21:00+09:00"
  }
}
```

### 6-4. `POST /api/v1/robot/commands`

목적:
긴급 정지, 재개, 수동 이동 같은 로봇 명령 발행

주의:
현재 DB 스키마에는 별도 `robot_commands` 테이블이 없습니다.
P0에서는 MQTT 발행 후 `robots`, `missions`, `alerts` 상태 갱신으로 추적합니다.
나중에 감사 로그가 필요해지면 `robot_command_logs` 테이블을 추가하는 것을 권장합니다.

요청 예시:

```json
{
  "robot_id": "550e8400-e29b-41d4-a716-446655440000",
  "command_type": "EMERGENCY_STOP",
  "requested_by": "user:dashboard",
  "target_zone_id": null,
  "payload": {
    "reason": "manual safety stop"
  }
}
```

서버 동작:

1. 입력 검증
2. MQTT `agribot/commands/mission` 발행
3. 필요 시 `alerts` 또는 `missions` 상태 변경 대기

응답 예시:

```json
{
  "data": {
    "accepted": true,
    "command_type": "EMERGENCY_STOP",
    "published_topic": "agribot/commands/mission"
  }
}
```

### 6-5. `POST /api/v1/missions/patrol/start`

목적:
순찰 시작

요청 예시:

```json
{
  "robot_id": "550e8400-e29b-41d4-a716-446655440000",
  "zone_ids": ["zone_A", "zone_B"],
  "loop_count": 1,
  "requested_by": "user:dashboard"
}
```

서버 동작:

1. `missions`에 새 미션 생성
2. MQTT `agribot/commands/mission` 발행

응답 예시:

```json
{
  "data": {
    "mission_id": "d4d69b93-e6cf-455f-95ec-f4c6a0f366f3",
    "mission_type": "PATROL",
    "status": "PENDING"
  }
}
```

### 6-6. `POST /api/v1/missions/patrol/stop`

목적:
순찰 중지

요청 예시:

```json
{
  "robot_id": "550e8400-e29b-41d4-a716-446655440000",
  "requested_by": "user:dashboard",
  "reason": "manual pause"
}
```

### 6-7. `POST /api/v1/missions/return-home`

목적:
로봇 홈 복귀

요청 예시:

```json
{
  "robot_id": "550e8400-e29b-41d4-a716-446655440000",
  "requested_by": "user:dashboard"
}
```

### 6-8. `POST /api/v1/missions/harvest`

목적:
특정 토마토 수확 요청

요청 예시:

```json
{
  "robot_id": "550e8400-e29b-41d4-a716-446655440000",
  "plant_id": "plant_101",
  "fruit_id": "fruit_03",
  "requested_by": "user:dashboard"
}
```

서버 동작:

1. `missions`에 `HARVEST` 미션 생성
2. MQTT `agribot/commands/mission` 발행
3. 완료 시 `harvest_events` 적재 대기

응답 예시:

```json
{
  "data": {
    "mission_id": "08b95daa-d0ba-4870-9ed7-a75a72cc56dd",
    "target_fruit_id": "fruit_03",
    "status": "PENDING"
  }
}
```

### 6-9. `GET /api/v1/missions/{mission_id}`

목적:
미션 진행률, 현재 단계, 재시도 횟수 조회

응답 핵심 필드:

- `mission_type`
- `status`
- `current_step`
- `progress_percent`
- `retry_count`
- `started_at`
- `completed_at`

### 6-10. `GET /api/v1/zones`

목적:
구역 목록 및 기본 메타데이터 조회

응답 핵심 필드:

- `id`
- `name`
- `bounds`
- `description`

### 6-11. `GET /api/v1/plants`

목적:
식물 목록/필터 조회

쿼리 파라미터:

- `zone_id`
- `crop_name`
- `needs_water`
- `ready_to_harvest`
- `page`
- `size`

응답 핵심 필드:

- `id`
- `zone_id`
- `crop_name`
- `health_score`
- `growth_stage`
- `needs_water`
- `ready_to_harvest`
- `last_observed_at`

### 6-12. `GET /api/v1/plants/{plant_id}`

목적:
특정 식물 상세 조회

응답 예시:

```json
{
  "data": {
    "id": "plant_101",
    "zone_id": "zone_A",
    "crop_name": "tomato",
    "position": {
      "x": 1.2,
      "y": 3.4,
      "z": 0.0
    },
    "health_score": 0.82,
    "growth_stage": 0.70,
    "needs_water": true,
    "ready_to_harvest": true,
    "fruits": [
      {
        "id": "fruit_03",
        "ripeness_stage": "RIPE",
        "ready_to_harvest": true,
        "current_status": "VISIBLE"
      }
    ],
    "last_observed_at": "2026-03-16T16:05:00+09:00"
  }
}
```

### 6-13. `GET /api/v1/plants/{plant_id}/observations`

목적:
식물 관측 이력 조회

쿼리 파라미터:

- `from`
- `to`
- `limit`

응답 핵심 필드:

- `class_name`
- `confidence`
- `health_score`
- `ready_to_harvest`
- `observed_at`
- `image_path`

### 6-14. `GET /api/v1/alerts`

목적:
알림 목록 조회

쿼리 파라미터:

- `severity`
- `alert_type`
- `zone_id`
- `acknowledged`
- `page`
- `size`

응답 핵심 필드:

- `id`
- `alert_type`
- `severity`
- `message`
- `zone_id`
- `plant_id`
- `detected_at`
- `acknowledged_at`

### 6-15. `POST /api/v1/alerts/{alert_id}/ack`

목적:
알림 읽음 처리

요청 예시:

```json
{
  "acknowledged_by": "user:dashboard"
}
```

응답 예시:

```json
{
  "data": {
    "id": "afe2ff8c-7b43-4f50-8f9c-9de1cf4ec67e",
    "acknowledged_at": "2026-03-16T16:30:00+09:00",
    "acknowledged_by": "user:dashboard"
  }
}
```

### 6-16. `GET /api/v1/environment/latest`

목적:
구역별 최신 환경값 조회

쿼리 파라미터:

- `zone_id` 선택

응답 핵심 필드:

- `zone_id`
- `temperature`
- `humidity`
- `soil_moisture`
- `light_level`
- `co2_level`
- `recorded_at`

### 6-17. `GET /api/v1/environment/history`

목적:
환경 시계열 조회

쿼리 파라미터:

- `zone_id` 필수
- `from`
- `to`
- `interval` 예) `raw`, `5m`, `1h`

### 6-18. `GET /api/v1/iot/devices`

목적:
장치 현재 상태 조회

쿼리 파라미터:

- `zone_id`
- `device_type`
- `control_mode`
- `is_online`

응답 예시:

```json
{
  "data": [
    {
      "id": "sprinkler_1",
      "zone_id": "farm_01",
      "device_type": "SPRINKLER",
      "display_name": "Farm 01 Sprinkler 1",
      "control_mode": "AUTO",
      "current_state": "RUNNING",
      "current_value": 3,
      "value_unit": "sec",
      "is_online": true,
      "last_seen_at": "2026-03-16T16:31:00+09:00"
    }
  ]
}
```

### 6-19. `GET /api/v1/actuations/recommendations`

목적:
IoT 자동 추천 목록 조회

왜 필요한가:
가이드 문서에는 영양제는 "추천은 자동, 실행은 승인 후"라고 되어 있습니다.
그래서 추천 목록을 별도 조회하는 API가 필요합니다.

쿼리 파라미터:

- `zone_id`
- `device_id`
- `status`
- `approval_required`
- `page`
- `size`

응답 핵심 필드:

- `id`
- `recommendation_type`
- `reason_code`
- `reason_text`
- `suggested_value`
- `value_unit`
- `priority`
- `approval_required`
- `status`

### 6-20. `POST /api/v1/actuations/recommendations/{id}/approve`

목적:
추천 승인 후 실제 명령으로 전환

요청 예시:

```json
{
  "reviewed_by": "user:dashboard",
  "auto_execute": true
}
```

서버 동작:

1. `actuation_recommendations.status = APPROVED`
2. `reviewed_by`, `reviewed_at` 저장
3. `auto_execute = true`이면 `actuation_commands` 생성
4. MQTT `agribot/commands/actuation` 발행

응답 예시:

```json
{
  "data": {
    "recommendation_id": "53adfc2d-2b2d-4106-8fa2-ea6dd19bc4c6",
    "status": "APPROVED",
    "command_id": "9f118c26-7c1f-4b3d-aec8-6d90f3b4f138"
  }
}
```

### 6-21. `POST /api/v1/actuations/recommendations/{id}/reject`

목적:
추천 거절

요청 예시:

```json
{
  "reviewed_by": "user:dashboard",
  "comment": "skip for now"
}
```

### 6-22. `POST /api/v1/actuations/watering`

목적:
급수 명령 생성

요청 예시:

```json
{
  "zone_id": "zone_A",
  "device_id": "pump_zone_a",
  "target_value": 300,
  "value_unit": "ml",
  "requested_by": "user:dashboard",
  "request_source": "USER_BUTTON",
  "recommendation_id": null
}
```

서버 동작:

1. `actuation_commands` insert
2. MQTT `agribot/commands/actuation` 발행

응답 예시:

```json
{
  "data": {
    "command_id": "ad440a5d-574a-4573-9b8f-fb0fc4e72c66",
    "command_type": "WATERING",
    "command_status": "REQUESTED"
  }
}
```

### 6-23. `POST /api/v1/actuations/nutrients`

목적:
영양제 실행

요청 예시:

```json
{
  "zone_id": "zone_A",
  "device_id": "nutrient_zone_a",
  "target_value": 120,
  "value_unit": "ml",
  "requested_by": "user:dashboard",
  "request_source": "USER_BUTTON",
  "recommendation_id": "53adfc2d-2b2d-4106-8fa2-ea6dd19bc4c6",
  "command_payload": {
    "nutrient_type": "calcium_boost"
  }
}
```

### 6-24. `GET /api/v1/actuations/history`

목적:
장치 실행 이력 조회

주요 조회 테이블:

- `actuation_commands`
- `actuation_logs`
- `iot_devices`

쿼리 파라미터:

- `zone_id`
- `device_id`
- `command_type`
- `result`
- `from`
- `to`
- `page`
- `size`

응답 핵심 필드:

- `command_id`
- `device_id`
- `command_type`
- `requested_by`
- `command_status`
- `result`
- `result_message`
- `state_after`
- `started_at`
- `finished_at`

### 6-25. `GET /api/v1/harvests`

목적:
수확 이력 조회

쿼리 파라미터:

- `zone_id`
- `plant_id`
- `fruit_id`
- `success`
- `date_from`
- `date_to`
- `page`
- `size`

응답 핵심 필드:

- `fruit_id`
- `plant_id`
- `success`
- `fail_reason`
- `basket_count`
- `harvested_at`

### 6-26. `GET /api/v1/harvests/stats`

목적:
일별/주별 수확 통계 조회

쿼리 파라미터:

- `group_by`: `day`, `week`
- `date_from`
- `date_to`
- `zone_id`

응답 예시:

```json
{
  "data": {
    "group_by": "day",
    "items": [
      {
        "bucket": "2026-03-16",
        "success_count": 12,
        "failure_count": 1
      }
    ]
  }
}
```

### 6-27. `GET /api/v1/media/{asset_id}`

목적:
이미지 메타데이터 또는 다운로드 URL 조회

응답 핵심 필드:

- `id`
- `file_path`
- `media_type`
- `captured_at`

### 6-28. `WS /ws/live`

목적:
대시보드 실시간 반영

권장 이벤트 타입:

| event | 설명 |
| --- | --- |
| `robot.status.updated` | 로봇 상태 갱신 |
| `mission.updated` | 미션 상태 갱신 |
| `alert.created` | 새 알림 발생 |
| `environment.sample.updated` | 환경값 갱신 |
| `iot.device.updated` | 장치 상태 갱신 |
| `actuation.log.created` | 실행 결과 추가 |
| `harvest.event.created` | 수확 이벤트 발생 |

메시지 예시:

```json
{
  "event": "iot.device.updated",
  "timestamp": "2026-03-16T16:40:00+09:00",
  "data": {
    "id": "sprinkler_1",
    "zone_id": "farm_01",
    "current_state": "RUNNING",
    "current_value": 3,
    "value_unit": "sec"
  }
}
```

## 7. REST ↔ MQTT 매핑

| REST 동작 | MQTT 토픽 |
| --- | --- |
| `POST /api/v1/robot/commands` | `agribot/commands/mission` |
| `POST /api/v1/missions/patrol/start` | `agribot/commands/mission` |
| `POST /api/v1/missions/patrol/stop` | `agribot/commands/mission` |
| `POST /api/v1/missions/return-home` | `agribot/commands/mission` |
| `POST /api/v1/missions/harvest` | `agribot/commands/mission` |
| `POST /api/v1/actuations/*` | `agribot/commands/actuation` |
| 장치 상태 수신 | `agribot/iot/device_state` |
| 장치 실행 결과 수신 | `agribot/iot/command_result` |
| 환경값 수신 | `agribot/environment/{zone_id}` |
| 관측 결과 수신 | `agribot/observations/crops` |
| 수확 이벤트 수신 | `agribot/events/harvest` |
| 알림 수신 | `agribot/events/alert` |

## 8. 구현 우선순위

### 8-1. 먼저 구현할 API

아래는 발표용 P0에 바로 필요한 순서입니다.

1. `GET /api/v1/dashboard/summary`
2. `GET /api/v1/robot/status`
3. `POST /api/v1/missions/patrol/start`
4. `POST /api/v1/missions/return-home`
5. `GET /api/v1/plants`
6. `GET /api/v1/alerts`
7. `GET /api/v1/environment/latest`
8. `GET /api/v1/iot/devices`
9. `POST /api/v1/actuations/watering`
10. `POST /api/v1/actuations/nutrients`
11. `GET /api/v1/actuations/history`
12. `GET /api/v1/harvests`
15. `GET /ws/live`

### 8-2. IoT 추천 흐름 때문에 추가 구현이 필요한 API

가이드 문서의 "자동 추천 + 승인 후 실행"을 제대로 살리려면 아래 API를 추가하는 것이 좋습니다.

1. `GET /api/v1/actuations/recommendations`
2. `POST /api/v1/actuations/recommendations/{id}/approve`
3. `POST /api/v1/actuations/recommendations/{id}/reject`

이 3개가 있어야 영양제 승인 흐름과 추천 이유 표시가 자연스럽게 구현됩니다.
