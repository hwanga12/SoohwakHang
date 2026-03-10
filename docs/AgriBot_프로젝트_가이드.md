# 🌱 AgriBot — 스마트 농장 자율주행 채소 관리 로봇

> Gazebo Harmonic과 ROS 2 Jazzy를 활용하여 비닐하우스/농장 환경을 자율주행하며 토마토·딸기 등의 채소를 관리하고, IoT 기기와 통신하는 로봇 시뮬레이션

---

## 🛠 기술 스택

| 항목 | 버전 |
|---|---|
| **OS** | Ubuntu 24.04 (WSL2 또는 네이티브) |
| **Framework** | ROS 2 Jazzy |
| **Simulator** | Gazebo Harmonic |
| **Language** | Python 3.12 / C++ 17 |

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

> **참고:** 이 훅은 브랜치명에서 Jira 이슈 키(예: `S14P-42`)를 추출하여 커밋 메시지 앞에 자동으로 붙여줍니다.
> 예시: 브랜치 `feature/S14P-42-login` → 커밋 `"로그인 기능 추가"` → 결과: `"S14P-42 로그인 기능 추가"`

### 4. ROS 2 의존성 자동 설치

```bash
cd ~/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
sudo apt update
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```

### 5. 워크스페이스 빌드

`--symlink-install` 옵션을 사용하면 Python 코드 수정 시 매번 빌드하지 않아도 반영됩니다.

```bash
colcon build --symlink-install
source install/setup.bash
```

### 6. 환경 변수 설정

`~/.bashrc` 하단에 아래 내용을 추가하고, `source ~/.bashrc`를 한 번만 실행하세요.

```bash
# ROS 2
source /opt/ros/jazzy/setup.bash
source ~/S14P21A602/agribot_ws/install/setup.bash

# Gazebo 모델 경로
export GZ_SIM_RESOURCE_PATH=~/S14P21A602/agribot_ws/src/agribot_description/models

# WSL2 GPU 가속 (NVIDIA GPU가 있는 경우)
export GALLIUM_DRIVER=d3d12
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
```

### 7. 시뮬레이션 실행 테스트

```bash
ros2 launch agribot_bringup simulation.launch.py
```

---

## 📂 프로젝트 구조

### 전체 폴더 구조

```
S14P21A602/                        ← Git 루트 (GitLab 레포)
├── README.md                      ← 빠른 시작 가이드
├── .gitignore
├── tools/                         ← Git hooks 등 유틸
│   └── git-hooks/
├── docs/                          ← 프로젝트 문서 (설계서, 발표자료)
│
└── agribot_ws/                    ← ROS 2 Colcon 워크스페이스
    └── src/                       ← ⭐ 모든 코드가 여기에!
        ├── agribot_description/   # 🤖 로봇 모델, 월드, URDF, 런치
        ├── agribot_navigation/    # 🗺️ 자율주행 (Nav2, SLAM)
        ├── agribot_perception/    # 📷 센서 처리 (카메라, 라이다)
        ├── agribot_control/       # 🎮 모터 제어
        ├── agribot_iot/           # 🌡️ IoT 기기 통신
        ├── agribot_interfaces/    # 📨 커스텀 msg/srv/action
        └── agribot_bringup/       # 🚀 전체 시스템 런치
```

### 패키지별 상세 설명

| 패키지 | 빌드 타입 | 설명 | 담당 역할 |
|---|---|---|---|
| `agribot_description` | ament_python | 로봇 SDF 모델, Gazebo 월드(비닐하우스), URDF/Xacro, RViz 설정, 런치 파일 | 모델링 담당 |
| `agribot_navigation` | ament_python | Nav2 기반 자율주행, SLAM, AMCL, 경로 계획, 장애물 회피 | 자율주행 담당 |
| `agribot_perception` | ament_python | 카메라(RGB-D)·라이다(LiDAR) 데이터 전처리, 객체 인식 (OpenCV) | 센서 담당 |
| `agribot_control` | ament_python | Differential drive 모터 제어, cmd_vel 처리, PID 제어 | 제어 담당 |
| `agribot_iot` | ament_python | 비닐하우스 IoT 기기 통신 (온습도 센서, 환풍기, 조명 등), MQTT/HTTP 브릿지 | IoT 담당 |
| `agribot_interfaces` | **ament_cmake** | 커스텀 ROS 메시지(msg), 서비스(srv), 액션(action) 정의 | 통합 담당 |
| `agribot_bringup` | ament_python | 전체 시스템을 한 번에 실행하는 상위 런치 파일 | 통합 담당 |

