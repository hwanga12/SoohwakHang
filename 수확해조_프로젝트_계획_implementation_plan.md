# 🌱 AgriBot 프로젝트 전체 기획서

스마트 농장 자율주행 채소 관리 로봇의 전체 시스템을 설계합니다.

---

## 📊 현재 상태 진단

| 항목 | 상태 | 설명 |
|------|------|------|
| 로봇 모델 (SDF) | ⚠️ 기본만 | 3D 메시만 있고 **카메라·라이다 센서 없음** |
| 월드 환경 | ✅ 기본 완성 | 비닐하우스, 토마토, 잎사귀 모델 배치됨 |
| 커스텀 메시지/서비스 | ✅ 정의됨 | `CropStatus`, `EnvironmentData`, `IoTCommand`, `SetHumidity` |
| perception 패키지 | ❌ 빈 골격 | AI 인식 로직 없음 |
| navigation 패키지 | ❌ 빈 골격 | Nav2 설정 없음 |
| control 패키지 | ❌ 빈 골격 | 모터 제어 없음 |
| iot 패키지 | ❌ 빈 골격 | IoT 통신 없음 |
| bringup 패키지 | ✅ 기본 완성 | 시뮬레이션 런치 파일 동작 확인됨 |
| 백엔드 서버 | ❌ 없음 | 데이터 저장·API 없음 |
| 사용자 UI | ❌ 없음 | 대시보드·모바일 앱 없음 |

---

## 🏗️ 시스템 아키텍처 (4계층)

```
┌──────────────────────────────────────────────────────────────────┐
│  1. 서비스 계층 (애플리케이션 & 클라우드)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
│  │ 관제 대시보드  │  │ 모바일 앱     │  │ 백엔드 (FastAPI)     │    │
│  │ (React)      │  │ (Flutter)    │  │ + PostgreSQL + MQTT  │    │
│  └──────────────┘  └──────────────┘  └──────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
        ↕ REST API / WebSocket / MQTT
┌──────────────────────────────────────────────────────────────────┐
│  2. 지능 제어 계층 (ROS 2 노드들)                                    │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐  ┌────────────┐   │
│  │ 센서 처리   │  │ 인지(YOLO) │  │ 상위 판단 │  │ 주행 실행   │   │
│  │ camera     │  │ 작물·장애물 │  │ Mission  │  │ Nav2       │   │
│  │ LiDAR·IMU  │  │ 병해 검출   │  │ BT 로직  │  │ Planner    │   │
│  └────────────┘  └────────────┘  └──────────┘  └────────────┘   │
│  ┌────────────┐  ┌────────────────────────────────────────────┐  │
│  │ IoT 브릿지  │  │ 위치추정·지도화 (SLAM / Localization)      │  │
│  └────────────┘  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
        ↕ ROS 2 Topics / Services / Actions
┌──────────────────────────────────────────────────────────────────┐
│  3. 시뮬레이션 계층 (Gazebo Harmonic)                                │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────────┐     │
│  │ 가상 센서   │  │ 비닐하우스    │  │ 로봇 모델 (agribot)  │     │
│  │ + ros_gz   │  │ + 작물 모델   │  │ + diff_drive         │     │
│  └────────────┘  └──────────────┘  └──────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
        ↕
┌──────────────────────────────────────────────────────────────────┐
│  4. 인프라 계층                                                     │
│  Ubuntu 24.04 │ ROS 2 Jazzy │ ros_gz_bridge │ Python 3.12       │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🤖 로봇에 추가해야 할 센서

현재 [agribot/model.sdf](file:///home/ssafy/SSAFY/S14P21A602/agribot_ws/src/agribot_description/models/agribot/model.sdf)에 **센서가 전혀 없습니다.** 아래 센서들을 추가해야 합니다.

| 센서 | 용도 | Gazebo 플러그인 |
|------|------|-----------------|
| **RGB-D 카메라** | 토마토 인식, 병든 잎 감지 (YOLOv8) | `gz-sim-rgbd-camera-system` |
| **2D LiDAR** | 자율주행 장애물 회피, SLAM 지도 생성 | `gz-sim-gpu-lidar-system` |
| **IMU** | 로봇 자세 추정 | `gz-sim-imu-system` |
| **Differential Drive** | 바퀴 구동 제어 | `gz-sim-diff-drive-system` |

---

## 🔄 핵심 데이터 흐름

### 병든 잎 감지 → 사용자 알림
```
카메라 이미지 → YOLOv8 추론 → 병해 판별 → ROS Topic 발행
      → IoT 브릿지 (MQTT) → 백엔드 서버 → 대시보드/모바일 푸시 알림
