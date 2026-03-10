# *🌱* AgriBot (좋은  — 스마트 농장 자율주행 채소 관리 로봇

> Gazebo Harmonic과 ROS 2 Jazzy를 활용하여 비닐하우스/농장 환경을 자율주행하며 토마토·딸기 등의 채소를 관리하고, IoT 기기와 통신하는 로봇 시뮬레이션
> 

---

## 🛠 기술 스택

| 항목 | 버전 |
| --- | --- |
| **OS** | Ubuntu 24.04 (WSL2 또는 네이티브) |
| **Framework** | ROS 2 Jazzy |
| **Simulator** | Gazebo Harmonic |
| **Language** | Python 3.12 / C++ 17 |
| **자율주행 프레임워크** | Nav 2 |
| **이미지 인식** | YOLOv8 |

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
예시: 브랜치 `feature/S14P-42-login` → 커밋 `"로그인 기능 추가"` → 결과: `"S14P-42 로그인 기능 추가"`
> 

### 4. ROS 2 의존성 자동 설치

```bash
cd ~/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
sudo apt update
rosdep update
rosdep install --from-paths src --ignore-src -r -y
```

### 5. 워크스페이스 빌드

- `-symlink-install` 옵션을 사용하면 Python 코드 수정 시 매번 빌드하지 않아도 반영됩니다.

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
| --- | --- | --- | --- |
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
> 

| 타입 | 파일명 | 설명 |
| --- | --- | --- |
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
| --- | --- |
| `build/` | `colcon build` 하면 자동 생성. 팀원마다 환경이 달라 충돌 발생 |
| `install/` | 빌드 산출물. 자동 생성 |
| `log/` | 빌드 로그. 용량만 차지 |
| `__pycache__/` | Python 캐시. 자동 생성 |
| `*.bag`, `*.db3` | ROS bag 파일. 대용량 |

### 대용량 3D 모델 (.glb) 관리

| 방법 | 추천도 | 설명 |
| --- | --- | --- |
| **직접 커밋** | ⭐⭐⭐ | 총 100MB 이하면 GitLab이 충분히 감당 가능. **SSAFY 규모에서 가장 현실적** |
| Git LFS | ⭐⭐ | 정석이지만 SSAFY GitLab 서버에서 LFS 활성화 + 팀원 전원 설정 필요. 설정 비용이 과함 |
| 외부 공유 (구글 드라이브) | ⭐ | “링크 어디였지?” 혼란 발생 확률 높음 |

> **💡 결론:** `.glb` 파일 총합이 100MB 이하이면 직접 커밋, 500MB 이상이면 Git LFS를 고려하세요.
만약 무거운 배경(World) 모델이 있다면, 메인 로봇 모델은 직접 커밋 + 무거운 배경은 외부 저장소 + 다운로드 스크립트(`download_models.sh`)를 만드는 하이브리드 방식도 좋습니다.
> 

# GIT LFS 하는 법 !

## 1. Git LFS 설치 및 초기화

먼저 내 컴퓨터에 LFS가 설치되어 있어야 합니다. (팀원들도 한 번씩은 해야 합니다.)

Bash

`# LFS 설치 (Ubuntu 기준)
sudo apt install git-lfs

# Git LFS 활성화 (계정당 한 번만 수행)
git lfs install`

## 2. 관리할 에셋 확장자 지정

어떤 파일들을 LFS로 관리할지 프로젝트 폴더에서 정해줘야 합니다. 보통 Gazebo에서 쓰는 대용량 파일들을 등록합니다.

Bash

`# .stl, .dae, .png 같은 파일들을 LFS 관리 대상으로 등록
git lfs track "*.stl"
git lfs track "*.dae"
git lfs track "*.png"
git lfs track "*.jpg"

# 설정 저장 (매우 중요: .gitattributes 파일이 생성됩니다)
git add .gitattributes`

## 3. 평소처럼 사용하기

설정이 끝났다면 평소 Git 사용법과 똑같습니다.

Bash

`git add src/my_robot_description/meshes/huge_model.dae
git commit -m "Add robot mesh assets with LFS"
git push origin main`

## 4. 팀원이 코드를 받을 때

팀원이 `git clone`을 하면 LFS 파일들도 자동으로 다운로드됩니다. 만약 파일이 깨져 보이거나 포인터(텍스트)만 보인다면 아래 명령어를 입력하면 됩니다.

Bash

`git lfs pull`

---

### ⚠️ 주의사항

- **`.gitattributes`를 꼭 커밋하세요:** 이 파일이 깃에 올라가야 다른 팀원들의 컴퓨터도 "아, 이 파일은 LFS로 관리하는구나"라고 인식합니다.
- **중간에 도입할 경우:** 이미 일반 Git으로 커밋된 큰 파일들은 소급 적용되지 않습니다. 새로 추가하는 파일부터 적용되거나, 기존 이력을 재작성(Migration)해야 합니다.

### .gitignore (전체)

```
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