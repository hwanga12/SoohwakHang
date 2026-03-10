# 🌱 AgriBot — 농장 자율주행 채소 관리 로봇

비닐하우스/농장에서 토마토·딸기 등의 채소를 관리하는 자율주행 로봇 시뮬레이션

> **Ubuntu 24.04** + **ROS 2 Jazzy** + **Gazebo Harmonic**

---

## 🛠 기술 스택

| 항목 | 버전 |
|---|---|
| Ubuntu | 24.04 (WSL2 또는 네이티브) |
| ROS 2 | Jazzy |
| Gazebo | Harmonic |
| Python | 3.12 |

---

## 🚀 빠른 시작 (Quick Start)

### 1. 사전 요구사항

```bash
# ROS 2 Jazzy
sudo apt install ros-jazzy-desktop

# Gazebo Harmonic (ROS 통합)
sudo apt install ros-jazzy-ros-gz

# Navigation2 (자율주행)
sudo apt install ros-jazzy-navigation2 ros-jazzy-nav2-bringup

# SLAM Toolbox
sudo apt install ros-jazzy-slam-toolbox
```

### 2. 저장소 클론

```bash
cd ~
git clone https://lab.ssafy.com/s14-mobility-smarthome-sub1/S14P21A602.git
cd S14P21A602
```

### 3. Git Hook 설치 (Jira 이슈 키 자동 삽입)

```bash
sh tools/git-hooks/install.sh
```

### 4. 워크스페이스 빌드

```bash
cd agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

### 5. 환경 변수 설정 (`~/.bashrc`에 추가)

```bash
# ROS 2
source /opt/ros/jazzy/setup.bash
source ~/S14P21A602/agribot_ws/install/setup.bash

# Gazebo 모델 경로
export GZ_SIM_RESOURCE_PATH=~/S14P21A602/agribot_ws/src/agribot_description/models

# (WSL2 GPU 가속이 필요한 경우)
# export GALLIUM_DRIVER=d3d12
# export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
```

### 6. 시뮬레이션 실행

```bash
ros2 launch agribot_bringup simulation.launch.py
```

---

## 📂 패키지 구조

```
agribot_ws/src/
├── agribot_description/    # 🤖 로봇 모델, 월드, URDF, 런치
├── agribot_navigation/     # 🗺️ 자율주행 (Nav2, SLAM)
├── agribot_perception/     # 📷 센서 처리 (카메라, 라이다)
├── agribot_control/        # 🎮 모터 제어
├── agribot_iot/            # 🌡️ IoT 기기 통신
├── agribot_interfaces/     # 📨 커스텀 msg/srv/action
└── agribot_bringup/        # 🚀 전체 시스템 런치
```

| 패키지 | 설명 | 담당 |
|---|---|---|
| `agribot_description` | 로봇 SDF 모델, Gazebo 월드, URDF, RViz 설정 | 모델링 담당 |
| `agribot_navigation` | Nav2 기반 자율주행, SLAM, 경로 계획 | 자율주행 담당 |
| `agribot_perception` | 카메라·라이다 데이터 처리, 객체 인식 | 센서 담당 |
| `agribot_control` | Differential drive 제어, cmd_vel 처리 | 제어 담당 |
| `agribot_iot` | 비닐하우스 IoT 기기 통신 (습도, 온도 등) | IoT 담당 |
| `agribot_interfaces` | 커스텀 ROS 메시지 및 서비스 정의 | 통합 담당 |
| `agribot_bringup` | 전체 시스템 한 번에 실행하는 런치 파일 | 통합 담당 |

---

## 🌿 브랜치 전략

```
main ─────────────── 발표/제출용 (보호, MR로만 merge)
├── release/*  ───── 발표 전 안정화
└── develop ──────── 통합 개발 (MR로만 merge)
    ├── feature/navigation
    ├── feature/perception
    ├── feature/control
    ├── feature/world-design
    ├── feature/iot
    └── feature/bringup-launch
```

### 작업 흐름

```bash
# ① 아침: develop 최신 코드 가져오기
git checkout develop && git pull origin develop
git checkout feature/내-기능 && git merge develop

# ② 작업: 코드 작성 & 커밋
git add .
git commit -m "feat: 라이다 센서 노드 추가"

# ③ 퇴근 전: GitLab에 push
git push origin feature/내-기능

# ④ 기능 완성: GitLab에서 Merge Request 생성
#    feature/내-기능 → develop (코드 리뷰 후 merge)
```

### 커밋 메시지 컨벤션

| 접두사 | 용도 | 예시 |
|---|---|---|
| `feat:` | 새 기능 | `feat: 자율주행 경로 계획 노드 추가` |
| `fix:` | 버그 수정 | `fix: 라이다 데이터 파싱 오류 수정` |
| `docs:` | 문서 | `docs: README 빠른 시작 가이드 추가` |
| `refactor:` | 리팩토링 | `refactor: 센서 노드 콜백 구조 개선` |
| `chore:` | 설정/빌드 | `chore: .gitignore 업데이트` |

---

## 👥 팀원

| 이름 | 역할 |
|---|---|
| | |

---

## 📄 라이선스

Apache-2.0