```

### 토마토 수확
```
카메라 이미지 → YOLOv8 추론 → 익은 토마토 감지 → 위치 추정
      → Nav2로 접근 → 수확 동작 (매니퓰레이터 or 시뮬레이션 이벤트)
      → 수확 기록 → 백엔드 DB 저장
```

### 자율 순찰
```
SLAM으로 지도 생성 → 순찰 경로 생성 (Waypoints)
      → Nav2로 경로 추종 → 카메라로 작물 모니터링
      → 물주기/영양제 필요 시 IoT 명령 발행
```

---

## 📦 패키지별 개발 계획

### 1단계: 로봇 하드웨어 (agribot_description)
> 센서를 추가하고, 바퀴 구동을 설정합니다.

- [model.sdf](file:///home/ssafy/SSAFY/S14P21A602/agribot_ws/src/agribot_description/models/agribot/model.sdf)에 RGB-D 카메라, LiDAR, IMU 센서 추가
- Differential Drive 플러그인 추가 (바퀴 2개 + 캐스터)
- `ros_gz_bridge`로 센서 데이터를 ROS 2 토픽으로 변환

### 2단계: 자율주행 (agribot_navigation)
> 지도를 만들고, 그 위에서 자율주행합니다.

- SLAM Toolbox로 비닐하우스 지도 생성
- Nav2 설정 (경로 계획, 장애물 회피, 로컬/글로벌 코스트맵)
- Waypoint 순찰 노드 작성

### 3단계: AI 인식 (agribot_perception)
> 카메라로 작물 상태를 판단합니다.

- YOLOv8 모델 학습 (토마토 익음/안익음, 병든 잎사귀)
- ROS 2 인식 노드: 카메라 이미지 → 추론 → 결과 발행
- 병해 분류 결과를 `CropStatus` 메시지로 발행

### 4단계: 제어 및 동작 (agribot_control)
> 로봇의 물리적 동작을 제어합니다.

- `cmd_vel` 처리 (Differential Drive)
- 수확 동작 시퀀스 (시뮬레이션에서는 모델 제거/이동으로 대체)
- 물주기/영양제 동작

### 5단계: IoT 통신 (agribot_iot)
> ROS 2 ↔ 외부 서비스 간 브릿지를 구현합니다.

- MQTT 클라이언트 노드 (ROS 2 토픽 → MQTT 브로커)
- 환경 데이터 수집 (가상 온습도, 토양수분 센서)
- IoT 명령 수신 및 실행

### 6단계: 백엔드 서버 (신규 패키지 or 별도 프로젝트)
> 데이터를 저장하고 API를 제공합니다.

| 구성요소 | 기술 스택 | 역할 |
|----------|-----------|------|
| **API 서버** | FastAPI (Python) | REST API 제공 |
| **데이터베이스** | PostgreSQL | 작물 상태, 수확 기록, 환경 데이터 저장 |
| **메시지 브로커** | Mosquitto (MQTT) | ROS 2 ↔ 백엔드 실시간 통신 |
| **알림 서비스** | Firebase FCM or WebSocket | 사용자에게 실시간 알림 |

#### 주요 API 예시:
```
GET  /api/crops              → 전체 작물 상태 목록
GET  /api/crops/{id}/history → 특정 작물의 상태 이력
GET  /api/diseases           → 감지된 병해 목록
POST /api/harvest            → 수확 기록 저장
GET  /api/environment        → 환경 데이터 조회
POST /api/robot/command      → 로봇에게 명령 전달
GET  /api/watering/history   → 물주기 이력
GET  /api/nutrients          → 영양제 투여 현황/권장량
```

### 7단계: 사용자 인터페이스 (신규 프로젝트)
> 사용자가 농장을 모니터링하고 제어합니다.

#### 관제 대시보드 (웹) — React 기반
| 화면 | 표시 내용 |
|------|-----------|
| **메인 대시보드** | 로봇 위치(지도), 환경 상태(온습도), 작물 건강도 요약 |
| **작물 관리** | 각 작물의 건강도, 성장 단계, 수확 이력 |
| **병해 알림** | 병든 잎사귀 사진, 병명, 감지 시간, 위치 |
| **수확 현황** | 수확된 토마토 수, 일별/주별 통계 |
| **물주기/영양제** | 물 준 시간, 영양제 투여량, 권장 영양제 정보 |
| **로봇 제어** | 수동 조종, 순찰 경로 설정, 긴급 정지 |

#### 모바일 앱 (선택사항) — Flutter 또는 React Native
- 푸시 알림 (병든 잎 발견, 수확 완료 등)
- 간단한 현황 조회

---

## 🗓️ 주차별 상세 개발 가이드 (7주)

> **읽는 법**: 각 주차는 "이번 주 목표 → 핵심 개념 → 구체적 작업 → 확인 방법" 순서입니다.
> 위에서 아래로 순서대로 읽으면 전체 흐름이 보입니다!

---

### 📅 1주차: 🤖 로봇에 센서 달기

> **이번 주 목표**: Gazebo 안의 로봇이 "눈(카메라)"과 "귀(LiDAR)"를 갖고, "다리(바퀴)"로 움직이게 만듭니다.

#### 🧠 이번 주에 알아야 할 핵심 개념
| 용어 | 쉬운 설명 |
|------|-----------|
| **SDF 파일** | 로봇의 설계도. XML 형식으로 생김새, 센서, 바퀴를 정의합니다 |
| **센서 플러그인** | Gazebo에서 카메라/라이다 등을 시뮬레이션해주는 부품 |
| **Differential Drive** | 양쪽 바퀴 속도를 다르게 해서 방향을 바꾸는 구동 방식 (로봇 청소기처럼) |
| **ros_gz_bridge** | Gazebo의 센서 데이터를 ROS 2로 넘겨주는 통역사 |
| **Topic** | ROS 2에서 데이터가 흐르는 파이프라인 (예: `/camera/image` → 카메라 이미지가 흐름) |

#### ✅ 구체적 작업 순서

**작업 1-1: 로봇 SDF에 센서 추가**
- 파일: `agribot_ws/src/agribot_description/models/agribot/model.sdf`
- 추가할 센서:
  - **RGB-D 카메라**: 토마토 색상 인식, 병든 잎 사진 촬영용
  - **2D LiDAR**: 주변 장애물 감지, 지도 만들기용
  - **IMU**: 로봇이 기울어졌는지 감지
- 바퀴 추가: 왼쪽 바퀴 + 오른쪽 바퀴 + 보조 캐스터(바퀴)

**작업 1-2: Differential Drive 플러그인 추가**
- `model.sdf` 안에 `gz-sim-diff-drive-system` 플러그인 추가
- 이렇게 하면 `/cmd_vel` 토픽으로 "앞으로 가", "왼쪽으로 돌아" 같은 명령을 보낼 수 있음

**작업 1-3: ros_gz_bridge 설정**
- `spawn_agribot.launch.py`에 브릿지 노드 추가
- Gazebo 센서 데이터 → ROS 2 토픽으로 매핑:
  - 카메라 이미지 → `/agribot/camera/image`
  - LiDAR 스캔 → `/agribot/lidar/scan`
  - IMU 데이터 → `/agribot/imu/data`

**작업 1-4: 빌드 및 테스트**
```bash
# 빌드
cd ~/SSAFY/S14P21A602/agribot_ws
colcon build --symlink-install
source install/setup.bash

