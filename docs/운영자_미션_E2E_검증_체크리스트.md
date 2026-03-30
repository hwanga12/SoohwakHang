# 운영자 미션 E2E 검증 체크리스트

이 문서는 운영자 UI의 아래 7개 동작이 실제 런타임까지 이어지는지 확인하는 짧은 실행 문서입니다.

- `진단하기`
- `수확하기`
- `일시정지`
- `재개`
- `귀가`
- `패트롤로 병 진단`
- `패트롤로 전체 수확`

확인 목표는 아래 흐름입니다.

`프론트 버튼 -> backend API -> runtime 파일 -> ROS executor/node -> status 파일 -> 프론트 상태 반영`

## 1. 시작 전

공통 env와 runtime 디렉터리는 먼저 맞춥니다.

```bash
source <(./scripts/operator_runtime_health.sh --print-env)
./scripts/operator_runtime_health.sh --reset-runtime
```

ROS 실행 전에는 워크스페이스가 한 번 빌드돼 있어야 합니다.

```bash
cd "$AGRIBOT_WS"
source "/opt/ros/$ROS_DISTRO/setup.bash"
colcon build --symlink-install
```

아래 중 하나면 다시 빌드합니다.

- 처음 실행하는 팀원인 경우
- `install/setup.bash`가 없는 경우
- `agribot_ws/src` 아래 ROS 패키지 코드를 최근에 바꾼 경우

핵심 전제는 하나입니다.

- backend와 ROS가 같은 `AGRIBOT_RUNTIME_DIR`를 봐야 합니다.

다르면 버튼 직후 `accepted`처럼 보여도 실제 status 파일이 갱신되지 않습니다.

## 2. 실행 순서

터미널 1:

```bash
./scripts/backend_up.sh
```

터미널 2:

```bash
cd frontend
npm install
cd ..
./scripts/frontend_up.sh
```

터미널 3:

```bash
./scripts/agribot_launch.sh agribot_bringup simulation.launch.py use_iot:=false
```

터미널 4:

```bash
./scripts/mission_manager_up.sh
```

터미널 5:

```bash
./scripts/harvest_action_server_up.sh
```

## 3. 기본 점검

먼저 한 번에 확인합니다.

```bash
./scripts/operator_runtime_health.sh
```

최소 기대 결과:

- `backend` 포트 `8000`이 떠 있음
- `frontend` 포트 `5173`이 떠 있음
- `robot_manual_command_executor`
- `mission_bridge_executor`
- `patrol_node`
- `harvest_route_node`
- `robot_control_state.json`
- `robot_manual_command_status.json`
- `robot_mission_status.json` 또는 `mission_statuses/*.json`

필요하면 개별 확인도 합니다.

```bash
ros2 node list | egrep 'robot_manual_command_executor|mission_bridge_executor|patrol_node|harvest_route_node'
find "$AGRIBOT_RUNTIME_DIR" -maxdepth 2 -type f | sort
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
curl -s http://localhost:8000/api/v1/robot/control/status | jq
```

## 4. 시나리오별 체크

### 4-1. 진단하기

UI:

1. 메인페이지에서 식물을 선택합니다.
2. 식물 모달에서 `진단하기`를 누릅니다.

확인:

```bash
cat "$AGRIBOT_RUNTIME_DIR/robot_manual_command.json" | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_manual_command_status.json" | jq
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
```

기대:

- `command_type`이 `navigate_to_pose`
- status가 `pending -> running -> succeeded/failed`
- 프론트 상태 문구도 같은 흐름

실패 징후:

- command 파일만 생기고 status 파일은 없음
- `/robot/commands/latest`가 계속 `idle`

### 4-2. 수확하기

UI:

1. 수확 가능한 식물을 선택합니다.
2. 모달에서 `수확하기`를 누릅니다.

확인:

```bash
cat "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json" | jq
MISSION_ID="$(jq -r '.mission_id' "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json")"
curl -s "http://localhost:8000/api/v1/missions/$MISSION_ID" | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_mission_status.json" | jq
```

기대:

