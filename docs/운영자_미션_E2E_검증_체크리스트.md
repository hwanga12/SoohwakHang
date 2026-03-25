# 운영자 미션 E2E 검증 체크리스트

이 문서는 운영자 UI에서 시작하는 아래 시나리오를 한 번에 점검하기 위한 실행 문서입니다.

- `진단하기`로 식물 좌표 이동
- `수확하기`로 harvest target 요청
- `패트롤로 병 진단`
- `패트롤로 전체 수확`
- 이동 또는 미션 진행 중 `일시정지`
- `재개`
- `귀가`

이 문서의 목적은 "버튼이 눌렸다"가 아니라 아래 흐름이 실제로 이어지는지 확인하는 것입니다.

`프론트 버튼 -> backend API -> runtime 파일 -> ROS executor/node -> status 파일 -> 프론트 상태 반영`

## 1. 적용 범위

이 체크리스트는 아래 변경이 함께 반영된 통합 환경을 기준으로 작성했습니다.

- FE-01: 메인페이지 `진단하기`가 실제 `navigate_to_pose` 호출
- ROS-01: `start_patrol`, `harvest_target` runtime bridge
- BE-01: `/missions/patrol/start`, `/missions/harvest`가 실제 request 파일 생성
- FE-02: 메인페이지 `수확하기`, `패트롤` 버튼이 authoritative mission polling 사용

즉, `develop` 단독 기준이 아니라 위 기능이 합쳐진 통합 런타임을 확인하는 문서입니다.

## 2. 사전 준비

### 2-1. 공통 환경 변수

모든 팀원이 같은 경로 규칙으로 실행할 수 있게 먼저 아래 변수를 맞춥니다.

```bash
cd /path/to/S14P21A602   # 예: cd ~/SSAFY/S14P21A602
export REPO_ROOT="$(git rev-parse --show-toplevel)"
export AGRIBOT_WS="$REPO_ROOT/agribot_ws"
export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
export AGRIBOT_RUNTIME_DIR="${AGRIBOT_RUNTIME_DIR:-/tmp/agribot_runtime}"
```

### 2-2. 가장 먼저 확인할 핵심 조건

backend와 ROS executor가 같은 runtime 디렉터리를 봐야 합니다.

```bash
echo "$AGRIBOT_RUNTIME_DIR"
```

아래 두 위치가 모두 같은 값을 써야 합니다.

- backend를 실행하는 터미널
- ROS `simulation.launch.py`를 실행하는 터미널

다르면 frontend에서는 mission이 accepted처럼 보이거나 pending 대기처럼 보이는데, 실제 status 파일이 갱신되지 않을 수 있습니다.

### 2-3. runtime 디렉터리 초기화

이전 테스트 파일이 남아 있으면 상태가 헷갈릴 수 있으므로 시작 전에 비웁니다.

```bash
rm -rf "$AGRIBOT_RUNTIME_DIR"
mkdir -p "$AGRIBOT_RUNTIME_DIR"
```

## 3. 실행 순서

### 3-1. backend 실행