# 시뮬레이션 실행
ros2 launch agribot_bringup simulation.launch.py
```

#### 🔍 확인 방법 (이렇게 되면 성공!)
```bash
# 1. 토픽 목록 확인 — 카메라, 라이다 토픽이 보이면 성공
ros2 topic list

# 2. 카메라 이미지 확인
ros2 topic echo /agribot/camera/image --once

# 3. 키보드로 로봇 조종 테스트
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/agribot/cmd_vel
```
→ **키보드 WASD로 로봇이 움직이면 1주차 완료!** 🎉

---

### 📅 2주차: 🗺️ 지도 만들기 & 자율주행

> **이번 주 목표**: 로봇이 비닐하우스 안을 돌아다니며 지도를 만들고, 그 지도 위에서 목적지까지 스스로 찾아가게 합니다.

#### 🧠 이번 주에 알아야 할 핵심 개념
| 용어 | 쉬운 설명 |
|------|-----------|
| **SLAM** | 돌아다니면서 동시에 지도를 만드는 기술 (Simultaneous Localization And Mapping) |
| **Nav2** | ROS 2의 자율주행 프레임워크. 경로 계획 + 장애물 회피를 해줌 |
| **Costmap** | 로봇이 "여기는 지나가도 됨 / 여기는 벽" 이라고 판단하는 지도 |
| **Waypoint** | 로봇이 순서대로 방문할 좌표 목록 (순찰 경로) |
| **AMCL** | 지도 위에서 "나는 지금 여기에 있다"를 추정하는 기술 |

#### ✅ 구체적 작업 순서

**작업 2-1: SLAM Toolbox 설정 및 지도 생성**
- `agribot_navigation/config/` 에 SLAM 설정 파일(YAML) 작성
- 런치 파일 작성: SLAM + 로봇 + Gazebo를 한 번에 실행
- 키보드로 로봇을 조종하면서 비닐하우스 지도를 완성
- 완성된 지도를 `.pgm` + `.yaml` 파일로 저장
```bash
# 지도 저장 명령어
ros2 run nav2_map_server map_saver_cli -f ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/maps/greenhouse_map
```

**작업 2-2: Nav2 설정**
- `agribot_navigation/config/nav2_params.yaml` 작성
- 주요 설정: 로봇 크기, 장애물 감지 범위, 최대 속도 등
- Nav2 런치 파일 작성

**작업 2-3: 자율주행 테스트**
- RViz2에서 "2D Goal Pose"로 목적지를 찍으면 로봇이 스스로 이동
- 장애물을 피해서 가는지 확인

**작업 2-4: Waypoint 순찰 노드 작성**
- `agribot_navigation/agribot_navigation/patrol_node.py` 작성
- 토마토 밭 구역을 순서대로 방문하는 좌표 리스트 정의
- 하나의 구역에 도착하면 → 잠시 멈추고 카메라로 관찰 → 다음 구역으로 이동

#### 🔍 확인 방법
```bash
# RViz2에서 지도 위에 로봇 위치가 표시되고,
# 목표 지점을 찍으면 로봇이 스스로 이동하면 성공!
ros2 launch agribot_navigation navigation.launch.py
```
→ **RViz2에서 목표점을 찍으면 로봇이 장애물을 피해 도착하면 2주차 완료!** 🎉

---

### 📅 3주차: 🧠 AI로 토마토와 병든 잎 인식하기

> **이번 주 목표**: 카메라 이미지에서 "익은 토마토"와 "병든 잎사귀"를 자동으로 찾아내는 AI를 만듭니다.

#### 🧠 이번 주에 알아야 할 핵심 개념
| 용어 | 쉬운 설명 |
|------|-----------|
| **YOLOv8** | 이미지에서 물체를 실시간으로 찾아내는 AI 모델 (매우 빠름) |
| **데이터셋** | AI를 학습시키기 위한 사진 모음 + "이 사진에 토마토가 여기 있어" 라는 정답지 |
| **학습(Training)** | AI 모델에게 사진을 보여주며 "토마토는 이렇게 생겼어"를 가르치는 과정 |
| **추론(Inference)** | 학습된 AI가 새로운 사진을 보고 "여기에 토마토가 있네!"라고 판단하는 과정 |
| **바운딩 박스(BBox)** | AI가 물체를 찾으면 그려주는 사각형 테두리 |

#### ✅ 구체적 작업 순서

**작업 3-1: 데이터셋 준비**
- 토마토 이미지 수집 (인터넷, Gazebo 시뮬레이션 캡처)
- 라벨링: 각 이미지에서 토마토/병든 잎의 위치를 표시
  - 무료 도구: [Roboflow](https://roboflow.com) 또는 [CVAT](https://cvat.ai)
- 분류 클래스 예시:
  - `ripe_tomato` (익은 토마토) — 빨간색
  - `unripe_tomato` (안 익은 토마토) — 초록색
  - `diseased_leaf` (병든 잎) — 갈색 반점, 시든 잎
  - `healthy_leaf` (건강한 잎) — 정상 초록 잎

**작업 3-2: YOLOv8 모델 학습**
```bash
# ultralytics 설치
pip install ultralytics

