# Observation Priority Rules

`S14P-404` 기준선용 감지 이벤트 우선순위 규칙입니다.

## 우선순위 표

| 우선순위 | 감지 조건 | event kind | 다음 미션 타입 | target_id 규칙 | 비고 |
| --- | --- | --- | --- | --- | --- |
| 1 | `class_name`에 `disease` 포함 | `diseased_leaf` | `OBSERVE` | `plant_id` 우선 | 병든 잎은 수확보다 먼저 확인 |
| 2 | `ready_to_harvest=true` 또는 `class_name`이 ripe tomato 계열 | `ripe_tomato` | `HARVEST` | `fruit_id`, 없으면 `plant_id` | 익은 토마토 수확 후보 |
| 3 | 위 둘에 해당하지 않는 관측 | `generic_observation` | `OBSERVE` | `fruit_id`, 없으면 `plant_id` | 예비 관찰 이벤트 |

## 중복 제거 규칙

- dedup key는 `zone_id + plant_id + fruit_id + event kind` 조합으로 만든다.
- 같은 dedup key가 active 상태면 새 관측은 중복으로 무시한다.
- 같은 dedup key가 최근 처리 완료된 뒤 `120초` 이내에 다시 오면 cooldown 중복으로 무시한다.
- 같은 dedup key가 pending 상태일 때는, 더 높은 priority 또는 더 높은 confidence의 이벤트만 기존 pending 후보를 갱신한다.

## tie-break 규칙

1. priority가 높은 이벤트를 먼저 처리한다.
2. priority가 같으면 confidence가 더 높은 이벤트를 먼저 처리한다.
3. 둘 다 같으면 더 먼저 들어온 이벤트를 유지한다.

## 현재 구현 범위

- `mission_manager`가 `PlantObservation`을 받아 pending/active 후보를 관리한다.
- patrol 중 higher-priority observation이 들어오면 patrol stop을 요청하고, 정지 직후 해당 observation 미션으로 전환한다.
- active observation이 완료되면 다음 pending 후보를 자동 승격한다.
- 실제 수확 액션/질병 후속 처리 자체는 후속 티켓에서 붙인다.
