# AgriBot

수확해조(AgriBot)는 ROS 2 Jazzy와 Gazebo Harmonic 기반의 스마트팜 자율주행 시뮬레이션 프로젝트입니다.  
로봇 시뮬레이션, FastAPI 백엔드, React 관제 프론트엔드, PostgreSQL, MQTT 브로커를 함께 사용해 병해 진단, AI 판단 이력, 수확 시나리오, IoT 제어 흐름을 통합합니다.

## 핵심 기능

- 밭 순찰, 관측 지점 이동, 수동 이동, 귀가
- 병해 진단 데모 및 AI 판단 이력 저장
- 숙도 및 수확 의사결정(`HARVEST_DECISION`) 조회
- 개별 수확 / 전체 수확 패트롤 시나리오
- PostgreSQL 기반 식물, 과실, 미션, 수확, AI 판단 데이터 관리
- Direct ROS topic bridge 기반 backend-robot 상태/제어 연동
- runtime file bridge fallback 기반 pose/path/runtime artifact 연동

## 기술 스택

| 구분 | 구성 |
| --- | --- |
| OS / Runtime | Ubuntu 24.04, Python 3.12, Node.js |
| Robot / Sim | ROS 2 Jazzy, Gazebo Harmonic, Nav2, SLAM Toolbox |
| Backend | FastAPI, SQLAlchemy, psycopg2, Uvicorn |
| Frontend | React 18, Vite 6, TypeScript |
| Data / Infra | PostgreSQL 16, pgAdmin4, Eclipse Mosquitto |
| AI | Ultralytics YOLO 기반 병해 진단 |

## 저장소 구조

```text
S14P21A602/
├── agribot_ws/   # ROS 2 workspace
├── backend/      # FastAPI, DB 모델/라우터/서비스, seed, docker-compose
├── frontend/     # React + Vite 관제 UI
├── scripts/      # 실행/점검/런타임 보조 스크립트
├── docs/         # 설계/실행/검증 문서
├── exec/         # 포팅 매뉴얼, 최신 DB dump
└── artifacts/    # 모델, 런타임 산출물, 데모 입력 리소스
```

## 사전 요구사항

- ROS 2 Jazzy
- Gazebo Harmonic 및 `ros-gz`
- Navigation2, SLAM Toolbox
- Docker / Docker Compose
- Python 3.12 + `venv`
- Node.js / npm

예시 설치:

```bash
sudo apt update
sudo apt install -y \
  ros-jazzy-desktop \
  ros-jazzy-ros-gz \
  ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup \
  ros-jazzy-slam-toolbox
```

## 최초 1회 준비

### Frontend

```bash
cd frontend
npm install
npm run build
```

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
../scripts/install_backend_runtime.sh
```

### ROS workspace

```bash
cd agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

## 실행 순서

루트에서 아래 순서대로 실행합니다.

### 1. 공통 환경 및 런타임 초기화

```bash
cd /home/ssafy/Desktop/pjt/S14P21A602
source <(./scripts/operator_runtime_health.sh --print-env)
./scripts/operator_runtime_health.sh --reset-runtime
```

### 2. Backend

```bash
./scripts/backend_up.sh
```

기본 주소:

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`

### 3. Frontend

```bash
./scripts/frontend_up.sh
```

기본 주소:

- UI: `http://127.0.0.1:5173`

### 4. ROS 시뮬레이션

헤드리스/원격 환경에서는 아래 명령을 권장합니다.

```bash
./scripts/agribot_launch.sh agribot_bringup simulation.launch.py use_iot:=true use_rviz:=false
```

### 5. Mission Manager

```bash
./scripts/mission_manager_up.sh
```

### 6. Harvest Action Server

```bash
./scripts/harvest_action_server_up.sh
```

### 7. 상태 점검

```bash
./scripts/operator_runtime_health.sh
```

## 데모 흐름

2026-03-30 기준 아래 흐름을 실제로 검증했습니다.

- 프론트 메인 화면 접속
- `진단하기` 실행 후 수동 이동 상태 추적
- `수확하기` 실행 후 수확 완료 및 basket count 반영
- 대시보드 / 로봇 상태 / 수확 통계 / AI 판단 API 정상 응답

주요 확인 API:

```bash
curl -s http://127.0.0.1:8000/api/v1/dashboard/summary | jq
curl -s http://127.0.0.1:8000/api/v1/robot/status | jq
curl -s http://127.0.0.1:8000/api/v1/robot/commands/latest | jq
curl -s http://127.0.0.1:8000/api/v1/harvests/stats | jq
curl -s "http://127.0.0.1:8000/api/v1/inference/judgments/latest?fruit_id=farm01_plant_02_tomato_01&judgment_type=HARVEST_DECISION" | jq
```

## DB 및 데모 데이터

- Docker 실행 정의: `backend/docker-compose.yml`
- 기본 DB: `agribot_db`
- 계정: `agribot / password`
- pgAdmin: `http://127.0.0.1:5050`
- 데모 데이터 재적재: `backend/seed_demo_data.py`
- 최신 dump: `exec/db/agribot_db_dump_20260330.sql`

데모 데이터 재생성:

```bash
cd backend
.venv/bin/python seed_demo_data.py
```

## 테스트

### Backend

```bash
cd backend
.venv/bin/pytest
```

### ROS packages

```bash
cd agribot_ws
source /opt/ros/jazzy/setup.bash
colcon test --packages-select agribot_bringup agribot_navigation
colcon test-result --verbose
```

## 문서

- 포팅 매뉴얼: `exec/포팅_매뉴얼.md`
- 실행/문서 인덱스: `docs/README.md`
- launch 관련 메모: `docs/README_LAUNCH.md`
- 운영자 검증 체크리스트: `docs/운영자_미션_E2E_검증_체크리스트.md`
- 프로토콜 연결 감사: `TIL/docs/프로토콜_연결_감사_및_개선안.md`

## 주의 사항

- Backend는 workspace가 build되어 있으면 direct ROS bridge를 우선 사용하고, 그렇지 않으면 legacy runtime file bridge로 fallback 합니다.
- Backend와 ROS 노드는 fallback 경로를 위해 같은 `AGRIBOT_RUNTIME_DIR`를 사용해야 합니다.
- Frontend는 정적 파일 운영 배포 구성이 아니라 Vite dev server 기준입니다.
- Backend는 Nginx/Apache 없이 Uvicorn으로 실행합니다.
- 시뮬레이터 GUI/EGL 경고가 있어도 headless 환경에서는 core ROS 노드와 file bridge가 정상 기동할 수 있습니다.