### agribot_description 상세 구조

```
agribot_description/
├── package.xml
├── setup.py
├── models/
│   ├── agribot/              # 로봇 본체 모델
│   │   ├── model.sdf         ✅ Git 관리
│   │   ├── model.config      ✅ Git 관리
│   │   └── meshes/
│   │       └── agribot.glb   ✅ Git 관리 (100MB 이하)
│   └── greenhouse/           # 비닐하우스 환경 모델
├── worlds/
│   └── farm_world.sdf        # Gazebo 시뮬레이션 월드
├── urdf/                     # URDF/Xacro (RViz용)
├── launch/
│   └── spawn_agribot.launch.py
├── rviz/                     # RViz 시각화 설정
└── config/                   # 파라미터 YAML
```

### agribot_interfaces 커스텀 메시지/서비스

> ⚠️ 이 패키지만 **ament_cmake** 빌드 타입입니다 (msg/srv 컴파일이 필요하기 때문)

| 타입 | 파일명 | 설명 |
|---|---|---|
| msg | `CropStatus.msg` | 작물 이름, 건강도, 성장 단계, 물 필요 여부, 수확 가능 여부, 위치 |
| msg | `IoTCommand.msg` | IoT 기기 ID, 명령 유형, 목표 값, 단위 |
| msg | `EnvironmentData.msg` | 온도, 습도, 토양 수분, 조도, CO2 농도, 구역 ID |
| srv | `SetHumidity.srv` | 구역별 목표 습도 설정 요청 → 성공 여부/현재 습도 응답 |

---

## 🗃️ Git 관리 전략

### ✅ Git에 올려야 하는 것 (Commit 대상)

`src/` 폴더 안의 내용만 추적합니다:
- 소스 코드 (`.py`, `.cpp`)
- 패키지 설정 (`package.xml`, `setup.py`, `CMakeLists.txt`)
- 런치 파일 (`launch/`)
- 설정 파일 (`config/*.yaml`)
- 로봇/환경 모델 (`models/`, `urdf/`, `worlds/`)
- 문서 (`docs/`)
- `.gitignore`, `README.md`

### ❌ 절대 올리면 안 되는 것 (Commit 금지)

| 폴더/파일 | 이유 |
|---|---|
| `build/` | `colcon build` 하면 자동 생성. 팀원마다 환경이 달라 충돌 발생 |
| `install/` | 빌드 산출물. 자동 생성 |
| `log/` | 빌드 로그. 용량만 차지 |
| `__pycache__/` | Python 캐시. 자동 생성 |
| `*.bag`, `*.db3` | ROS bag 파일. 대용량 |

### 대용량 3D 모델 (.glb) 관리

| 방법 | 추천도 | 설명 |
|---|---|---|
| **직접 커밋** | ⭐⭐⭐ | 총 100MB 이하면 GitLab이 충분히 감당 가능. **SSAFY 규모에서 가장 현실적** |
| Git LFS | ⭐⭐ | 정석이지만 SSAFY GitLab 서버에서 LFS 활성화 + 팀원 전원 설정 필요. 설정 비용이 과함 |
| 외부 공유 (구글 드라이브) | ⭐ | "링크 어디였지?" 혼란 발생 확률 높음 |

> **💡 결론:** `.glb` 파일 총합이 100MB 이하이면 직접 커밋, 500MB 이상이면 Git LFS를 고려하세요.
> 만약 무거운 배경(World) 모델이 있다면, 메인 로봇 모델은 직접 커밋 + 무거운 배경은 외부 저장소 + 다운로드 스크립트(`download_models.sh`)를 만드는 하이브리드 방식도 좋습니다.

### .gitignore (전체)

