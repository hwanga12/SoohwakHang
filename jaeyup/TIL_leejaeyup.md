# 26. 03. 04.
오늘은 고양이 원예 관리 로봇'의 가상 환경(Gazebo)을 세팅했다. 
생각보다 딸깍 될 줄 알았는데, 현실은 온갖 에러가 튀어나왔다.


# 26. 03. 05.
우분투, ROS, 가제보 버전을 통일하는 게 좋다고 하는데, 어떤 쪽으로 통일할지가 고민이 된다.
정보가 더 적지만 최신인 버전으로 통일할까, 안정성은 있는 구형인 버전으로 설치할까...

```
1. 추천 1순위 (최신 표준 스택)

조합: Ubuntu 24.04 + ROS 2 Jazzy + Gazebo Harmonic

특징: 2029년까지 공식 지원을 받는 가장 최신 버전이자 앞으로의 로보틱스 표준입니다. 지금 새롭게 프로젝트를 기획하거나 학습을 시작하신다면 무조건 이 세트로 세팅하는 것을 권장합니다.

2. 추천 2순위 (가장 풍부한 레퍼런스)

조합: Ubuntu 22.04 + ROS 2 Humble + Gazebo Fortress

특징: 현재 시점에서 가장 많은 유저층과 방대한 튜토리얼, 안정적인 패키지들을 뽐내는 세트입니다. 만약 사용하려는 특정 센서나 오픈소스 코드가 아직 최신 버전(Jazzy)을 지원하지 않는다면 이 조합이 가장 안전한 선택입니다.
```

```
🏆 딱 하나만 추천한다면: **Ubuntu 22.04 + ROS 2 Humble + Gazebo Fortress**
이유는 간단합니다:

| 기준 | 설명 |
| --- | --- |
| **안정성** | ROS 2 Humble은 **2027년까지 지원되는 LTS(장기지원)** 버전. 버그 수정과 보안 패치가 계속 나옴 |
| **자료 풍부** | 전 세계 ROS 2 사용자의 **과반수 이상**이 이 조합을 사용 중. 구글링하면 답이 가장 많이 나옴 |
| **교육 자료** | SSAFY 포함 대부분의 로보틱스 교육기관이 이 조합을 기준으로 교재를 만듦 |
| **Fortress** | Gazebo Classic과 달리 **현재 지원 중**이면서, 충분히 성숙한 안정 버전 |

최신 조합(Ubuntu 24.04 + Jazzy + Harmonic)은 너무 새로워서 아직 레퍼런스가 부족하고, 예기치 않은 버그를 만날 확률이 높습니다. 특히 학습 중인 단계에서는 **에러가 났을 때 검색해서 해결할 수 있는 자료가 많은 조합**이 가장 중요합니다.
```

LLM도 그때 그때 다르게 대답하니까, 하나만 선택하기 더더욱 헷갈린다.


# 26. 03. 06.
어제 고민했던 ROS 2/Gazebo 버전에 대해 결단을 내렸다. 가장 최신 스택인 `Ubuntu 24.04 + ROS 2 Jazzy + Gazebo Harmonic` 조합으로 완전히 새로 설치하기로 했다.
> 실물 카메라나 라이다 센서 등을 이용하는 것이 아니기 때문에, 호환성을 위해 굳이 구버전을 이용할 필요가 없었기 때문이다.

## 1. Ubuntu 22.04 완전 삭제 및 새 환경 세팅
* 기존에 꼬여있던 WSL 배포판을 `wsl --unregister Ubuntu-22.04` 한 줄로 깔끔하게 밀어버리고, Ubuntu 24.04를 새로 설치했다.
* 공식 문서를 참고해 터미널 명령어만으로 ROS 2 Jazzy와 Gazebo Harmonic 세팅을 무사히 마쳤다.

## 2. Gazebo Harmonic과 NVIDIA GPU 외장 그래픽 연동 성공
* 외장 그래픽 카드(RTX 4070)를 시뮬레이터에서 사용하려 했으나, NVIDIA WSL 드라이버(591.44)와 최신 Mesa 버전에 엮인 d3d12 렌더러 호환성 버그로 자꾸 `Segmentation Fault` 크래시가 났다.
* Windows 호스트에서 NVIDIA 드라이버를 최신 버전(595.71)으로 업데이트하니까 크래시가 완벽히 해결되었다.
* `~/.bashrc`에 환경변수를 영구 등록하여, 이제 항상 안정적으로 GPU 가속(GPU ~23% 점유)을 받는다.
  ```bash
  export GALLIUM_DRIVER=d3d12
  export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA
  ```