```bash
cd "$REPO_ROOT/backend"
source .venv/bin/activate
export AGRIBOT_RUNTIME_DIR="$AGRIBOT_RUNTIME_DIR"
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3-2. frontend 실행

```bash
cd "$REPO_ROOT/frontend"
npm install
npm run dev
```

### 3-3. ROS 시뮬레이션 실행

```bash
cd "$AGRIBOT_WS"
source "/opt/ros/$ROS_DISTRO/setup.bash"
source install/setup.bash
export AGRIBOT_RUNTIME_DIR="$AGRIBOT_RUNTIME_DIR"
cd "$REPO_ROOT"
./scripts/agribot_launch.sh agribot_bringup simulation.launch.py
```

## 4. 런타임 기본 점검

### 4-1. 필요한 ROS 노드가 실제로 올라왔는지 확인

```bash
ros2 node list | egrep 'robot_manual_command_executor|mission_bridge_executor|patrol_node|harvest_route_node'
```

기대 결과:

- `robot_manual_command_executor`
- `mission_bridge_executor`
- `patrol_node`
- `harvest_route_node`

위 4개가 보여야 합니다.

주의:

- `mission_bridge_executor`가 없으면 `start_patrol`, `harvest_target` 요청이 status 파일로 이어지지 않습니다.
- `patrol_node`가 없으면 패트롤 미션이 실제 ROS 서비스 호출로 이어지지 않습니다.
- `harvest_route_node`가 없으면 harvest target publish 이후 실제 동작이 이어지지 않습니다.

### 4-2. runtime 파일 생성 위치 확인

```bash
find "$AGRIBOT_RUNTIME_DIR" -maxdepth 2 -type f | sort
```

기대 결과 예시:

- `robot_manual_command.json`
- `robot_manual_command_status.json`
- `robot_control_state.json`
- `robot_mission_request.json`
- `robot_mission_status.json`
- `mission_statuses/...`

### 4-3. backend 최신 명령 상태 확인

```bash
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
```

여기서 먼저 봐야 할 필드는 아래입니다.

- `data.status`
- `data.command_id`
- `data.requested_command_type`
- `data.control_state.mode`
- `data.control_state.active_activity`

## 5. 시나리오별 체크리스트

각 시나리오는 "UI에서 버튼을 눌렀을 때 어떤 파일과 상태를 같이 확인해야 하는지"까지 포함합니다.

---

## 5-1. 진단하기로 식물 좌표 이동

### UI 행동

1. 메인페이지에서 식물을 선택합니다.
2. 식물 모달에서 `진단하기`를 누릅니다.

### 확인 포인트

```bash
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_manual_command.json" | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_manual_command_status.json" | jq
```

### 기대 결과

- `robot_manual_command.json`에 `command_type: "navigate_to_pose"`가 기록됩니다.
- `/robot/commands/latest`가 `pending` 또는 `running`으로 바뀝니다.
- 완료 후 `succeeded` 또는 실패 시 `failed`로 바뀝니다.
- 메인페이지 UI도 같은 상태 흐름을 따라갑니다.

### 실패 징후

- UI는 이동 중이라고 뜨는데 `/robot/commands/latest`가 계속 `idle`
- command 파일은 생겼는데 status 파일이 갱신되지 않음
- target pose가 엉뚱한 좌표이거나 식물과 맞지 않음

---

## 5-2. 수확하기로 harvest target 요청

### UI 행동

1. 메인페이지에서 수확 가능한 식물을 선택합니다.
2. 식물 모달에서 `수확하기`를 누릅니다.

### 확인 포인트

수확 버튼 직후:

```bash
cat "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json" | jq
```

mission id 확인 후:

```bash
MISSION_ID="$(jq -r '.mission_id' "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json")"
curl -s "http://localhost:8000/api/v1/missions/$MISSION_ID" | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_mission_status.json" | jq
```

### 기대 결과

- request 파일에 아래 값이 있어야 합니다.
  - `request_type: "harvest_target"`
  - `plant_id`
  - `fruit_id`
  - `tomato_id` 또는 같은 의미의 대상 id
- mission status가 `pending -> running -> succeeded/failed`로 변합니다.
- 메인페이지는 accepted만으로 성공을 띄우지 않고, status polling 결과가 있어야 성공으로 바뀝니다.
- harvest 성공 후에는 선택 식물의 작업 상태가 `수확 완료`로 반영됩니다.

### 실패 징후

- `robot_mission_request.json`이 안 생김
- mission id는 생겼는데 `/api/v1/missions/{mission_id}`가 계속 비어 있거나 404만 반복됨
- UI는 성공인데 mission status 파일은 없음
- `harvest_route_node`가 안 떠 있어서 running 이후 진행이 멈춤

---

## 5-3. 패트롤로 병 진단

### UI 행동

1. 메인페이지 오른쪽 조작판에서 `패트롤로 병 진단`을 누릅니다.

### 확인 포인트

```bash
cat "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json" | jq
MISSION_ID="$(jq -r '.mission_id' "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json")"
curl -s "http://localhost:8000/api/v1/missions/$MISSION_ID" | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_mission_status.json" | jq
```

### 기대 결과

- request 파일에 아래 값이 있어야 합니다.
  - `request_type: "start_patrol"`
  - `patrol_mode: "diagnosis"`
  - `zone_ids`
  - `loop_count`
- UI 상태 칩이 `accepted -> pending -> running -> succeeded/failed`로 변합니다.
- 성공 시 결과 카드가 실제 패트롤 상태 메시지로 바뀝니다.

### 실패 징후

- `patrol_mode`가 누락되거나 `harvest`로 잘못 들어감
- `/api/v1/missions/{mission_id}`는 있는데 계속 `idle`
- `patrol_node`가 없어서 running으로 넘어가지 않음

---

## 5-4. 패트롤로 전체 수확

### UI 행동

1. 메인페이지 오른쪽 조작판에서 `패트롤로 전체 수확`을 누릅니다.

### 확인 포인트

```bash
cat "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json" | jq
MISSION_ID="$(jq -r '.mission_id' "$AGRIBOT_RUNTIME_DIR/robot_mission_request.json")"
curl -s "http://localhost:8000/api/v1/missions/$MISSION_ID" | jq
```

### 기대 결과

- request 파일에 `patrol_mode: "harvest"`가 기록됩니다.
- 병 진단 패트롤과 구분된 상태 메시지가 UI에 표시됩니다.
- 성공/실패가 실제 mission status를 따라갑니다.

### 실패 징후

- 진단 패트롤과 같은 문구만 재사용되고 mode 구분이 안 됨
- request 파일은 `start_patrol`인데 mode가 비어 있음

---

## 5-5. 이동 또는 미션 진행 중 일시정지

### UI 행동

아래 둘 중 하나를 먼저 진행합니다.

- `진단하기`로 좌표 이동 시작
- 패트롤 또는 수확 미션을 running 상태까지 올림

그 다음 메인페이지에서 `일시정지`를 누릅니다.

### 확인 포인트

```bash
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_control_state.json" | jq
```

### 기대 결과

- `/robot/commands/latest`의 최근 명령이 `pause_motion` 또는 `pause_patrol` 계열로 바뀝니다.
- `control_state.mode`가 `paused`가 됩니다.
- frontend의 새 미션 버튼이 disabled 됩니다.

### 실패 징후

- 일시정지 버튼은 눌렸는데 `control_state.mode`가 계속 `normal`
- UI에서는 멈춘 것처럼 보이는데 실제 명령 상태는 그대로 running

---

## 5-6. 재개

### UI 행동

1. 위 일시정지 상태에서 `재개`를 누릅니다.

### 확인 포인트

```bash
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_control_state.json" | jq
```

### 기대 결과

- 최근 명령이 `resume_motion` 또는 `resume_patrol` 계열로 바뀝니다.
- `control_state.mode`가 다시 `normal`로 돌아옵니다.
- 저장된 문맥이 있으면 이동 또는 순찰이 이어집니다.
- 미션 버튼이 다시 활성화됩니다.

### 실패 징후

- UI에서는 재개라고 뜨는데 `resumeAvailable`이 false 상태로 멈춤
- `control_state.mode`가 `paused`에서 바뀌지 않음

---

## 5-7. 귀가

### UI 행동

1. 이동 또는 미션이 없는 상태에서 `귀가`를 누릅니다.

### 확인 포인트

```bash
curl -s http://localhost:8000/api/v1/robot/commands/latest | jq
cat "$AGRIBOT_RUNTIME_DIR/robot_manual_command.json" | jq
```

### 기대 결과

- 최근 명령이 `return_home`로 기록됩니다.
- `/robot/commands/latest`가 `pending/running/succeeded/failed` 흐름을 따릅니다.
- 프론트 UI 상태도 같은 흐름을 따라갑니다.

### 실패 징후

- 귀가 버튼 이후도 최신 명령이 이전 값 그대로 남아 있음
- 홈 복귀인데 `navigate_to_pose` 또는 다른 명령으로 기록됨

## 6. 통합 판단 기준

아래 4개가 동시에 맞아야 "통과"로 판단합니다.

1. frontend의 상태 문구와 칩이 backend의 authoritative status와 일치한다.
2. backend와 ROS가 같은 `AGRIBOT_RUNTIME_DIR`를 사용한다.
3. `simulation.launch.py` 기준으로 필요한 executor/node가 실제로 떠 있다.
4. request 파일, status 파일, API 응답이 같은 mission id 또는 command id를 가리킨다.

## 7. 자주 막히는 원인

### 7-1. runtime 디렉터리가 서로 다름

증상:

- backend accepted는 되는데 status polling이 안 바뀜

확인:

```bash
echo "$AGRIBOT_RUNTIME_DIR"
```

backend 터미널과 ROS 터미널에서 같은 값인지 각각 확인합니다.

### 7-2. simulation.launch.py에 필요한 executor가 빠짐

증상:

- 일시정지/재개/귀가는 되는데 harvest/patrol만 멈춤

확인:

```bash
ros2 node list | egrep 'mission_bridge_executor|robot_manual_command_executor|patrol_node|harvest_route_node'
```

### 7-3. frontend가 stub 성공을 표시하는 오래된 브랜치

증상:

- 버튼을 누르면 바로 성공 문구가 뜨는데 runtime status는 없음

확인:

- FE-02가 반영된 브랜치 또는 병합본인지 확인
- `/missions/harvest`, `/missions/patrol/start` accepted 응답에 `status_endpoint`가 있는지 확인

## 8. 기록 권장 항목

테스트를 끝낸 뒤 아래를 같이 남기면 회고가 쉬워집니다.

- 사용 브랜치 조합
- `AGRIBOT_RUNTIME_DIR` 값
- 실행한 launch 명령
- 실패한 시나리오 번호
- 마지막으로 확인한 `mission_id` 또는 `command_id`
- 관련 스크린샷 또는 터미널 로그