# 학습 실행 (GPU가 있으면 빠름, 없으면 CPU로도 가능)
yolo train model=yolov8n.pt data=dataset.yaml epochs=100 imgsz=640
```
- 학습 결과: `best.pt` 파일 (이것이 학습된 AI 모델)

**작업 3-3: ROS 2 인식 노드 작성**
- `agribot_perception/agribot_perception/detector_node.py` 작성
- 하는 일:
  1. 카메라 토픽(`/agribot/camera/image`)에서 이미지를 받음
  2. YOLOv8 모델(`best.pt`)로 추론
  3. 결과를 `CropStatus` 메시지로 발행
  4. 병든 잎이 발견되면 `/disease_alert` 토픽으로 알림 발행

**작업 3-4: 인식 결과 시각화**
- RViz2에서 카메라 이미지 위에 바운딩 박스가 그려지는지 확인
- 감지된 객체 정보가 ROS 토픽으로 나오는지 확인

#### 🔍 확인 방법
```bash
# 인식 노드 실행
ros2 run agribot_perception detector_node

# 다른 터미널에서 결과 확인
ros2 topic echo /crop_status
ros2 topic echo /disease_alert
```
→ **카메라에 토마토가 보이면 "ripe_tomato detected!" 메시지가 뜨면 3주차 완료!** 🎉

---

### 📅 4주차: 🔗 인식 + 자율주행 통합 & IoT

> **이번 주 목표**: AI가 토마토를 발견하면 로봇이 자동으로 다가가고, 센서 데이터를 외부로 전송합니다.

#### 🧠 이번 주에 알아야 할 핵심 개념
| 용어 | 쉬운 설명 |
|------|-----------|
| **Behavior Tree (BT)** | 로봇의 의사결정 로직을 나무 구조로 표현 ("만약 토마토 발견 → 다가감 → 수확") |
| **MQTT** | IoT 기기들이 메시지를 주고받는 경량 프로토콜 (카카오톡 같은 것) |
| **브로커** | MQTT 메시지를 중계해주는 서버 (우체국 같은 역할) |
| **Action** | ROS 2에서 "시간이 오래 걸리는 작업"을 요청하고 진행상황을 확인하는 방식 |

#### ✅ 구체적 작업 순서

**작업 4-1: 미션 매니저 노드 작성**
- `agribot_control/agribot_control/mission_manager.py` 작성
- 행동 로직:
  1. 순찰 중 → AI가 익은 토마토 감지 → Nav2에 "토마토 위치로 이동" 요청
  2. 토마토에 도착 → 수확 동작 (시뮬레이션에서는 토마토 모델 제거)
  3. 병든 잎 감지 → 알림 토픽 발행 + MQTT로 외부 전송
  4. 순찰 완료 → 물주기 필요 구역에 물 공급

**작업 4-2: MQTT 브릿지 구축**
```bash
# Mosquitto (MQTT 브로커) 설치
sudo apt install mosquitto mosquitto-clients