## 3. 웹에서 3D 모델 다운받아 띄우기 (.glb)
* "아무 3D 모델이나 띄워서 로봇을 만들 수 있다"는 사실을 알았다. 시뮬레이터에서는 구형 `.obj` 등보다 모델의 텍스처, 재질, 형상 정보가 단일 파일로 꽉꽉 압축된 `.glb` 포맷이 에러도 안 나고 우수하다는 것을 배웠다.
* Sketchfab에서 다운받은 4개의 모델(stray_cat, 숲 디오라마, 온실 구조물 등)을 `~/.gazebo/models` 경로 하위에 넣고 각각 `model.config`와 `model.sdf` 파일들을 만들어 줬다.
* Gazebo Harmonic은 UI가 많이 달라졌다. Component Inspector에서 정적(static)인 맵을 마음대로 회전 및 배치하고 싶다면 GUI가 아니라 SDF 코드 안에 아예 `<pose>0 0 0 0 0 1.5708</pose>` (90도 회전 시 라디안 값)를 추가하는 게 가장 원색적이고 깔끔한 해결책이다.
* 또한 모델 자체가 시뮬레이션 내에서 회전/이동되길 원한다면 `<static>false</static>` 설정이 필수적이다!

## Next Step
단순히 바퀴 달린 모델링을 가져왔다고 로봇이 스스로 굴러가는 게 아니란 걸 알았다. 가제보에서 주행을 구현하려면 가상 원기둥(Cylinder)이나 박스형 차대에 바퀴 관절(Joint)을 엮은 다음 껍데기를 씌우는 식이어야 한다. 이젠 이 '고양이 껍데기를 얹은 구동체'의 주행 코드를 짤 차례다.

# 26. 03. 09.
주제가 좀 더 들었을 때 '그럴듯 하게 들리는' 주제이면 좋겠는데
컨셉을 잡기 어렵다.


# 26. 03. 10.
## TIL (Today I Learned) - Gazebo 및 WSL 트러블슈팅

이번 세션에서 해결한 문제들과 새롭게 알게 된 사실들을 정리한 문서입니다.

### 1. WSL 시스템 접근 및 환경 변수 경고
- **현상:** PowerShell 시스템(네트워크 경로 `\\wsl$...`)에서 `wsl`을 실행했을 때 경로 해석 에러(`Failed to translate`)와 ROS `setup.bash` 중복 소싱 경고(`ROS_DISTRO was set to...`) 발생.
- **배운 점:**
  - 윈도우 네트워크 경로 자체를 wsl 내부 Linux 환경의 경로로 직역하지 못해 발생한 단순 경고임. 홈 디렉토리(`~`)로 정상 접속되므로 작업 자체에는 지장이 없음.
  - `.bashrc` 등에 ROS 환경 변수 적용 스크립트가 여러 번 실행되었거나 꼬여 있어도 심각한 에러는 아니며, 필요시 확인 후 수정하면 됨.

### 2. Gazebo (Classic) vs Ignition Gazebo (Gazebo Sim) 명령어
- **현상:** `gz sim` 명령어와 `gazebo` 명령어 간 혼동. `gazebo shapes.sdf` 실행 시 `command not found` 오류 발생.
- **배운 점:**
  - 옛날 버전인 **Gazebo Classic** (ROS 1 버전에 자주 포함되던 버전)은 `gazebo [파일명]`으로 켬.
  - 현재 시스템에 설치된 새로운 버전 **Ignition Gazebo (Gazebo Sim)** 는 `gz sim [파일명]`으로 켬.
  - ROS 노드들과 종합적으로 띄울 때는 `roscore` 구동 후 `roslaunch` 명령어를 주로 사용함.