```gitignore
# ─── ROS 2 빌드 산출물 (가장 중요) ───
build/
install/
log/

# ─── Colcon 메타데이터 ───
.colcon_*

# ─── Python ───
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.eggs/
*.so
.Python
env/
venv/
.venv/

# ─── C++ / C ───
*.o
*.obj
*.out
*.app
*.gch
*.pch
*.lib
*.a
*.la
*.lo
*.dll
*.dylib
*.exe

# ─── IDE / 에디터 ───
.vscode/
.idea/
*.swp
*.swo
*~
*.bak

# ─── OS ───
.DS_Store
Thumbs.db
desktop.ini

# ─── Gazebo 런타임 캐시 ───
.gz/
*.fuel/
~/.ignition/
~/.gazebo/

# ─── ROS bag 파일 (대용량) ───
*.bag
*.db3
rosbag2_*/

# ─── 기타 ───
*.log
core
core.*
```

---

## 🌿 Git 브랜치 전략 (6명 협업)

### 간소화된 GitFlow (Feature Branch 전략)

SSAFY처럼 정해진 기간 내에 빠르게 결과를 내야 하는 프로젝트에서는 복잡한 정통 GitFlow보다 **단순화된 GitFlow**가 적합합니다.

```
main ─────────────────────────────── 발표/제출용 (보호됨, 절대 직접 push ❌)
│
├── release/v1.0 ─────────────────── 발표 전 안정화 (develop에서 분기)
│
└── develop ──────────────────────── 통합 개발 (MR로만 merge)
    │
    ├── feature/navigation         ← 팀원 A: 자율주행 (Nav2, SLAM)
    ├── feature/perception         ← 팀원 B: 센서 처리 (카메라, 라이다)
    ├── feature/control            ← 팀원 C: 모터 제어
    ├── feature/world-design       ← 팀원 D: 월드/맵/로봇 모델링
    ├── feature/iot                ← 팀원 E: IoT 기기 통신
    └── feature/bringup-launch     ← 팀원 F: 런치/설정/통합
```

### 브랜치 역할 설명

| 브랜치 | 역할 | 규칙 |
|---|---|---|
| `main` | 발표/제출용. 시뮬레이션이 에러 없이 실행되는 "완벽한 상태" | 절대 직접 push ❌. MR로만 merge |
| `develop` | 개발의 중심지. 모든 팀원의 기능이 1차적으로 모이는 통합 테스트 브랜치 | MR + 팀원 1명 이상 코드 리뷰 후 merge |
| `feature/*` | 각 팀원이 맡은 기능을 개발하는 개인 작업 공간 | develop에서 분기, 완료 후 develop으로 MR |
| `release/*` | 발표 1~2주 전 develop에서 분기하여 안정화. 버그만 수정, 새 기능은 develop에서 계속 | 안정화 완료 후 main에 merge |
| `hotfix/*` | main에서 긴급 버그 발견 시. main에서 분기 → 수정 → main, develop 양쪽에 MR | 긴급 상황에만 사용 |

### 📌 매일 반복하는 작업 흐름

```bash
# ① 아침: develop에서 최신 코드 가져오기
git checkout develop
git pull origin develop
git checkout feature/내-기능
git merge develop

# ② 작업: 내 feature 브랜치에서 코드 작성 & 커밋
git add .
git commit -m "feat: 라이다 센서 노드 추가"

# ③ 퇴근 전: 내 브랜치를 GitLab에 올리기
git push origin feature/내-기능

# ④ 기능 완성 시: GitLab에서 Merge Request 생성
#    feature/내-기능 → develop
#    팀원 1명 이상 코드 리뷰 후 Merge
```

### ⚠️ 충돌 최소화 팁

> **매일 아침 반드시!** `git checkout develop` → `git pull` → `git checkout feature/내기능` → `git merge develop` 으로 코드를 최신화하고 개발을 시작하세요!

- 작업 폴더(패키지)를 기능별로 확실히 분리하세요
- 공통 파일(메인 URDF, 공통 설정 YAML 등)을 수정해야 할 때는 **작업 전 팀 메신저에 미리 공유**
- 한 MR에 너무 많은 변경을 넣지 마세요 — 작은 MR이 리뷰하기 쉽고 충돌도 적습니다

### 📌 커밋 메시지 컨벤션