# Python MQTT 라이브러리 설치
pip install paho-mqtt
```
- `agribot_iot/agribot_iot/mqtt_bridge_node.py` 작성
- 하는 일:
  - ROS 2 토픽 → MQTT 메시지로 변환하여 외부 전송
  - 예: `/disease_alert` → MQTT `agribot/alerts/disease`
  - 예: `/crop_status` → MQTT `agribot/crops/status`

**작업 4-3: 가상 환경 센서 노드**
- `agribot_iot/agribot_iot/environment_sensor_node.py` 작성
- 가상의 온도/습도/토양수분 데이터를 생성하여 `EnvironmentData` 메시지로 발행
- 이 데이터도 MQTT를 통해 백엔드로 전송

**작업 4-4: 통합 테스트**
- 전체 시나리오: 로봇 출발 → 순찰 → 토마토 발견 → 수확 → 병든 잎 발견 → 알림

#### 🔍 확인 방법
```bash
# MQTT 메시지 모니터링
mosquitto_sub -t "agribot/#" -v

# 전체 시스템 실행
ros2 launch agribot_bringup full_system.launch.py
```
→ **로봇이 순찰하다 토마토를 발견하고 자동으로 다가가면 4주차 완료!** 🎉

---

### 📅 5주차: 🖥️ 백엔드 서버 구축

> **이번 주 목표**: 로봇의 데이터를 저장하고, 웹/앱에서 조회할 수 있는 API 서버를 만듭니다.

#### 🧠 이번 주에 알아야 할 핵심 개념
| 용어 | 쉬운 설명 |
|------|-----------|
| **FastAPI** | Python으로 REST API를 빠르게 만들 수 있는 프레임워크 |
| **REST API** | 웹에서 데이터를 주고받는 약속 (GET=조회, POST=저장, PUT=수정, DELETE=삭제) |
| **PostgreSQL** | 데이터를 저장하는 데이터베이스 (엑셀 같지만 더 강력함) |
| **ORM (SQLAlchemy)** | Python 코드로 DB를 조작 (SQL을 직접 안 써도 됨) |
| **Docker** | 서버 환경을 패키징해서 어디서든 동일하게 실행 가능하게 해주는 도구 |

#### ✅ 구체적 작업 순서

**작업 5-1: 프로젝트 초기 설정**
```bash
# 백엔드 폴더 생성
mkdir -p ~/SSAFY/S14P21A602/backend/app/{models,routers,services,mqtt}