### 3. Gazebo 모델 불러오기 (캐시/경로 우선순위 이슈)
- **현상:** 팀원의 Git 최신 브랜치를 가져와 `gz sim smartfarm.sdf`를 열었는데, 팀원이 만든 모델 대신 내가 예전에 만들었던 로컬 구 버전 모델이 불러와지는 문제.
- **배운 점:**
  - Gazebo는 3D 모델을 불러올 때 현재 프로젝트 폴더보다 **사용자 홈 캐시(`~/.gz/models` 혹은 `~/.ignition/models`) 내 숨김 폴더에 저장된 모델을 우선적으로 참조**하는 특성이 있음.
  - 해결책: 환경 변수 `GZ_SIM_RESOURCE_PATH`를 설정하여 현재 프로젝트의 `models` 폴더 경로를 Gazebo가 최우선으로 살펴보도록 명시해야 함.

### 4. 터미널 내 상대 경로와 현재 위치(pwd)의 중요성
- **현상:** `GZ_SIM_RESOURCE_PATH=$(pwd)/models...` 를 입력하고 실행했는데 여전히 `Unable to find or download file` 에러 발생.
- **배운 점:**
  - 사용자가 이미 `worlds` 폴더 안에 들어간 상태에서 `$(pwd)`를 호출했으므로 잘못된 경로(`worlds/models`)가 설정됨.
  - 같은 이유로 `worlds` 폴더 내에서 `worlds/smartfarm.sdf` 파일을 부르려 하니 `worlds/worlds/smartfarm.sdf`를 찾는 꼴이 되어 파일을 찾을 수 없었음.
  - CLI(터미널) 명령어 입력 시 **현재 어느 폴더에 위치해 있는지**를 정확히 인지하고, 상대 경로를 기준점에 맞게 호출하는 것이 매우 중요함. (예: 최상위 `gazebo_workspace` 폴더로 나온 후 실행)


# 26. 03. 12.
## 3D 모델(wall-e.glb)을 Agribot 로봇 패키지에 통합
어제 다운로드 했던 3D 모델 중 `wall-e.glb`를 ROS 2 패키지에 넣고 Gazebo 시뮬레이터 상의 로봇 외형으로 띄우는 작업을 수행했다.

1. **모델 파일 배치**: `wall-e.glb` 파일을 `agribot_description` 패키지 내부의 `models/agribot/meshes/` 경로로 복사했다.
2. **URDF (Xacro) 정의**: 로봇의 구조를 기재하는 `agribot.urdf.xacro` 파일을 새로 생성했다. 해당 파일 안에서 `base_link`의 외형(visual) 및 충돌 영역(collision) 속성에 메쉬 파일 경로(`package://agribot_description/models/agribot/meshes/wall-e.glb`)를 연결해 주었다.
3. **Launch 파일 수정**: Gazebo 환경을 띄우는 `spawn_agribot.launch.py` 파일에 `robot_state_publisher` 노드를 추가해 방금 만든 xacro 파일 정보를 퍼블리시 하도록 했고, Gazebo Harmonic의 `ros_gz_sim create`을 이용해 이 정보를 바탕으로 엔티티를 스폰하도록 수정했다.
4. **동작 확인**: 작성한 패키지를 `colcon build`로 빌드 완료했으며, 이제 런치 파일을 실행하면 Gazebo 시뮬레이션 환경에 정상적으로 Wall-E 모델 기반의 로봇이 띄워진다.

## Gazebo Harmonic 모델 경로(Resource Path) 트러블슈팅 및 배경 추가
ROS 2 패키지 내부에 저장된 3D 모델(URDF 포함)을 런치 파일로 실행할 때, Gazebo Harmonic 엔진이 `package://` 또는 `model://` 경로를 찾지 못하는 이슈가 발생했다. GUI로 단순 배치하는 것과 달리, 정식 ROS 패키지로서 환경을 관리하기 위해 아래와 같이 조치했다.