| 접두사 | 용도 | 예시 |
|---|---|---|
| `feat:` | 새 기능 추가 | `feat: 자율주행 경로 계획 노드 추가` |
| `fix:` | 버그 수정 | `fix: 라이다 데이터 파싱 오류 수정` |
| `docs:` | 문서 수정 | `docs: README 빠른 시작 가이드 추가` |
| `refactor:` | 코드 리팩토링 | `refactor: 센서 노드 콜백 구조 개선` |
| `chore:` | 설정/빌드 관련 | `chore: .gitignore 업데이트` |

> 💡 Git Hook이 설치되어 있으면 브랜치명에서 Jira 이슈 키가 자동으로 커밋 메시지에 삽입됩니다.

---

## 👥 팀원 역할 분배

| 역할 | 담당 패키지 | 핵심 기술 | feature 브랜치 |
|---|---|---|---|
| **팀원 A** — 자율주행 | `agribot_navigation` | Nav2, SLAM, AMCL, 경로 계획 | `feature/navigation` |
| **팀원 B** — 인지/센서 | `agribot_perception` | 카메라, 라이다, OpenCV, 객체 인식 | `feature/perception` |
| **팀원 C** — 제어 | `agribot_control` | diff_drive, cmd_vel, PID 제어 | `feature/control` |
| **팀원 D** — 모델링/월드 | `agribot_description` | SDF, URDF/Xacro, Gazebo 플러그인 | `feature/world-design` |
| **팀원 E** — IoT | `agribot_iot` | MQTT, ROS 브릿지, 환경 센서 시뮬 | `feature/iot` |
| **팀원 F** — 통합/인프라 | `agribot_bringup`, `agribot_interfaces` | 런치파일, 커스텀 메시지, CI/CD | `feature/bringup-launch` |

---

## 📅 개발 시작 순서 (1주차 로드맵)

### Day 1: Git 세팅 & 프로젝트 구조 확인

```bash
# WSL2 우분투에서 실행
cd ~
git clone https://lab.ssafy.com/s14-mobility-smarthome-sub1/S14P21A602.git
cd S14P21A602

# Git Hook 설치
sh tools/git-hooks/install.sh

# 첫 빌드 테스트
cd agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
```

### Day 2: 로봇 모델(SDF) + 비닐하우스 월드 제작

- 팀원 D가 `agribot_description/models/` 아래에 로봇 SDF 모델 제작
- 비닐하우스 월드(`farm_world.sdf`) 환경 구성 시작
- 기본 런치 파일로 Gazebo에서 월드가 뜨는지 확인

### Day 3: 센서 + 구동 플러그인 부착

- 팀원 B: 로봇 모델에 카메라/라이다 센서 플러그인 추가
- 팀원 C: Differential drive 플러그인 추가, `cmd_vel`로 로봇 움직이는지 확인
- `ros2 topic list`로 센서 토픽이 발행되는지 검증

### Day 4~5: 각 파트 병렬 개발 시작

모든 팀원이 각자의 `feature/*` 브랜치에서 본격 개발 시작

---

## 🔧 자주 쓰는 명령어 모음

### 빌드 & 실행

```bash
# 전체 빌드
cd ~/S14P21A602/agribot_ws
colcon build --symlink-install

# 특정 패키지만 빌드
colcon build --packages-select agribot_navigation

# 환경 변수 적용
source install/setup.bash

# 시뮬레이션 실행
ros2 launch agribot_bringup simulation.launch.py
```

### ROS 2 디버깅

```bash
# 현재 실행 중인 토픽 목록
ros2 topic list

# 특정 토픽 데이터 실시간 확인
ros2 topic echo /scan           # 라이다 데이터
ros2 topic echo /camera/image   # 카메라 이미지

# 현재 실행 중인 노드 목록
ros2 node list

# 노드 간 연결 그래프 시각화
rqt_graph
```

### Git 작업

```bash
# 아침 루틴
git checkout develop && git pull origin develop
git checkout feature/내-기능 && git merge develop

# 커밋 & 푸시
git add .
git commit -m "feat: 기능 설명"
git push origin feature/내-기능

# develop 브랜치 생성 (최초 1회)
git checkout -b develop
git push -u origin develop

# feature 브랜치 생성
git checkout develop
git checkout -b feature/내-기능명
```

---

## 📄 라이선스

Apache-2.0