# 필요한 패키지 설치
pip install fastapi uvicorn sqlalchemy asyncpg paho-mqtt python-dotenv
```

**작업 5-2: 데이터베이스 테이블 설계**
| 테이블 | 저장하는 정보 | 주요 컬럼 |
|--------|---------------|-----------|
| `crops` | 개별 작물 정보 | id, name, position, health_score, growth_stage |
| `diseases` | 병해 감지 기록 | id, crop_id, disease_name, detected_at, image_url |
| `harvests` | 수확 기록 | id, crop_id, harvested_at, quantity |
| `watering_logs` | 물주기 기록 | id, zone_id, watered_at, amount_ml |
| `environment_data` | 환경 센서 기록 | id, zone_id, temperature, humidity, soil_moisture, recorded_at |
| `nutrient_recommendations` | 영양제 권장 | id, crop_id, nutrient_type, recommended_amount |

**작업 5-3: API 엔드포인트 개발**
- `backend/app/main.py` — FastAPI 앱 생성
- `backend/app/routers/crops.py` — 작물 관련 API
- `backend/app/routers/diseases.py` — 병해 관련 API
- `backend/app/routers/harvests.py` — 수확 관련 API
- `backend/app/routers/environment.py` — 환경 데이터 API
- `backend/app/routers/watering.py` — 물주기 관련 API

**작업 5-4: MQTT 수신 서비스**
- `backend/app/mqtt/listener.py` — MQTT 구독 + DB 저장
- 로봇이 보내는 MQTT 메시지를 받아서 자동으로 DB에 저장

**작업 5-5: Docker로 DB + MQTT 브로커 실행**
```yaml
# backend/docker-compose.yml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: agribot
      POSTGRES_PASSWORD: password
    ports: ["5432:5432"]
  
  mosquitto:
    image: eclipse-mosquitto:2
    ports: ["1883:1883"]
```
```bash
# 실행
cd ~/SSAFY/S14P21A602/backend
docker-compose up -d

# API 서버 실행
uvicorn app.main:app --reload --port 8000
```

#### 🔍 확인 방법
- 브라우저에서 `http://localhost:8000/docs` 접속 → Swagger API 문서가 보이면 성공
- API 테스트: 각 엔드포인트를 클릭하여 데이터 조회/저장 테스트

→ **Swagger에서 API를 테스트하고 DB에 데이터가 저장되면 5주차 완료!** 🎉

---

### 📅 6주차: 📱 사용자 대시보드 개발

> **이번 주 목표**: 사용자가 웹 브라우저에서 농장 현황을 실시간으로 모니터링합니다.