1. **절대/상대 경로 혼동의 원인 파악**: Gazebo Harmonic은 `GZ_SIM_RESOURCE_PATH` 환경 변수가 명시적으로 지정되지 않으면, 패키지 내부(`install/.../share/...`)의 커스텀 모델 폴더를 자동으로 스캔하지 못해 에러(`Unable to find file with URI`)를 뿜는다.
2. **Launch 파일에 환경 변수 주입**: `spawn_agribot.launch.py` 내부에 `AppendEnvironmentVariable` 기능을 사용하여 컴파일된 현재 패키지의 설치 폴더(및 `models` 폴더)를 가제보 리소스 경로로 동적 지정했다. 이로써 어떤 컴퓨터, 어느 팀원이 클론받아도 즉시 모델을 불러올 수 있게 재현성을 확보했다.
3. **비닐하우스 배경(Greenhouse) 정식 편입**: GUI에서 드래그 앤 드롭으로 맵을 꾸미는 것은 로컬 컴퓨터(캐시)에 의존하게 되어 협업시 깨질 위험이 크다. 따라서 다운로드한 비닐하우스 모델(`greenhouse.glb`)을 `agribot_description/models/greenhouse/` 내부로 옮기고 전용 `model.config`, `model.sdf`를 작성해주었다. 완성된 모델을 Gazebo 월드 파일(`farm_world.sdf`)의 `<include>` 태그로 선언하여 시뮬레이션을 켤 때 자동으로 맵 전체가 스폰되도록 설계했다.

## Colcon Build 시 리소스 누락 이슈 (setup.py)
코드상으로 경로를 아무리 잘 맞춰도, 정작 `install/` 폴더에 파일이 없으면 가제보가 불러올 수 없다. `colcon build` 과정에서 발생하는 리소스 누락 문제를 해결했다.

1. **상황 발생**: `model://` 경로 설정을 마쳤음에도 여전히 `Error Code 14 (could not be resolved)` 발생. 확인 결과, `install/` 폴더 내 패키지 경로에 `meshes/` 폴더와 `.glb` 파일이 아예 복사되지 않은 상태였다.
2. **원인 분석**: ROS 2 Python 패키지의 `setup.py` 내 `data_files` 항목이 파일 단위로 명시되어야 하는데, `models/greenhouse/` 폴더 하위의 `meshes/` 폴더를 복사하라는 규칙이 누락되어 있었다.
3. **해결 방법**: `setup.py`의 `data_files` 리스트에 `meshes` 하위의 모든 파일(`*.*`)을 포함하도록 한 줄을 추가했다. 이제 빌드 시 3D 모델 데이터가 정식으로 `share/` 경로에 포함되어 가제보가 정상적으로 리소스를 찾아 로드할 수 있게 되었다.

## 자율주행 수확 로봇 구현을 위한 모델링 전략 (토마토/딸기)
미래에 로봇팔을 이용한 정교한 수확 시뮬레이션을 구현하기 위해 필요한 모델링 확보 전략을 정리했다.

1. **모델 확보 전략**:
    - **통짜 모델 (Plant + Fruit)**: 배경용 식물은 줄기와 열매가 합쳐진 완성된 모델(`tomato plant` 등)을 사용한다. 이는 `<static>true</static>`으로 설정하여 환경의 일부로 배치한다.
    - **개별 열매 모델 (Individual Fruit)**: 로봇팔이 실제로 집어 옮길 수 있는 객체는 낱알 1개짜리 모델로 별도 확보한다. 이는 `<static>false</static>`인 물리 객체로 배치한다.
2. **시뮬레이션 구현 팁**:
    - 식물 줄기 모델과 낱알 모델을 SDF 월드 파일 안에서 좌표를 맞춰 겹쳐 배치하면, 마치 줄기에 열매가 달린 것처럼 시각적으로 연출할 수 있다. 
    - 로봇팔의 Gripper가 낱알을 잡는 순간 줄기에서 분리되어 트레이로 이동하는 동적 시뮬레이션이 가능하다. 
3. **추천 리소스 사이트**: Sketchfab, TurboSquid, Free3D 등에서 `.glb` 포맷 위주로 검색한다. (텍스처 내장 이점)


# 26. 03. 13.
## 프로젝트 전체 기획 수립
AgriBot 스마트 농장 자율주행 로봇의 전체 시스템을 기획했다. 코드베이스를 분석한 결과, 로봇 모델에 센서가 전혀 없었고 대부분의 패키지가 빈 골격이었다. 4계층 아키텍처(인프라 → 시뮬레이션 → 지능 제어 → 서비스)를 설계하고, 7주 단위 개발 로드맵을 수립했다.