- `request_type`이 `harvest_target`
- `plant_id`, `fruit_id`, `tomato_id`가 들어 있음
- status가 `pending -> running -> succeeded/failed`

실패 징후:

- request 파일은 있는데 mission status가 계속 없음
- `/api/v1/missions/{mission_id}`가 404만 반복

### 4-3. 패트롤로 병 진단

UI:

1. 오른쪽 조작판에서 `패트롤로 병 진단`을 누릅니다.

확인:

```bash
cat "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json" | jq
MISSION_ID="$(jq -r '.mission_id' "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json")"
curl -s "http://localhost:8000/api/v1/missions/$MISSION_ID" | jq
```

기대:

- `request_type`이 `start_patrol`
- `patrol_mode`가 `diagnosis`
- status가 `pending -> running -> succeeded/failed`

실패 징후:

- `patrol_mode` 누락
- `patrol_node`가 없어 running으로 안 넘어감

### 4-4. 패트롤로 전체 수확

UI:

1. 오른쪽 조작판에서 `패트롤로 전체 수확`을 누릅니다.

확인:

```bash
cat "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json" | jq
MISSION_ID="$(jq -r '.mission_id' "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json")"
curl -s "http://localhost:8000/api/v1/missions/$MISSION_ID" | jq
```

기대:

- `request_type`이 `start_patrol`
- `patrol_mode`가 `harvest`

실패 징후:

- 병 진단 패트롤과 구분 없이 같은 mode로 기록됨

### 4-5. 일시정지

UI:

1. `진단하기` 또는 패트롤/수확을 먼저 시작합니다.
2. 진행 중 `일시정지`를 누릅니다.

확인:

```bash
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_control_state.json" | jq
```

기대:

- 최근 명령이 `pause_motion` 또는 `pause_patrol`
- `control_state.mode`가 `paused`

실패 징후:

- 버튼은 눌렸는데 `control_state.mode`가 계속 `normal`
- executor 부재로 503 응답

### 4-6. 재개

UI:

1. 위 일시정지 상태에서 `재개`를 누릅니다.

확인:

```bash
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_control_state.json" | jq
```

기대:

- 최근 명령이 `resume_motion` 또는 `resume_patrol`
- `control_state.mode`가 `normal`

실패 징후:

- `paused`에서 안 풀림
- 저장된 재개 문맥 없이 `no_op`만 반복

### 4-7. 귀가

UI:

1. `귀가`를 누릅니다.

확인:

```bash
cat "$AGRIBOT_RUNTIME_DIR/robot_manual_command.json" | jq
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
```

기대:

- 최근 명령이 `return_home`
- status가 `pending/running/succeeded/failed`

실패 징후:

- 이전 명령이 그대로 남아 있음
- `return_home` 대신 다른 command type으로 기록됨

## 5. 통과 기준

아래 4개가 동시에 맞아야 통과입니다.

1. 프론트 상태 문구와 backend authoritative status가 일치한다.
2. backend와 ROS가 같은 `AGRIBOT_RUNTIME_DIR`를 사용한다.
3. 필요한 executor/node가 모두 떠 있다.
4. request 파일, status 파일, API 응답이 같은 `mission_id` 또는 `command_id`를 가리킨다.

## 6. 자주 막히는 원인

### 6-1. runtime 디렉터리 불일치

증상:

- request 파일은 생기는데 status 파일이 안 생김
- `/tmp/agribot_runtime`와 저장소 루트에 runtime 파일이 갈라져 있음

확인:

```bash
./scripts/operator_runtime_health.sh
```

### 6-2. ROS node 미기동

증상:

- 진단/수확/패트롤/귀가가 `accepted`까지만 감
- 일시정지/재개가 503 또는 no-op로 멈춤

확인:

```bash
ros2 node list | egrep 'robot_manual_command_executor|mission_bridge_executor|patrol_node|harvest_route_node'
```

### 6-3. 오래된 runtime 파일 잔존

증상:

- 이전 `mission_id`나 `command_id` 때문에 현재 동작 판별이 헷갈림

초기화:

```bash
./scripts/operator_runtime_health.sh --reset-runtime
```