#### 🧠 이번 주에 알아야 할 핵심 개념
| 용어 | 쉬운 설명 |
|------|-----------|
| **React** | 웹 UI를 만드는 JavaScript 프레임워크 |
| **컴포넌트** | 레고 블록처럼 조합하는 UI 조각 (버튼, 카드, 차트 등) |
| **WebSocket** | 서버와 실시간 양방향 통신 (채팅처럼 즉시 데이터 수신) |
| **차트 라이브러리** | 온도/습도 그래프를 그려주는 도구 (Recharts, Chart.js) |

#### ✅ 구체적 작업 순서

**작업 6-1: React 프로젝트 생성**
```bash
cd ~/SSAFY/S14P21A602
npx -y create-vite@latest frontend -- --template react
cd frontend && npm install
```

**작업 6-2: 주요 화면 구현**

| 화면 | 표시 내용 | 데이터 출처 (API) |
|------|-----------|-------------------|
| **메인 대시보드** | 로봇 상태, 환경 요약, 최근 알림 | 여러 API 조합 |
| **작물 현황** | 작물별 건강도 카드, 성장 단계 바 | `GET /api/crops` |
| **병해 알림** 🔴 | 병 이름, 사진, 감지 시각, 위치 | `GET /api/diseases` |
| **수확 통계** | 일별/주별 수확량 차트 | `GET /api/harvests` |
| **물주기 이력** | 언제 물을 줬는지 타임라인 | `GET /api/watering/history` |
| **영양제 권장** | 병해 기반 영양제 종류/양 추천 | `GET /api/nutrients` |
| **환경 모니터링** | 온도/습도/토양수분 실시간 그래프 | `GET /api/environment` |
| **로봇 제어** | 순찰 시작/정지, 긴급 정지 버튼 | `POST /api/robot/command` |

**작업 6-3: 실시간 알림 구현**
- WebSocket으로 서버와 연결 → 병해 감지 시 즉시 화면에 팝업 표시
- 또는 5초마다 API 폴링으로 새 알림 확인

**작업 6-4: 반응형 디자인**
- 모바일에서도 보기 좋게 반응형 레이아웃 적용

#### 🔍 확인 방법
```bash
cd ~/SSAFY/S14P21A602/frontend
npm run dev
# 브라우저에서 http://localhost:5173 접속
```
→ **대시보드에서 작물 현황, 병해 알림, 수확 통계가 보이면 6주차 완료!** 🎉

---

### 📅 7주차: 🧪 통합 테스트 & 발표 준비

> **이번 주 목표**: 모든 시스템을 연결하여 전체 시나리오를 테스트하고 발표를 준비합니다.

#### ✅ 구체적 작업 순서

**작업 7-1: 전체 시나리오 테스트**

아래 시나리오가 처음부터 끝까지 동작하는지 확인합니다:

```
1. 시뮬레이션 실행 (Gazebo에 비닐하우스 + 로봇 등장)
2. 로봇이 자동으로 순찰 시작 (Waypoint 따라 이동)
3. 카메라로 주변을 관찰하며 이동
4. 익은 토마토 발견 → 자동으로 다가가서 수확
5. 병든 잎사귀 발견 → 병명 판별 → MQTT로 알림 전송
6. 백엔드가 MQTT 메시지를 수신하여 DB에 저장
7. 대시보드에 실시간으로 알림 표시
8. 사용자가 대시보드에서 수확 통계, 물주기 이력 확인
9. 사용자가 대시보드에서 "순찰 중지" 명령 → 로봇 정지
```

**작업 7-2: 버그 수정 & 안정화**
- 발견된 버그 수정
- 에러 핸들링 추가 (센서 데이터 누락, 네트워크 끊김 등)
- 성능 최적화 (AI 추론 속도, 네비게이션 반응성)

**작업 7-3: 발표 자료 준비**
- 시연 영상 녹화 (전체 시나리오 동작)
- 시스템 아키텍처 다이어그램 정리
- 팀원별 역할 및 기여도 정리

**작업 7-4: 문서 정리**
- README.md 최종 업데이트
- 설치 및 실행 가이드 작성
- 트러블슈팅 FAQ 정리

#### 🔍 확인 방법
→ **위의 9단계 시나리오가 끊김 없이 동작하면 프로젝트 완료!** 🎉🎉🎉

---

## 💡 백엔드가 필요한 이유