- 핵심 깨달음: 로봇(ROS 2)이 감지한 정보를 사용자에게 전달하려면 **반드시 백엔드 서버가 필요**하다. ROS 2 ↔ MQTT 브로커 ↔ FastAPI 서버 ↔ React 대시보드라는 데이터 흐름이 필요하다.

## SDF 파일에 센서 추가하는 법
Gazebo Harmonic에서 로봇에 센서를 추가하려면 SDF 파일 안에 `<link>` + `<sensor>` 조합으로 정의한다.

1. **RGB-D 카메라**: `<sensor type="rgbd_camera">`로 정의. `<topic>` 태그로 Gazebo 토픽 이름을 지정한다. `<image>` 안에 해상도(width/height)와 FOV를 설정.
2. **2D LiDAR**: `<sensor type="gpu_lidar">`로 정의. `<horizontal>`에 samples(360), min/max angle(-π~π)으로 360° 스캔. `<range>`에 최소/최대 감지 거리 설정.
3. **IMU**: `<sensor type="imu">`로 정의. 가속도계 + 자이로스코프 데이터를 제공. 별도로 `gz-sim-imu-system` 플러그인을 모델에 추가해야 동작한다.
4. 센서를 추가할 때 **inertia(관성)** 값을 반드시 설정해야 한다. 없으면 물리 시뮬레이션이 불안정해진다.

## Differential Drive 구동 방식
로봇 청소기처럼 양쪽 바퀴 속도를 다르게 해서 방향을 바꾸는 구동 방식이다.

1. `gz-sim-diff-drive-system` 플러그인을 모델 SDF에 추가한다.
2. `<left_joint>`, `<right_joint>`에 각각 바퀴 조인트 이름을 지정한다.
3. `<wheel_separation>`(바퀴 간격)과 `<wheel_radius>`(바퀴 반지름)을 실제 모델 크기에 맞게 설정한다.
4. `<topic>cmd_vel</topic>`으로 설정하면, `/cmd_vel` 토픽에 `Twist` 메시지를 보내서 로봇을 조종할 수 있다.
5. 캐스터 휠은 `<joint type="ball">`로 자유 회전 가능하게 하고, 마찰을 0으로 설정(mu=0)하면 자연스럽게 끌려다닌다.

## ros_gz_bridge로 Gazebo ↔ ROS 2 연결
Gazebo와 ROS 2는 별개의 통신 체계를 사용하기 때문에 **브릿지**가 필요하다.

1. `ros_gz_bridge`의 `parameter_bridge` 노드를 launch 파일에 추가한다.
2. 인자 형식: `/토픽명@ROS타입[GZ타입` (GZ→ROS) 또는 `]` (ROS→GZ)
   - 예: `/agribot/camera/image@sensor_msgs/msg/Image[gz.msgs.Image`
3. 센서 데이터는 **GZ→ROS** 방향으로, 제어 명령(cmd_vel)은 **ROS→GZ** 방향으로 설정한다.
4. `gz topic -l`로 실제 Gazebo 토픽 이름을 확인하고, 브릿지 매핑이 일치하는지 반드시 확인해야 한다.

## ODE Trimesh 충돌 경고
`ODE Message 2: Trimesh-trimesh contach hash table bucket overflow`라는 메시지가 반복 출력되었다.

1. **원인**: GLB 메시를 collision geometry로 그대로 사용하면, ODE 물리 엔진이 삼각형 메시 간 충돌을 계산하느라 해시 테이블이 넘친다.
2. **영향**: 시뮬레이션 속도가 느려지지만 (Real Time Factor < 1.0), 로봇 동작 자체에는 영향 없다.
3. **해결법**: visual은 GLB 메시를 유지하되, collision만 간단한 box/cylinder로 교체하면 성능이 대폭 개선된다. (현재는 visual 유지를 위해 그대로 사용 중)

## teleop_twist_keyboard 사용법
`ros2 run teleop_twist_keyboard teleop_twist_keyboard`로 키보드 조종이 가능하다.

- 키를 한 번 누르면 그 속도로 **계속 움직인다** (꾹 누르지 않아도 됨)
- `i`=전진, `j`=좌회전, `l`=우회전, `k`=**정지**
- `q`/`z`=속도 증가/감소
- 반드시 **Gazebo Play 버튼(▶)**을 눌러야 물리 시뮬레이션이 시작된다.