> **Q: 로봇이 이런 기능을 하려면 백엔드가 필요한가?**
> **A: ✅ 네, 반드시 필요합니다.**

| 기능 | 왜 백엔드가 필요한가? |
|------|----------------------|
| 병든 잎 알림 | 로봇(ROS 2)이 발견한 병해 정보를 **사용자 앱/웹에 전달**하려면 중간 서버 필요 |
| 물주기 이력 | 언제 물을 줬는지 **기록을 저장**할 DB 필요 |
| 영양제 권장량 | 병해 + 작물 상태를 분석하여 **추천 로직** 실행할 서버 필요 |
| 수확 통계 | 수확 기록을 **누적 저장**하고 통계를 보여줄 서버 필요 |
| 사용자 제어 | 사용자가 웹/앱에서 로봇에 **명령을 보내려면** 중계 서버 필요 |

### ROS 2 ↔ 백엔드 ↔ UI 전체 흐름

```
ROS 2 (로봇 내부)                   백엔드 (서버)               UI (사용자)
┌─────────────┐    MQTT/HTTP    ┌──────────────┐   REST/WS   ┌──────────┐
│ 센서 데이터   │ ──────────────→ │ API 서버     │ ──────────→ │ 대시보드  │
│ AI 추론 결과  │ ──────────────→ │ + DB 저장    │ ──────────→ │ 모바일앱  │
│ 로봇 상태    │ ──────────────→ │ + 알림 전송   │            │          │
│ 수확/물주기   │ ──────────────→ │              │            │          │
│              │ ←────────────── │ 사용자 명령   │ ←────────── │ 명령 입력 │
└─────────────┘                 └──────────────┘            └──────────┘
```

---

## 📂 최종 프로젝트 폴더 구조

```
S14P21A602/
├── agribot_ws/                  ← ROS 2 워크스페이스 (1~4주차)
│   └── src/
│       ├── agribot_description/ # 로봇 모델 + 센서 + 월드
│       ├── agribot_navigation/  # Nav2, SLAM, 순찰
│       ├── agribot_perception/  # YOLOv8 인식 노드
│       ├── agribot_control/     # 미션 매니저, 수확 동작
│       ├── agribot_iot/         # MQTT 브릿지, 환경 센서
│       ├── agribot_interfaces/  # 커스텀 메시지/서비스
│       └── agribot_bringup/     # 전체 런치 파일
├── backend/                     ← 백엔드 서버 (5주차)
│   ├── app/
│   │   ├── main.py              # FastAPI 앱
│   │   ├── models/              # DB 테이블 정의
│   │   ├── routers/             # API 엔드포인트
│   │   ├── services/            # 비즈니스 로직
│   │   └── mqtt/                # MQTT → DB 저장
│   ├── requirements.txt
│   └── docker-compose.yml
├── frontend/                    ← 웹 대시보드 (6주차)
│   ├── src/
│   │   ├── components/          # UI 컴포넌트
│   │   ├── pages/               # 화면별 페이지
│   │   └── services/            # API 호출 함수
│   └── package.json
└── docs/                        ← 문서 (7주차)
```

---

## ⚡ 초보자를 위한 핵심 요약

> **한 줄 요약: 센서 달기 → 지도 만들기 → AI 학습 → 통합 → 백엔드 → UI → 테스트**

| 순서 | 하는 일 | 비유 |
|------|---------|------|
| 1주차 | 로봇에 눈(카메라)과 귀(라이다) 달기 | 사람에게 감각기관을 달아주는 것 |
| 2주차 | 집 안 지도 만들고 길 찾기 | 새 집에 이사와서 집 구조 파악하는 것 |
| 3주차 | "이건 토마토, 이건 병든 잎" 구분하기 | 눈으로 사물을 인식하는 법 배우기 |
| 4주차 | "토마토 보이면 가서 따기" 행동 연결 | 눈으로 본 것을 행동으로 옮기기 |
| 5주차 | 기록장 만들기 (데이터 저장) | 농사 일지를 쓰는 것 |
| 6주차 | 농사 일지를 예쁘게 보여주는 앱 | 스마트폰 앱으로 확인하는 것 |
| 7주차 | 전체 리허설 | 발표 전 최종 점검 |
