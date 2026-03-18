[S14P-31] 센서 출력 점검 및 Gazebo-ROS 브리지 안정화

## 개요

S14P-31 센서 출력 점검을 진행했습니다.

이번 MR의 목적은 다음 2가지입니다.

1. 현재 시뮬레이션에서 카메라, LiDAR, IMU, `/odom`이 실제로 어떤 상태로 출력되는지 확인한다.
2. 팀원이 같은 브랜치를 pull 받은 뒤 동일한 결과를 재현할수 있도록, 센서 브리지 구성을 런치 파일에 반영하고 점검 결과를 문서화한다.

점검 결과, 카메라 RGB/Depth/CameraInfo, IMU, `/odom`, `/clock`은 정상 수신되도록 정리했고, LiDAR `/agribot/lidar/scan`은 아직 미수신 상태로 남아 추가 원인 분석이 필요합니다.

---

## 배경

기존 상태에서는 `ros2 topic list` 상 토픽 이름은 보이지만, 실제 메시지가 안정적으로 수신되지 않는 문제가 있었습니다.

확인해보니 원인은 크게 2가지였습니다.

- Gazebo가 기본적으로 pause 상태로 시작되어 토픽만 생성되고 센서 메시지는 흐르지 않던 문제
- 카메라 관련 토픽을 단일 `ros_gz_bridgeparameter_bridge`에 한 번에 묶어둘 경우 ROS 측 수신이 불안정하던 문제

즉, 단순히 "토픽이 보인다" 수준이 아니라 실제 `echo--once`와 발행 주기까지 확인 가능한 상태로 런치를 보완할 필요가 있었습니다.

---

## 주요 변경 사항

### 1. Gazebo 자동 재생으로 변경
- `spawn_agribot.launch.py`에서 `gz_args`에 `-r`을 추가했습니다.
- 이제 `ros2 launch agribot_bringup simulation.launch.py`실행 시 Gazebo가 바로 재생 상태로 올라옵니다.
- 수동으로 GUI에서 Play 버튼을 누르지 않아도 센서 메시지가 흐르도록 수정했습니다.

### 2. 브리지 구성을 역할별로 분리
기존에는 여러 센서 토픽을 단일 `parameter_bridge`에 몰아서 연결하고 있었습니다.

이번 MR에서는 아래처럼 분리했습니다.

- 상태 브리지
- `/clock`
- `/agribot/imu`
- `/cmd_vel`
- `/odom`
- 카메라 정보 브리지
- `/agribot/camera/camera_info`
- LiDAR 브리지
- `/agribot/lidar/scan`
- 이미지 전용 브리지
- `/agribot/camera/image`
- `/agribot/camera/depth_image`

카메라 이미지 계열은 `ros_gz_bridge parameter_bridge` 대신 `ros_gz_image image_bridge`를 사용하도록 변경했습니다.

### 3. 패키지 의존성 추가
- `agribot_description/package.xml`에 `ros_gz_image` 실행 의존성을 추가했습니다.
- 팀원이 동일한 의존성을 기준으로 실행할 수 있도록 반영했습니다.

### 4. 센서 점검 결과 문서 추가
- 점검 결과를 [S14P-31_센서_출력_점검.md] 문서로 정리했습니다.
- 문서에는 다음 내용이 포함되어 있습니다.
- 실행 환경
- 실행/검증 명령
- 센서 점검표
- bridge 수정 포인트
- 미해결 이슈
- 후속 작업 제안

---

## 검증 방법

아래 순서로 직접 검증했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export HOME=/tmp/codex-home
export ROS_LOG_DIR=/tmp/ros_logs
export __NV_PRIME_RENDER_OFFLOAD=1
export __GLX_VENDOR_LIBRARY_NAME=nvidia
export DRI_PRIME=1

colcon build --symlink-install --packages-select agribot_description agribot_bringup
ros2 launch agribot_bringup simulation.launch.py
```

실행 후 아래 명령으로 확인했습니다.

```bash
ros2 topic list
ros2 topic echo --once --field header /agribot/camera/image
ros2 topic echo --once --field header /agribot/camera/depth_image
ros2 topic echo --once /agribot/camera/camera_info
ros2 topic echo --once /agribot/imu
ros2 topic echo --once /odom
ros2 topic echo --once /clock
ros2 topic echo --once --field header /agribot/lidar/scan

gz topic -e -n 3 -t /agribot/camera/camera_info
gz topic -e -n 3 -t /agribot/imu
gz topic -e -n 3 -t /odom

ros2 topic hz /agribot/imu
```

———

## 검증 결과

### 정상 수신 확인

- /agribot/camera/image
- /agribot/camera/depth_image
- /agribot/camera/camera_info
- /agribot/imu
- /odom
- /clock

### 미수신

- /agribot/lidar/scan

### 주기 확인 결과

- CameraInfo: GZ 헤더 기준 0.925s -> 0.991s, 약 15.15Hz
- IMU: GZ 헤더 기준 0.890s -> 0.900s -> 0.910s, 100Hz
- Odometry: GZ 헤더 기준 0.884s -> 0.918s -> 0.952s, 약 29.4Hz

즉, 카메라/IMU/Odometry는 설정된 센서 주기 기준으로는 정상 출력으로 판단했습니다.

———

## 확인된 이슈

### 1. LiDAR 미수신

- /agribot/lidar/scan은 메인 런치 기준에서도 미수신이었습니다.
- 별도 브리지로 분리해도 미수신이어서, 단순 bridge 설정 문제로 단정하기는 어렵습니다.
- 현재는 gpu_lidar 센서 자체, 렌더링 계층, 혹은 시뮬레이터 성능 저하 영향 가능성을 우선 의심하고 있습니다.

### 2. Gazebo 실시간 성능 저하

- ros2 topic hz /agribot/imu 기준 실제 벽시계 발행률은 약 0.635Hz 수준이었습니다.
- 반면 GZ 메시지 헤더 기준 시뮬레이션 내부 시간은 IMU 100Hz로 정상 증가했습니다.
- 즉, 센서 설정값이 틀린 것보다는 Gazebo가 매우 느리게 돌고 있는 상태입니다.

### 3. 물리 충돌 병목 의심

Gazebo 실행 중 아래 경고가 반복되었습니다.

- ODE Message 2: Trimesh-trimesh contact hash table bucket overflow

코드상 다음 모델들이 시각 메쉬를 그대로 collision mesh로 사용 중이었습니다.

- agribot_description/models/greenhouse/model.sdf
- agribot_description/models/tomato_plant/model.sdf
- agribot_description/models/tomato/model.sdf

월드에 이 메쉬 기반 모델이 여러 개 배치되어 있어 물리 계산 부하가 큰 상태로 보입니다.

———

## 기대 효과

- 팀원이 동일한 런치 명령만으로 카메라, IMU, /odom, /clock 출력 상태를 바로 재현할 수 있습니다.
- S14P-31 결과물인 센서 점검표와 bridge 수정 포인트가 문서로 남아 이후 티켓에서 참조 가능합니다.
- 다음 작업인 S14P-32 프레임 정합, S14P-33 주행/오도메트리 보정 전에 센서 입출력 기반이 정리되었습니다.

———

## 후속 작업 제안

- LiDAR 센서를 gpu_lidar 외 다른 센서 타입으로 바꿔 비교테스트
  헤드리스 실행 시 LiDAR 발행 여부 비교
- greenhouse, tomato_plant, tomato collision geometry를 단순화해서 실시간 성능 개선
- 이후 S14P-32에서 camera_link, imu_link, base_link,odom 프레임 정합 진행

## 변경 파일

- agribot_ws/src/agribot_description/launch/spawn_agribot.launch.py
- agribot_ws/src/agribot_description/package.xml
- S14P-31_센서_출력_점검.md


[S14P-32] 로봇 부품 좌표 정합 및 TF 트리 구성

## 개요

S14P-32 로봇 부품 좌표 정합을 진행했습니다.

이번 MR의 목적은 다음 3가지입니다.

1. `map`, `odom`, `base_link`, `camera_link`, `lidar_link`, `imu_link`의 관계를 ROS 2 `tf` 기준으로 고정한다.
2. Gazebo에서 이미 발행 중인 `/odom`을 RViz2와 `tf2`가 바로 사용할 수 있도록 `/tf`로 연결한다.
3. 다음 작업인 Nav2, localization, perception이 같은 프레임 기준선을 공유할 수 있도록 문서와 런치 설정을 함께 남긴다.

이번 작업으로 센서 링크의 정적 변환과 `odom -> base_link` 동적 변환을 ROS 쪽에서 확인 가능한 상태로 정리했고, 임시 `map -> odom` 기준점도 함께 추가했습니다.

---

## 배경

S14P-31까지 진행한 시점에는 카메라, IMU, `/odom` 토픽은 확인되었지만, TF 트리 기준으로는 아직 빈 부분이 있었습니다.

구체적으로는 아래 문제가 있었습니다.

- Gazebo DiffDrive가 `/odom` 메시지는 발행하지만 ROS `tf` 트리에서 `odom -> base_link`가 보장되지 않음
- `camera_link`, `lidar_link`, `imu_link`의 상대 위치가 SDF 안에는 정의되어 있지만 ROS `tf_static`으로는 노출되지 않음
- `map` 기준 프레임이 없어 이후 RViz2, Nav2, localization 연동 시 기준점이 일관되지 않을 수 있음

즉, 센서 토픽이 살아 있는 것과 별개로 "로봇 몸통과 센서가 서로 어디에 붙어 있는가"를 ROS 2 표준 방식으로 정리할 필요가 있었습니다.

---

## 주요 변경 사항

### 1. 정적 TF 체인 추가
- `spawn_agribot.launch.py`에 `static_transform_publisher`를 추가했습니다.
- 아래 4개 관계를 런치 시 즉시 발행하도록 구성했습니다.
- `map -> odom`
- `base_link -> camera_link`
- `base_link -> lidar_link`
- `base_link -> imu_link`

센서 링크 위치 값은 기존 `model.sdf`에 정의된 pose를 그대로 사용했습니다.

### 2. `/odom`을 `/tf`로 재발행하는 노드 추가
- `agribot_description/odom_tf_broadcaster.py`를 새로 추가했습니다.
- 이 노드는 `/odom`을 구독해 `odom -> base_link` 변환을 `tf2_ros.TransformBroadcaster`로 발행합니다.
- Gazebo 오도메트리와 ROS TF 소비자 사이를 연결하는 최소 브리지 역할입니다.

### 3. 런치 인자 추가
- `publish_map_to_odom_tf` 인자를 추가했습니다.
- 현재는 기본값 `true`로 두어 임시 항등 `map -> odom`을 발행합니다.
- 이후 SLAM 또는 localization이 실제 `map -> odom`을 발행할 때는 `false`로 끌 수 있게 했습니다.

### 4. 패키지 의존성과 엔트리포인트 보강
- `agribot_description/package.xml`에 `rclpy`, `tf2_ros`, `nav_msgs`, `geometry_msgs`, `launch_ros` 의존성을 추가했습니다.
- `setup.py`에 `odom_tf_broadcaster` 콘솔 엔트리포인트를 등록했습니다.

### 5. 좌표 정합 문서 추가
- 작업 결과를 `S14P-32_로봇_부품_좌표_정합.md`에 정리했습니다.
- 문서에는 프레임 구조, 좌표 기준, 적용 내용, 검증 명령, 현재 제한 사항을 남겼습니다.

---

## 검증 방법

아래 순서로 직접 검증했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_description
source install/setup.bash
export HOME=/tmp/codex-home
export ROS_LOG_DIR=/tmp/ros_logs

ros2 launch agribot_description spawn_agribot.launch.py
```

실행 후 아래 명령으로 확인했습니다.

```bash
ros2 topic list | rg "^/tf($|_static$)"
timeout 10s ros2 topic echo --once /tf_static
timeout 12s ros2 topic echo --once /tf
timeout 10s ros2 run tf2_ros tf2_echo base_link imu_link
```

---

## 검증 결과

### 정상 확인

- `/tf`
- `/tf_static`
- `base_link -> camera_link` 정적 변환 발행
- `base_link -> imu_link` 정적 변환 해석
- `odom -> base_link` 동적 변환 발행

### 확인 로그 요약

- `ros2 topic list`에서 `/tf`, `/tf_static` 생성 확인
- `/tf_static`에서 `base_link -> camera_link` 변환 확인
  - translation: `(0.2, 0.0, 0.1)`
- `/tf`에서 `odom -> base_link` 변환 확인
  - translation: `(약 0, 0, 0)`
- `tf2_echo base_link imu_link`에서 변환 확인
  - translation: `(0.0, 0.0, 0.05)`

즉, 최소 기준선인 `odom -> base_link -> sensor_links` 구조는 ROS 2 쪽에서 확인 가능한 상태로 정리했습니다.

---

## 확인된 이슈 및 주의사항

### 1. `map -> odom`은 임시 기준점

- 이번 MR의 `map -> odom`은 localization이 아직 없어서 넣은 임시 항등 변환입니다.
- 이후 Nav2 / SLAM / AMCL이 실제 `map -> odom`을 발행하면 반드시 중복 발행되지 않도록 꺼야 합니다.
- 런치 인자 `publish_map_to_odom_tf:=false`로 비활성화할 수 있도록 구성했습니다.

### 2. LiDAR 발행 문제는 별도 이슈

- 이번 MR은 좌표 정합 범위이며, `lidar_link` 프레임만 먼저 고정했습니다.
- `S14P-31`에서 확인된 `/agribot/lidar/scan` 미수신 문제는 여전히 남아 있습니다.

### 3. Gazebo 물리 경고는 그대로 존재

- 실행 중 `Trimesh-trimesh contact hash table bucket overflow` 경고는 계속 발생했습니다.
- 현재 TF 구성 검증과는 별개지만, Gazebo 실시간 성능 저하 원인 후보로 남아 있습니다.

---

## 기대 효과

- 이후 RViz2, tf2_tools, Nav2가 같은 프레임 이름과 센서 상대 위치를 기준으로 동작할 수 있습니다.
- 팀원이 동일한 런치만 실행해도 `base_link` 기준 센서 좌표와 `odom` 기준 본체 좌표를 재현할 수 있습니다.
- 다음 티켓에서 localization이나 SLAM을 붙일 때 기존 프레임 체인을 다시 정의하는 비용이 줄어듭니다.

---

## 후속 작업 제안

- `S14P-33`에서 바퀴 파라미터와 `/odom` 응답을 실제 주행 기준으로 보정
- localization 또는 SLAM 도입 시 `map -> odom` 임시 정적 TF 제거
- LiDAR 미발행 원인 분석과 충돌체 단순화 작업 병행

## 변경 파일

- agribot_ws/src/agribot_description/launch/spawn_agribot.launch.py
- agribot_ws/src/agribot_description/package.xml
- agribot_ws/src/agribot_description/setup.py
- agribot_ws/src/agribot_description/agribot_description/odom_tf_broadcaster.py
- S14P-32_로봇_부품_좌표_정합.md


[S14P-33] 주행·오도메트리 보정 및 calibration world 추가

## 개요

S14P-33 주행·오도메트리 보정을 진행했습니다.

이번 MR의 목적은 다음 4가지입니다.

1. `agribot`의 Differential Drive 파라미터를 실제 바퀴 치수 기준으로 재점검하고, teleop 직진/회전 응답을 과하지 않게 보정한다.
2. `/odom` 발행 주기를 상향해 이후 Nav2, localization, RViz 기준선으로 바로 쓸 수 있는 수준으로 정리한다.
3. `cmd_vel`이 끊긴 뒤에도 마지막 속도 명령이 남아 로봇이 계속 움직이는 문제를 watchdog으로 막는다.
4. 기본 `farm_world`의 무거운 삼각메시 충돌 병목과 분리된 전용 calibration world를 추가해 주행 검증을 재현 가능하게 만든다.

이번 작업으로 `/cmd_vel -> diff drive -> /odom -> /tf` 흐름을 안정화했고, 실제 직진 테스트를 반복할 수 있는 경량 검증 환경과 작업 문서까지 함께 남겼습니다.

---

## 배경

S14P-32까지 진행한 시점에는 TF 트리는 정리됐지만, 실제 주행 기준으로는 아직 두 가지 문제가 남아 있었습니다.

- 기본 `farm_world` 실행 시 `Trimesh-trimesh contact hash table bucket overflow` 경고가 반복되어 Gazebo 물리 성능이 크게 흔들림
- Gazebo DiffDrive가 마지막 속도 명령을 유지해, 짧게 준 `/cmd_vel` 이후에도 로봇이 계속 전진할 수 있음

즉, 바퀴 파라미터만 수치상 맞는지 보는 수준이 아니라 "직진 명령이 안정적으로 반영되고, `/odom`이 정상 증가하며, 명령이 끝나면 멈추는가"까지 같이 보정할 필요가 있었습니다.

---

## 주요 변경 사항

### 1. DiffDrive 파라미터 보정
- `agribot_ws/src/agribot_description/models/agribot/model.sdf`를 수정했습니다.
- 기존 wheel geometry를 다시 확인한 결과:
  - `wheel_separation = 0.35`
  - `wheel_radius = 0.06`
- 위 두 값은 실제 wheel pose / collision과 일치하므로 유지했습니다.
- 대신 동적 응답을 아래처럼 보수적으로 조정했습니다.
  - `max_linear_velocity = ±0.40`
  - `max_linear_acceleration = ±0.60`
  - `max_linear_jerk = ±1.50`
  - `max_angular_velocity = ±1.20`
  - `max_angular_acceleration = ±1.20`
  - `max_angular_jerk = ±2.50`
- `odom_publish_frequency`는 `30 -> 50 Hz`로 올렸습니다.

### 2. `cmd_vel` watchdog 추가
- `agribot_description/cmd_vel_watchdog.py`를 새로 추가했습니다.
- 입력은 `/cmd_vel`, 출력은 `/cmd_vel_safe`입니다.
- watchdog은 `20 Hz`로 명령을 재발행하고, `0.25초` 동안 새 명령이 없으면 zero twist를 보냅니다.
- DiffDrive 플러그인의 입력 토픽도 `cmd_vel_safe`로 바꿨습니다.

### 3. 런치 경로 수정
- `spawn_agribot.launch.py`에서 Gazebo 브리지를 `/cmd_vel_safe` 기준으로 연결했습니다.
- 같은 런치에서 `cmd_vel_watchdog` 노드를 함께 실행하도록 추가했습니다.
- 이로써 teleop와 이후 Nav2는 계속 `/cmd_vel`만 사용하고, Gazebo 쪽에는 timeout이 적용된 안전한 명령만 전달됩니다.

### 4. 오도메트리 전용 calibration world 추가
- `agribot_ws/src/agribot_description/worlds/odometry_calibration_world.sdf`를 새로 추가했습니다.
- 구성은 아래처럼 최소화했습니다.
  - ground plane
  - sun light
  - 중심선 확인용 마커 3개
  - `agribot` 단일 배치
- 목적은 온실/식물/토마토 mesh collision 부하와 분리된 상태에서 주행 기준선을 검증하는 것입니다.

### 5. 종료 안정성 및 문서 정리
- `odom_tf_broadcaster.py`는 `KeyboardInterrupt`와 중복 shutdown을 정상 처리하도록 정리했습니다.
- 작업 결과를 `S14P-33_주행_오도메트리_보정.md`에 문서화했습니다.
- 메인 가이드의 teleop 예시도 현재 구현 기준인 `/cmd_vel`로 맞췄습니다.

---

## 검증 방법

아래 순서로 직접 검증했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_description
source install/setup.bash
export HOME=/tmp/codex-home
export ROS_LOG_DIR=/tmp/ros_logs

ros2 launch agribot_bringup simulation.launch.py \
  world:=/home/ssafy/SSAFY/S14P21A602/agribot_ws/src/agribot_description/worlds/odometry_calibration_world.sdf
```

실행 후 아래 명령으로 확인했습니다.

```bash
timeout 10s ros2 topic hz /odom
timeout 8s ros2 topic echo --once --field transforms /tf
timeout 3s ros2 topic pub -r 5 /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.2}, angular: {z: 0.0}}"
timeout 8s ros2 topic echo --once --field transforms /tf
```

---

## 검증 결과

### 정상 확인

- `/odom`이 약 `50 Hz`로 안정적으로 발행됨
- 직진 명령 후 `odom -> base_link`의 `x`가 정상 증가함
- `y` 편차와 yaw drift는 측정 오차 수준으로 작음
- 명령 입력이 끊긴 뒤 위치가 계속 누적되지 않아 watchdog 정지가 동작함
- calibration world에서는 기존 `farm_world`에서 보이던 ODE collision 경고가 발생하지 않음

### 확인 로그 요약

- `timeout 10s ros2 topic hz /odom`
  - 평균 약 `49.09 ~ 49.13 Hz`
- 직진 전 `odom -> base_link`
  - `x ≈ 0`
  - `y ≈ 0`
- `3초` 동안 `linear.x = 0.2` 명령 전송 후
  - `x = 0.5510845081793189`
  - `y = -1.145172846324149e-12`
- watchdog timeout 이후 재확인
  - `x = 0.5901500771292297`
  - 재재확인: `x = 0.5734698196138319`

즉, 전진 명령에 따라 `/odom`은 정상 증가했고, 명령 종료 뒤에는 로봇이 계속 가속되지 않는 수준으로 정리됐습니다.

---

## 확인된 이슈 및 주의사항

### 1. 기본 `farm_world`는 여전히 무거움

- 이번 MR은 주행 기준선 보정 범위이며, 기본 `farm_world`의 triangle-mesh collision 단순화까지는 포함하지 않았습니다.
- 따라서 실제 자율주행 전체 통합 검증은 이후 별도 성능 개선 작업이 필요합니다.

### 2. calibration world는 검증용 기준선

- 이번에 추가한 `odometry_calibration_world.sdf`는 S14P-33 검증용 최소 환경입니다.
- 실제 농장 월드에서의 최종 주행 안정화는 이후 환경 충돌체 정리와 함께 다시 확인해야 합니다.

### 3. watchdog은 의도적인 안전 장치

- 짧은 테스트 명령 뒤에도 로봇이 계속 움직이던 기존 거동을 막기 위해 넣은 안전 장치입니다.
- 이후 Nav2 연동 시에도 `/cmd_vel`만 유지하면 같은 구조를 그대로 사용할 수 있습니다.

---

## 기대 효과

- teleop 직진 테스트를 더 작은 편차로 반복할 수 있습니다.
- `/odom` 발행 주기가 50 Hz 수준으로 올라가 후속 localization/Nav2 기준선으로 쓰기 쉬워졌습니다.
- stale `cmd_vel`로 인한 계속 주행 문제가 사라져 검증과 디버깅이 안전해졌습니다.
- 무거운 농장 월드와 분리된 calibration world 덕분에 주행/오도메트리 이슈를 재현하고 비교하기 쉬워졌습니다.

---

## 후속 작업 제안

- `farm_world`의 `greenhouse`, `tomato_plant`, `tomato` collision 단순화
- calibration world 기준값을 바탕으로 실제 농장 월드에서도 직진 편차 재검증
- 이후 Nav2 연동 시 watchdog timeout과 local planner 응답의 궁합 확인

## 변경 파일

- agribot_ws/src/agribot_description/models/agribot/model.sdf
- agribot_ws/src/agribot_description/launch/spawn_agribot.launch.py
- agribot_ws/src/agribot_description/agribot_description/cmd_vel_watchdog.py
- agribot_ws/src/agribot_description/agribot_description/odom_tf_broadcaster.py
- agribot_ws/src/agribot_description/setup.py
- agribot_ws/src/agribot_description/worlds/odometry_calibration_world.sdf
- docs/S14P-33_주행_오도메트리_보정.md
- docs/수확해조_프로젝트_개발_계획_및_협업_가이드.md


[S14P-34] 비닐하우스 단일 구역 메타데이터 추가

## 변경 내용

- `agribot_navigation/config/zones.yaml` 파일 추가
- 현재 시뮬레이션의 비닐하우스 전체를 단일 구역 `greenhouse_01`로 정의
- 구역의 대표 위치와 기본 범위를 함께 명시해 후속 작업에서 공통 `zone_id`를 사용하도록 기준 마련

## 작업 이유

- 현재 비닐하우스 오브젝트는 1개뿐이지만, 프로젝트 문서와 ROS 인터페이스가 이미 `zone_id`를 전제로 설계되어 있음
- 이후 `plants.yaml`, `iot_devices.yaml`, 환경 센서 데이터, 백엔드 저장 구조에서 같은 `zone_id`를 재사용할 수 있도록 최소 메타데이터가 필요함
- 따라서 이번 작업은 "여러 구역 분할"이 아니라 "단일 구역 명시"에 초점을 맞춤

## 참고

- 현재는 운영 구역 1개만 정의한 최소 버전임
- 추후 실제 지도 생성 결과에 맞춰 bounds 값은 조정 가능

## 검증

- `zones.yaml` 파일이 작업 트리에 정상 추가된 것 확인
- 별도 빌드나 런타임 테스트는 수행하지 않음


[S14P-35] 식물·토마토 canonical ID 정의 및 CropStatus 식별 필드 확장

## 개요

S14P-35 식물·토마토 ID 정의를 진행했습니다.

이번 MR의 목적은 다음 3가지입니다.

1. `farm_world.sdf`에 배치된 개별 식물과 토마토 과실에 대해 외부 시스템에서 재사용 가능한 canonical ID를 정의한다.
2. Gazebo 모델 이름과 별개로 perception, control, IoT, backend가 공통으로 사용할 수 있는 ID 계약을 확정한다.
3. `CropStatus.msg`에 식별 필드를 반영해 이후 상태 발행 노드들이 같은 기준으로 `crop_id`, `plant_id`, `tomato_id`, `zone_id`를 실어 보낼 수 있게 한다.

이번 작업으로 시뮬레이션 월드 기준 식물 10개, 토마토 10개의 canonical ID를 단일 레지스트리로 정리했고, ROS 인터페이스까지 그 기준을 수용하도록 확장했습니다.

---

## 배경

S14P-34에서 `greenhouse_01` 단일 구역 메타데이터를 먼저 정의했지만, 그 위에서 실제 개별 작물 단위를 구분하는 규칙은 아직 비어 있었습니다.

구체적으로는 아래 문제가 있었습니다.

- Gazebo include name인 `tomato_plant_1`, `tomato_fruit_9`는 시뮬레이터 내부 이름일 뿐이라 외부 시스템 계약 ID로 그대로 쓰기 애매함
- perception, control, backend가 각자 다른 이름 규칙을 쓰기 시작하면 이후 수확 기록, 상태 이력, 알림 연계 시 식별자 정합이 깨질 수 있음
- 기존 `CropStatus.msg`는 작물 이름과 상태값만 담고 있어 개별 식물/과실 단위 추적이 어려움

즉, 단순히 문서에 이름만 적는 수준이 아니라 "월드 배치 객체 -> canonical ID -> ROS 메시지"까지 이어지는 공통 기준선을 먼저 고정할 필요가 있었습니다.

---

## 주요 변경 사항

### 1. 식물/토마토 개체 레지스트리 추가
- `agribot_ws/src/agribot_description/config/crop_instances.yaml` 파일을 새로 추가했습니다.
- 이 파일은 현재 시뮬레이션 기준 식물/토마토 ID의 single source of truth 역할을 합니다.
- 포함 내용은 아래와 같습니다.
  - `greenhouse_01 -> gh01` zone prefix 규칙
  - 식물 ID 패턴: `gh01_plant_<nn>`
  - 토마토 ID 패턴: `<plant_id>_tomato_<nn>`
  - 식물 10개와 토마토 10개의 canonical ID
  - 각 개체의 Gazebo 모델명
  - 각 개체의 pose 정보
  - 토마토 과실의 부모 식물 ID

### 2. Gazebo 이름과 외부 계약 ID를 분리
- `tomato_plant_1`, `tomato_fruit_9` 같은 월드 모델명은 그대로 보존하되, 외부 계약에서는 canonical ID를 사용하도록 원칙을 명시했습니다.
- 즉, 월드 모델명은 `source_model_name`으로만 유지하고, 서비스 간 데이터 연동은 아래 규칙을 따르도록 정리했습니다.
  - 식물 상태: `crop_id == plant_id`
  - 토마토 상태: `crop_id == tomato_id`

### 3. `CropStatus.msg` 확장
- `agribot_ws/src/agribot_interfaces/msg/CropStatus.msg`를 확장했습니다.
- 새로 추가한 필드는 아래와 같습니다.
  - `std_msgs/Header header`
  - `string crop_id`
  - `string zone_id`
  - `string plant_id`
  - `string tomato_id`
  - `string source_model_name`
  - `string crop_type`
- 기존 상태값 필드인 `crop_name`, `health_score`, `growth_stage`, `needs_water`, `ready_to_harvest`, `position`은 유지했습니다.
- 이 변경으로 이후 perception/control 노드가 식별자와 상태값을 함께 발행할 수 있는 기반을 만들었습니다.

### 4. 작업 문서 추가
- `docs/S14P-35_식물_토마토_ID_정의.md` 문서를 새로 추가했습니다.
- 문서에는 아래 내용을 정리했습니다.
  - ID 정의 원칙
  - 식물 ID 매핑표
  - 토마토 ID 매핑표
  - `CropStatus` 사용 규칙
  - 범위 제외 항목
  - 검증 방법
  - 현재 제한 사항

### 5. README 메시지 설명 갱신
- `README.md`의 `CropStatus.msg` 설명을 현재 인터페이스 기준으로 업데이트했습니다.
- 이제 문서상으로도 `crop_id`, `zone_id`, `plant_id`, `tomato_id`가 포함된 메시지임을 바로 확인할 수 있습니다.

---

## ID 규칙 요약

### 식물 ID
- 형식: `gh01_plant_<nn>`
- 예시: `gh01_plant_01`

### 토마토 ID
- 형식: `<plant_id>_tomato_<nn>`
- 예시: `gh01_plant_01_tomato_01`

### 사용 규칙
- 식물 상태 메시지에서는 `crop_id == plant_id`
- 토마토 상태 메시지에서는 `crop_id == tomato_id`
- 부모 식물 관계는 `plant_id` 필드로 유지
- Gazebo 월드 이름은 `source_model_name`으로만 유지

---

## 검증 방법

아래 순서로 직접 검증했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_interfaces agribot_description
```

추가로 아래 파일 내용을 직접 확인했습니다.

```bash
sed -n '1,220p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_description/config/crop_instances.yaml
sed -n '1,120p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_interfaces/msg/CropStatus.msg
sed -n '1,220p' ~/SSAFY/S14P21A602/docs/S14P-35_식물_토마토_ID_정의.md
```

---

## 검증 결과

### 정상 확인

- 식물 10개에 대한 canonical `plant_id` 정의 완료
- 토마토 10개에 대한 canonical `tomato_id` 정의 완료
- 각 토마토 과실에 대한 부모 `plant_id` 매핑 완료
- `CropStatus.msg`가 새 식별 필드 기준으로 정상 생성되도록 빌드 통과
- `agribot_description`, `agribot_interfaces` 패키지 빌드 통과

### 확인 로그 요약

- `colcon build --symlink-install --packages-select agribot_interfaces agribot_description` 실행 결과 최종 성공
- 빌드 중 `agribot_interfaces`의 예전 생성물이 symlink 단계와 충돌하는 이슈가 1회 있었음
- stale 생성물 경로를 정리한 뒤 재빌드해 정상 완료함

즉, 이번 MR은 문서 정의에 그치지 않고 실제 ROS 인터페이스 레벨에서 재사용 가능한 ID 계약으로 반영된 상태입니다.

---

## 확인된 이슈 및 주의사항

### 1. 현재 토마토는 식물당 1개 기준
- 현재 `farm_world.sdf`에는 식물당 토마토 과실 1개씩만 연결했습니다.
- 이후 과실 수가 늘어나면 같은 `plant_id` 아래 `tomato_02`, `tomato_03` 방식으로 확장하면 됩니다.

### 2. `unhealthy_leaf_1`은 이번 범위 제외
- 현재 월드에 있는 `unhealthy_leaf_1`은 식물/토마토 ID 정의 범위에 포함하지 않았습니다.
- 잎 개체 식별이 필요해지면 별도 `leaf_scan_id` 체계를 추가하는 편이 맞습니다.

### 3. perception 매핑 로직은 아직 없음
- 이번 MR은 ID 계약과 레지스트리 정의까지가 범위입니다.
- 실제 인식 결과를 nearest pose 또는 world model name 기준으로 `crop_id`에 연결하는 perception 로직은 후속 작업이 필요합니다.

---

## 기대 효과

- 이후 perception, mission manager, harvest 로직, backend 저장 구조가 같은 식별자를 기준으로 연결될 수 있습니다.
- 수확 기록이나 작물 상태 이력을 저장할 때 Gazebo 모델명 대신 안정적인 canonical ID를 사용할 수 있습니다.
- 현재 단일 구역 메타데이터(`greenhouse_01`)와 개별 작물 식별자가 결합돼 backend 스키마 확장 시 일관성을 유지하기 쉬워집니다.
- 향후 월드 객체가 늘어나더라도 같은 규칙으로 식물/과실 ID를 확장할 수 있습니다.

---

## 후속 작업 제안

- perception 노드에서 탐지 결과를 `crop_instances.yaml` 기준으로 `crop_id`에 매핑하는 로직 추가
- harvest / disease / history 저장 구조에서 `crop_id`, `plant_id`, `tomato_id`를 공통 키로 사용하도록 정리
- 잎 스캔 객체나 병해 샘플에 대한 별도 개체 ID 체계 필요 여부 검토

## 변경 파일

- agribot_ws/src/agribot_description/config/crop_instances.yaml
- agribot_ws/src/agribot_interfaces/msg/CropStatus.msg
- docs/S14P-35_식물_토마토_ID_정의.md
- README.md


[S14P-36] 지도 생성 설정

## 개요

S14P-36 지도 생성 설정을 진행했습니다.

이번 MR의 목적은 다음 3가지입니다.

1. AgriBot이 Gazebo 시뮬레이션 안에서 LiDAR를 기준으로 지도를 만들 수 있도록 `slam_toolbox` 기본 구성을 준비한다.
2. 팀원이 한 번의 launch 명령으로 시뮬레이션, SLAM, RViz를 함께 올릴 수 있도록 mapping 전용 런치를 추가한다.
3. 이후 티켓인 S14P-37 지도 저장, S14P-203 localization, S14P-204 Nav2 파라미터 조정이 바로 이어질 수 있도록 패키지 자원과 의존성을 정리한다.

이번 작업으로 `agribot_navigation` 패키지에 mapping 설정 파일, launch 파일, RViz 화면 설정, map 저장 디렉터리 안내를 추가했고, 패키지 빌드까지 통과하는 상태로 정리했습니다.

---

## 배경

기존 `agribot_navigation` 패키지는 `zones.yaml`만 있는 골격 상태였고, 실제로 지도 생성을 시작할 수 있는 실행 파일과 설정 파일이 없었습니다.

또한 현재 시뮬레이션 진입점인 `agribot_description/launch/spawn_agribot.launch.py`는 임시 `map -> odom` 정적 TF를 기본 발행하도록 되어 있어, SLAM이 실제 `map -> odom`을 발행하는 구성과는 충돌 가능성이 있었습니다.

즉, 이번 티켓에서는 단순히 YAML 하나를 추가하는 수준이 아니라 아래 기준을 먼저 갖출 필요가 있었습니다.

- 시뮬레이션 런치와 충돌 없이 SLAM이 TF를 소유할 수 있을 것
- LiDAR 토픽 `/agribot/lidar/scan`과 현재 프레임 체계 `map`, `odom`, `base_link`를 그대로 사용할 것
- 팀원이 바로 실행 가능한 RViz 화면과 map 저장 위치까지 함께 제공할 것

---

## 주요 변경 사항

### 1. SLAM Toolbox 매핑 파라미터 추가
- `agribot_ws/src/agribot_navigation/config/slam_mapping.yaml`을 새로 추가했습니다.
- 현재 로봇 기준에 맞춰 아래 항목을 연결했습니다.
- `map_frame: map`
- `odom_frame: odom`
- `base_frame: base_link`
- `scan_topic: /agribot/lidar/scan`
- LiDAR 최대 거리 10m와 비닐하우스 주행을 고려해 mapping update, travel threshold, loop closing 관련 기본값을 함께 조정했습니다.

### 2. mapping 통합 런치 추가
- `agribot_ws/src/agribot_navigation/launch/mapping.launch.py`를 새로 추가했습니다.
- 이 런치는 아래 구성을 한 번에 실행하도록 만들었습니다.
- `agribot_description`의 `spawn_agribot.launch.py`
- `slam_toolbox`의 `online_async_launch.py`
- mapping 전용 RViz2
- 여기서 `publish_map_to_odom_tf=false`를 내려 기존 임시 정적 TF를 끄고, SLAM이 `map -> odom` 변환을 담당하도록 구성했습니다.

### 3. mapping 전용 RViz 화면 추가
- `agribot_ws/src/agribot_navigation/rviz/mapping.rviz`를 새로 추가했습니다.
- 아래 항목이 바로 보이도록 기본 display를 구성했습니다.
- `/map`
- `/map_updates`
- `/agribot/lidar/scan`
- `map`, `odom`, `base_link`, `lidar_link` TF
- 팀원이 launch 직후 지도 생성 시작 여부를 바로 확인할 수 있도록 최소 구성으로 정리했습니다.

### 4. map 저장 디렉터리 스캐폴딩 추가
- `agribot_ws/src/agribot_navigation/maps/README.md`를 추가했습니다.
- 이후 S14P-37에서 `map_saver_cli`로 `greenhouse_map.pgm`, `greenhouse_map.yaml`을 저장할 위치와 명령 예시를 남겼습니다.

### 5. 패키지 설치 자원 및 의존성 보강
- `agribot_ws/src/agribot_navigation/setup.py`에서 `rviz`, `maps` 디렉터리도 함께 설치되도록 수정했습니다.
- `agribot_ws/src/agribot_navigation/package.xml`에 아래 실행 의존성을 추가했습니다.
- `agribot_description`
- `launch`
- `launch_ros`
- `ros2launch`
- `rviz2`
- 이를 통해 새 launch와 RViz 자원이 실제 설치 경로에서도 정상 동작하도록 정리했습니다.

---

## 검증 방법

아래 순서로 정적 검증과 패키지 빌드 검증을 진행했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation
python3 -m py_compile launch/mapping.launch.py

python3 -c "from pathlib import Path; import yaml; yaml.safe_load(Path('config/slam_mapping.yaml').read_text()); yaml.safe_load(Path('rviz/mapping.rviz').read_text()); print('yaml-ok')"

cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_navigation
```

추가로 아래 파일을 직접 확인했습니다.

```bash
sed -n '1,240p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/config/slam_mapping.yaml
sed -n '1,240p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/launch/mapping.launch.py
sed -n '1,220p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/package.xml
sed -n '1,220p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/setup.py
```

---

## 검증 결과

### 정상 확인

- `mapping.launch.py` Python 문법 검사 통과
- `slam_mapping.yaml` 파싱 통과
- `mapping.rviz` YAML 파싱 통과
- `agribot_navigation` 패키지 단독 빌드 통과
- launch, config, rviz, maps 자원이 설치 대상으로 정상 포함되도록 반영 완료

### 확인 로그 요약

- 첫 `colcon build`에서는 기존 `install/agribot_navigation`의 stale symlink 상태 때문에 `mapping.launch.py` 설치 단계가 1회 실패했습니다.
- 해당 패키지의 `build/agribot_navigation`, `install/agribot_navigation`만 정리한 뒤 재빌드해 정상 완료했습니다.

즉, 이번 MR은 "SLAM을 위한 설정 초안" 수준이 아니라 실제 워크스페이스에서 설치 가능한 mapping 패키지 상태까지 맞춘 작업입니다.

---

## 확인된 이슈 및 주의사항

### 1. 실제 map 파일은 아직 생성하지 않음
- 이번 티켓 범위는 S14P-36 설정 준비까지입니다.
- `greenhouse_map.pgm`, `greenhouse_map.yaml` 실제 생성은 다음 티켓인 S14P-37에서 수행하는 것이 맞습니다.

### 2. 런타임 SLAM 동작은 이번 MR에서 실주행 검증하지 않음
- 이번 작업에서는 문법, YAML, 패키지 설치/빌드 검증까지 수행했습니다.
- 실제 Gazebo를 띄운 뒤 로봇을 움직이며 `/map`이 증가하는지 확인하는 런타임 검증은 후속 실행 단계에서 진행하면 됩니다.

### 3. LiDAR 입력 품질은 기존 센서 상태에 의존
- `scan_topic`은 `/agribot/lidar/scan`으로 연결했지만, 실제 mapping 품질은 LiDAR 발행 안정성에 영향을 받습니다.
- 기존 센서 점검에서 LiDAR 미수신 이슈가 있었다면, mapping launch 실행 전 해당 부분을 함께 재확인할 필요가 있습니다.

---

## 기대 효과

- 팀원이 `ros2 launch agribot_navigation mapping.launch.py` 한 번으로 지도 생성 세션을 시작할 수 있습니다.
- 이후 S14P-37 map 저장, S14P-203 localization, S14P-204 Nav2 조정이 같은 패키지 구조 위에서 바로 이어질 수 있습니다.
- 임시 `map -> odom` 정적 TF와 SLAM TF가 충돌하지 않도록 미리 정리해 두어 후속 Nav2 연동 리스크를 줄였습니다.
- RViz 기본 화면이 함께 제공돼 SLAM 상태 확인과 디버깅 진입 장벽이 낮아집니다.

---

## 후속 작업 제안

- `mapping.launch.py` 실제 실행 후 teleop 기반으로 비닐하우스 전체를 주행하며 `/map` 증가 여부 확인
- `map_saver_cli`로 `greenhouse_map` 저장 후 S14P-37 결과물 생성
- 저장된 map을 기준으로 S14P-203 `amcl` localization launch 추가
- 이후 S14P-204에서 `nav2_params.yaml`과 costmap 설정 작성

## 변경 파일

- agribot_ws/src/agribot_navigation/config/slam_mapping.yaml
- agribot_ws/src/agribot_navigation/launch/mapping.launch.py
- agribot_ws/src/agribot_navigation/rviz/mapping.rviz
- agribot_ws/src/agribot_navigation/maps/README.md
- agribot_ws/src/agribot_navigation/package.xml
- agribot_ws/src/agribot_navigation/setup.py


[S14P-37] 비닐하우스 지도 생성·저장

## 개요

S14P-37 비닐하우스 지도 생성·저장을 진행했습니다.

이번 MR의 목적은 다음 3가지입니다.

1. 이후 localization과 Nav2가 바로 사용할 수 있는 저장 지도 산출물 `greenhouse_map.pgm`, `greenhouse_map.yaml`을 패키지에 추가한다.
2. 지도 파일을 한 번 생성하는 것으로 끝내지 않고, `map_server`로 다시 불러와 재사용 가능한 상태인지 검증한다.
3. 현재 `farm_world.sdf`의 물리 성능 제약이 있더라도, 팀원이 동일한 metadata를 기준으로 같은 기본 지도를 재생성할 수 있는 경로를 남긴다.

이번 작업으로 `agribot_navigation` 패키지에 baseline map generator, 저장 지도 preview launch, 실제 `greenhouse_map` 산출물을 추가했고, 설치된 패키지 경로에서 map load까지 검증했습니다.

---

## 배경

S14P-36까지 진행한 시점에는 `slam_toolbox` 설정, mapping launch, RViz 설정은 준비되어 있었지만 실제 저장 지도 파일은 아직 없었습니다.

또한 이번 turn에서 `mapping.launch.py`를 실제로 띄워 `farm_world.sdf` 기반 live mapping도 함께 확인해봤는데, 아래 문제가 바로 드러났습니다.

- Gazebo에서 `Trimesh-trimesh contact hash table bucket overflow` 경고가 지속적으로 반복됨
- `greenhouse`, `tomato_plant`, `tomato`가 triangle mesh collision을 그대로 사용해 물리 부하가 큼
- 시뮬레이션이 충분히 진행되지 않아 SLAM 기반 실주행 저장을 이번 상태 그대로는 재현성 있게 완료하기 어려움

즉, 이번 티켓에서는 "live SLAM 저장"만 바라보기보다, 우선 후속 티켓이 바로 쓸 수 있는 저장 map 산출물과 재로드 경로를 먼저 안정적으로 확보할 필요가 있었습니다.

---

## 주요 변경 사항

### 1. 저장 지도 산출물 추가
- `agribot_ws/src/agribot_navigation/maps/greenhouse_map.pgm`
- `agribot_ws/src/agribot_navigation/maps/greenhouse_map.yaml`
- 저장 map metadata는 아래 값으로 정리했습니다.
- `resolution: 0.1`
- `origin: [-35.0, -10.0, 0.0]`

### 2. baseline map generator 추가
- `agribot_ws/src/agribot_navigation/agribot_navigation/generate_static_map.py`를 새로 추가했습니다.
- 이 스크립트는 아래 shared metadata를 읽어 저장 map을 재생성합니다.
- `agribot_navigation/config/zones.yaml`
- `agribot_description/config/crop_instances.yaml`
- 비닐하우스 외벽, 출입구, 좌우 재배 구역, 개별 식물 footprint를 occupancy map으로 반영하도록 구성했습니다.

### 3. 저장 지도 preview launch 추가
- `agribot_ws/src/agribot_navigation/launch/map_preview.launch.py`를 새로 추가했습니다.
- 이 런치는 아래 구성을 한 번에 실행합니다.
- `nav2_map_server/map_server`
- `nav2_lifecycle_manager/lifecycle_manager`
- 선택적 `rviz2`
- 이를 통해 Gazebo 없이도 저장된 `greenhouse_map.yaml`을 다시 불러와 통로 구조가 보이는지 바로 확인할 수 있게 했습니다.

### 4. 패키지 실행 경로와 의존성 보강
- `agribot_ws/src/agribot_navigation/setup.py`에 `generate_static_map` console script를 추가했습니다.
- `agribot_ws/src/agribot_navigation/package.xml`에 아래 실행 의존성을 추가했습니다.
- `nav2_lifecycle_manager`
- `python3-yaml`
- `agribot_ws/src/agribot_navigation/maps/README.md`에는 재생성, preview, 추후 live SLAM 저장 명령까지 함께 정리했습니다.

---

## 검증 방법

아래 순서로 산출물 생성, 패키지 빌드, 저장 지도 재로드 검증을 진행했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export HOME=/tmp/codex-home
export ROS_LOG_DIR=/tmp/ros_logs

python3 src/agribot_navigation/agribot_navigation/generate_static_map.py
colcon build --symlink-install --packages-select agribot_navigation

ros2 run agribot_navigation generate_static_map --output-prefix /tmp/greenhouse_map_test
ros2 launch agribot_navigation map_preview.launch.py use_rviz:=false
```

추가로 아래 명령으로 산출물과 메타데이터를 직접 확인했습니다.

```bash
sed -n '1,120p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/maps/greenhouse_map.yaml
find ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/maps -maxdepth 1 -type f | sort
git status --short
```

---

## 검증 결과

### 정상 확인

- `greenhouse_map.pgm`, `greenhouse_map.yaml` 생성 완료
- `agribot_navigation` 패키지 단독 빌드 통과
- 설치된 패키지 기준 `ros2 run agribot_navigation generate_static_map` 실행 확인
- `map_preview.launch.py`에서 설치 경로의 저장 map load 성공

### 확인 로그 요약

- `map_server`가 `/home/ssafy/SSAFY/S14P21A602/agribot_ws/install/agribot_navigation/share/agribot_navigation/maps/greenhouse_map.yaml`을 정상 로드했습니다.
- 동일하게 `greenhouse_map.pgm`도 정상 로드했고, 로그 기준 map 크기는 `700 X 2450 @ 0.1 m/cell`로 확인했습니다.
- 별도로 `ros2 run agribot_navigation generate_static_map --output-prefix /tmp/greenhouse_map_test`도 성공해 설치된 entry point가 정상 동작함을 확인했습니다.

즉, 이번 MR은 단순히 저장 파일만 추가한 것이 아니라 "재생성 가능하고 다시 불러와 검증된 저장 지도"까지 포함한 작업입니다.

---

## 확인된 이슈 및 주의사항

### 1. `farm_world.sdf` 기반 live SLAM 저장은 아직 재현성이 낮음
- `mapping.launch.py` 실주행 시 Gazebo에서 `Trimesh-trimesh contact hash table bucket overflow` 경고가 대량으로 반복되었습니다.
- 현재 `greenhouse`, `tomato_plant`, `tomato` 모델이 mesh collision을 그대로 사용하고 있어 물리 병목이 큽니다.
- 따라서 이번 MR의 저장 지도는 "현재 협업용 기준선 map"으로 보는 것이 맞고, 추후 성능 개선 후 live SLAM 결과로 같은 파일명을 덮어쓰는 흐름이 적절합니다.

### 2. 이번 저장 map은 shared metadata 기반 baseline map임
- `zones.yaml`과 `crop_instances.yaml`을 기준으로 외벽, 통로, 재배 구역을 occupancy map으로 구성했습니다.
- 실제 센서 스캔을 누적한 SLAM 결과물과 완전히 동일하다고 보기는 어렵지만, localization/Nav2 연계를 시작할 기준 map으로는 바로 사용할 수 있습니다.

---

## 기대 효과

- 이후 S14P-203 localization이 바로 사용할 저장 map 산출물이 생겼습니다.
- 팀원이 `ros2 run agribot_navigation generate_static_map`으로 같은 기준 지도를 재생성할 수 있습니다.
- `map_preview.launch.py`로 Gazebo 없이도 map 파일 재로드를 바로 확인할 수 있어 디버깅 진입 비용이 낮아졌습니다.
- live SLAM 성능 문제가 남아 있더라도 후속 Nav2 설정 작업은 저장 map 기준으로 계속 진행할 수 있습니다.

---

## 후속 작업 제안

- `farm_world.sdf`의 mesh collision을 단순화해 Gazebo 실시간 성능 개선
- 성능 개선 후 `mapping.launch.py`로 비닐하우스 전체를 실제 주행하고 `map_saver_cli`로 `greenhouse_map` 재생성
- 저장 map 기준으로 S14P-203 `amcl` localization launch 추가
- 이후 S14P-204에서 `nav2_params.yaml`과 costmap 파라미터 조정

## 변경 파일

- agribot_ws/src/agribot_navigation/agribot_navigation/generate_static_map.py
- agribot_ws/src/agribot_navigation/launch/map_preview.launch.py
- agribot_ws/src/agribot_navigation/maps/greenhouse_map.pgm
- agribot_ws/src/agribot_navigation/maps/greenhouse_map.yaml
- agribot_ws/src/agribot_navigation/maps/README.md
- agribot_ws/src/agribot_navigation/package.xml
- agribot_ws/src/agribot_navigation/setup.py


[S14P-203] 지도 기반 위치 추정

## 개요

S14P-203 지도 기반 위치 추정을 진행했습니다.

이번 MR의 목적은 다음 3가지입니다.

1. 저장된 `greenhouse_map.yaml`을 기준으로 `map_server`와 `amcl`을 함께 실행할 수 있는 localization 경로를 추가한다.
2. Gazebo 시뮬레이션에서 임시 정적 `map -> odom` 대신 AMCL이 실제 `map -> odom`을 발행하도록 연결한다.
3. 팀원이 동일한 명령으로 localization 세션을 재현하고, RViz2에서 초기 위치를 지정해 바로 검증할 수 있도록 문서와 의존성을 함께 정리한다.

이번 작업으로 `agribot_navigation` 패키지에 AMCL 파라미터와 localization 전용 launch를 추가했고, 빌드와 launch argument 로딩까지 확인했습니다.

---

## 배경

S14P-202까지 진행한 시점에는 저장 지도 `greenhouse_map.pgm`, `greenhouse_map.yaml`은 이미 준비되어 있었고, `mapping.launch.py`와 `map_preview.launch.py`도 있었습니다.

하지만 실제 정적 지도 기반 운용 단계에서 필요한 localization 경로는 아직 비어 있었습니다.

구체적으로는 아래 상태였습니다.

- `spawn_agribot.launch.py`는 임시 항등 `map -> odom` 정적 TF를 발행하는 구조였음
- 저장 지도를 불러오는 `map_server`와 실제 위치 추정을 담당할 `amcl`을 함께 실행하는 launch가 없었음
- RViz2에서 `/initialpose`를 찍어 localization을 바로 확인하는 표준 실행 경로가 문서화되어 있지 않았음

즉, 지도는 이미 저장되어 있었지만 "저장 지도를 기준으로 로봇이 지금 어디 있는지 추정하는 단계"가 아직 연결되지 않은 상태였습니다.

---

## 주요 변경 사항

### 1. AMCL 파라미터 파일 추가
- `agribot_ws/src/agribot_navigation/config/amcl.yaml`을 새로 추가했습니다.
- 현재 로봇 프레임과 센서 토픽에 맞춰 아래 값을 반영했습니다.
- `base_frame_id: base_link`
- `odom_frame_id: odom`
- `global_frame_id: map`
- `scan_topic: /agribot/lidar/scan`
- LiDAR SDF 범위와 맞춘 `laser_min_range: 0.12`, `laser_max_range: 10.0`
- 이번 파일은 localization 시작선에 필요한 최소 설정으로 두었고, 세부 Nav2 주행 튜닝은 후속 티켓으로 분리했습니다.

### 2. localization 전용 launch 추가
- `agribot_ws/src/agribot_navigation/launch/localization.launch.py`를 새로 추가했습니다.
- 이 런치는 아래 구성을 한 번에 실행합니다.
- `agribot_description/spawn_agribot.launch.py`
- `nav2_map_server/map_server`
- `nav2_amcl/amcl`
- `nav2_lifecycle_manager/lifecycle_manager`
- 선택적 `rviz2`
- 특히 `publish_map_to_odom_tf:=false`를 넘겨, 기존 임시 정적 TF를 끄고 AMCL이 `map -> odom`을 맡도록 전환했습니다.

### 3. 실행 의존성 보강
- `agribot_ws/src/agribot_navigation/package.xml`에 아래 실행 의존성을 추가했습니다.
- `nav2_amcl`
- `nav2_map_server`
- 이를 통해 팀원이 패키지 의존성 기준만 맞추면 동일한 localization launch를 바로 실행할 수 있게 했습니다.

### 4. 사용 가이드와 작업 문서 추가
- `agribot_ws/src/agribot_navigation/maps/README.md`에 localization 실행 명령을 추가했습니다.
- `docs/S14P-203_지도_기반_위치_추정.md` 문서에 목표, 반영 내용, 실행 방법, 현재 제한 사항을 정리했습니다.
- RViz2에서 `2D Pose Estimate`로 `/initialpose`를 주는 절차까지 함께 남겼습니다.

---

## 검증 방법

아래 순서로 패키지 빌드와 localization launch 로딩을 검증했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_navigation
source install/setup.bash
export HOME=/tmp/codex-home
export ROS_LOG_DIR=/tmp/ros_logs

ros2 launch agribot_navigation localization.launch.py --show-args
```

추가로 아래 명령으로 변경 파일과 AMCL 설정을 직접 확인했습니다.

```bash
sed -n '1,220p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/launch/localization.launch.py
sed -n '1,220p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/config/amcl.yaml
git status --short
```

---

## 검증 결과

### 정상 확인

- `agribot_navigation` 패키지 단독 빌드 통과
- 설치된 패키지 기준 `localization.launch.py` 인자 로딩 성공
- launch 기본값으로 아래 경로가 연결됨
- `maps/greenhouse_map.yaml`
- `config/amcl.yaml`
- `rviz/mapping.rviz`

### 확인 로그 요약

- `ros2 launch agribot_navigation localization.launch.py --show-args` 기준 `use_sim_time`, `world`, `map`, `params_file`, `use_rviz`, `autostart` 인자가 정상 노출되었습니다.
- 설치 경로 기준 기본 map 파일은 `/home/ssafy/SSAFY/S14P21A602/agribot_ws/install/agribot_navigation/share/agribot_navigation/maps/greenhouse_map.yaml`으로 확인했습니다.
- 설치 경로 기준 AMCL 파라미터 파일은 `/home/ssafy/SSAFY/S14P21A602/agribot_ws/install/agribot_navigation/share/agribot_navigation/config/amcl.yaml`으로 확인했습니다.

즉, 이번 MR은 localization 설정 파일만 추가한 것이 아니라, 실제 패키지 설치 경로 기준으로 launch가 읽히는 상태까지 맞춘 작업입니다.

---

## 확인된 이슈 및 주의사항

### 1. 이번 MR은 localization 시작선까지 검증
- 이번 turn에서는 `ros2 launch ... --show-args`까지 확인했습니다.
- 실제 RViz2에서 초기 위치를 찍고 수렴 정도를 보는 런타임 검증은 Gazebo 세션을 길게 띄워 확인하는 후속 단계가 남아 있습니다.

### 2. localization 품질은 LiDAR 품질에 직접 영향받음
- `amcl`은 `/agribot/lidar/scan`을 사용하도록 연결했습니다.
- 따라서 scan 품질이나 시뮬레이션 성능 문제가 있으면 수렴 안정성도 함께 흔들릴 수 있습니다.

### 3. Nav2 주행 파라미터는 아직 범위 밖
- 이번 작업은 `map_server + amcl` 기반 위치 추정 경로를 만드는 범위입니다.
- costmap, planner, controller, recovery 동작은 후속 `S14P-204`에서 조정하는 편이 맞습니다.

---

## 기대 효과

- 저장된 `greenhouse_map` 기준 localization 실행 경로가 생겼습니다.
- 팀원이 `ros2 launch agribot_navigation localization.launch.py`만으로 같은 시작 구성을 재현할 수 있습니다.
- 기존 임시 `map -> odom` 정적 TF를 AMCL 기반 동적 추정으로 교체할 준비가 끝났습니다.
- 이후 S14P-204에서 Nav2 파라미터 조정을 바로 이어갈 수 있습니다.

---

## 후속 작업 제안

- 실제 Gazebo + RViz2 세션에서 `2D Pose Estimate` 후 `amcl_pose`, `particle_cloud`, `map -> base_link` 수렴 확인
- 저장 map 기준 `nav2_params.yaml` 작성 및 costmap/planner/controller 초기값 조정
- 시뮬레이션 성능과 LiDAR 품질을 함께 점검해 localization 흔들림 원인 분리

## 변경 파일

- agribot_ws/src/agribot_navigation/config/amcl.yaml
- agribot_ws/src/agribot_navigation/launch/localization.launch.py
- agribot_ws/src/agribot_navigation/maps/README.md
- agribot_ws/src/agribot_navigation/package.xml
- docs/S14P-203_지도_기반_위치_추정.md

[S14P-39] 자율주행 파라미터 조정 및 farm_world collision 경량화

## 개요

S14P-39 자율주행 파라미터 조정을 진행했습니다.

이번 MR의 목적은 다음 3가지입니다.

1. 저장된 정적 지도와 AMCL 기준선 위에서 Nav2 자율주행 스택을 실제로 기동 가능한 상태로 완성한다.
2. 비닐하우스 통로 환경에 맞게 planner, controller, costmap, recovery 파라미터를 조정해 RViz 목표점 이동 기준선을 만든다.
3. `farm_world`의 무거운 triangle-mesh collision 병목을 줄여, 시각 품질은 유지하면서 물리 계산과 TF 초기화를 더 안정적으로 만든다.

이번 작업으로 `navigation.launch.py`와 `nav2_params.yaml`을 추가해 정적 지도 기반 Nav2 스택을 바로 띄울 수 있게 했고, `farm_world`는 visual mesh는 유지한 채 collision만 단순화해 기존 ODE 충돌 병목을 줄였습니다.

---

## 배경

S14P-38까지 진행한 시점에는 저장 지도와 AMCL localization은 준비되어 있었지만, 실제 목표점 주행에 필요한 Nav2 서버 구성이 빠져 있었습니다.

구체적으로는 아래 문제가 있었습니다.

- `planner_server`, `controller_server`, `bt_navigator`, `behavior_server`, `waypoint_follower`를 한 번에 올리는 전용 launch가 없음
- 로봇 footprint, inflation, planner / controller 조합이 비닐하우스 통로 기준으로 아직 정리되지 않음
- 기본 `farm_world`는 `greenhouse`, `tomato_plant`, `tomato`, `leaf_scan`이 mesh collision을 그대로 사용하고 있어 Gazebo 물리 부하가 큼
- 실제로 Nav2 기동 시 `odom`과 `map` 관련 TF가 늦게 올라와 activation이 흔들리고, 이전 작업에서도 ODE `Trimesh-trimesh contact hash table bucket overflow` 경고가 반복됨

즉, 단순히 Nav2 YAML만 추가하는 수준이 아니라 "자율주행 파라미터 세팅"과 "월드 collision 경량화"를 같이 처리해야 실제 목표점 이동 기준선을 만들 수 있었습니다.

---

## 주요 변경 사항

### 1. Nav2 파라미터 파일 추가
- `agribot_ws/src/agribot_navigation/config/nav2_params.yaml`를 새로 추가했습니다.
- 이번 MR의 기본 조합은 아래와 같습니다.
  - Global Planner: `nav2_smac_planner::SmacPlanner2D`
  - Local Controller: `nav2_regulated_pure_pursuit_controller::RegulatedPurePursuitController`
  - Recovery: `spin`, `backup`, `wait`
- AgriBot 차체와 통로 여유폭을 기준으로 아래 값을 정리했습니다.
  - footprint: `[[0.24, 0.20], [0.24, -0.20], [-0.24, -0.20], [-0.24, 0.20]]`
  - local costmap: `4 x 4`, `0.05 m`
  - global costmap: `0.10 m`
  - inflation radius: `0.35`
  - desired linear velocity: `0.28 m/s`
  - goal tolerance: `0.15 m`, `0.15 rad`
- Nav2는 기본적으로 `Twist`를 사용하도록 두어 현재 `/cmd_vel -> /cmd_vel_safe` watchdog 구조와 바로 맞물리게 했습니다.

### 2. navigation 전용 launch 추가
- `agribot_ws/src/agribot_navigation/launch/navigation.launch.py`를 새로 추가했습니다.
- 이 launch는 기존 `localization.launch.py`를 그대로 포함하고, 그 위에 아래 Nav2 서버를 추가로 올립니다.
  - `controller_server`
  - `planner_server`
  - `smoother_server`
  - `behavior_server`
  - `bt_navigator`
  - `waypoint_follower`
  - `lifecycle_manager_navigation`
- 결과적으로 `ros2 launch agribot_navigation navigation.launch.py` 한 번으로 Gazebo + map_server + AMCL + Nav2 navigation stack까지 함께 검증할 수 있게 했습니다.

### 3. RViz 자율주행 검증 화면 보강
- `agribot_ws/src/agribot_navigation/rviz/mapping.rviz`를 보강했습니다.
- 아래 요소를 추가했습니다.
  - `nav2_rviz_plugins/GoalTool`
  - `/plan` global path 표시
  - `/local_plan` local path 표시
- 이제 RViz에서 `2D Pose Estimate` 후 `2D Goal Pose`로 바로 자율주행 검증이 가능합니다.

### 4. 패키지 의존성과 사용 가이드 정리
- `agribot_ws/src/agribot_navigation/package.xml`에 Nav2 planner / controller / smoother / behavior / BT / waypoint / RViz plugin 의존성을 추가했습니다.
- `agribot_ws/src/agribot_navigation/maps/README.md`에 full navigation launch 사용법과 검증 절차를 문서화했습니다.
- 작업 결과 문서는 `docs/S14P-39_자율주행_파라미터_조정.md`에 정리했습니다.

### 5. farm_world collision 경량화
- 시각 품질은 유지하고 collision만 단순화하는 방향으로 수정했습니다.
- `greenhouse`, `tomato_plant`, `leaf_scan` 모델에서는 mesh collision을 제거하고 visual mesh만 남겼습니다.
- `tomato`는 `static=true`로 바꿔 동적 mesh contact를 만들지 않게 했고, collision mesh도 제거했습니다.
- 대신 `agribot_ws/src/agribot_description/worlds/farm_world.sdf`에 보이지 않는 collision proxy를 추가했습니다.
  - 비닐하우스 외곽 벽: box collision
  - 작물 베드 영역 2개: box collision
- 즉, 화면에 보이는 모델은 그대로 두고 LiDAR / 물리 / costmap이 참조하는 충돌체만 단순화했습니다.

---

## 검증 방법

아래 순서로 직접 검증했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_description agribot_navigation
source install/setup.bash
export HOME=/tmp/codex-home
export ROS_LOG_DIR=/tmp/ros_logs

ros2 launch agribot_navigation navigation.launch.py
```

빠른 검증용으로는 아래 명령도 사용했습니다.

```bash
ros2 launch agribot_navigation navigation.launch.py --show-args
timeout 20s ros2 launch agribot_navigation navigation.launch.py use_rviz:=false
```

RViz에서는 아래 순서로 확인했습니다.

```bash
1. Fixed Frame이 `map`인지 확인
2. `2D Pose Estimate`로 초기 위치 지정
3. `2D Goal Pose`로 통로 안 목표 지정
4. `/plan`, `/local_plan`, `/map`, `/agribot/lidar/scan` 표시 확인
```

---

## 검증 결과

### 정상 확인

- `agribot_navigation` 빌드 성공
- `navigation.launch.py --show-args` 정상 출력
- `controller_server`, `planner_server`, `smoother_server`, `behavior_server`, `bt_navigator`, `waypoint_follower` configure 성공
- `SmacPlanner2D`, `RegulatedPurePursuitController`, `spin/backup/wait` recovery plugin 로딩 확인
- collision 경량화 이후 `controller_server`가 이전보다 더 빠르게 activation 단계까지 진행
- 수정 후 로그에서는 기존처럼 ODE `Trimesh-trimesh ... overflow` 문자열이 재발하지 않음

### 확인 로그 요약

- `ros2 launch agribot_navigation navigation.launch.py --show-args`
  - `map`, `localization_params_file`, `nav2_params_file`, `use_rviz`, `autostart` 등 주요 인자 노출 확인
- `timeout 20s ros2 launch agribot_navigation navigation.launch.py use_rviz:=false`
  - 초기에는 `odom -> base_link` 대기 후 `controller_server` activation 진입 확인
  - 이후 `map -> odom`은 AMCL 초기 위치가 없어서 늦게 형성되는 상태 확인

즉, Nav2 파라미터와 launch 자체는 정상적으로 붙었고, 월드 collision 경량화 이후에는 이전보다 기동 기준선이 분명히 좋아졌습니다.

---

## 확인된 이슈 및 주의사항

### 1. AMCL 초기 위치는 여전히 필요
- 이번 MR은 localization 위에 navigation stack을 얹은 작업입니다.
- 따라서 RViz에서 `2D Pose Estimate`를 주기 전까지는 `map -> odom`이 완전히 안정되지 않아 planner / controller가 map frame을 기다릴 수 있습니다.
- 이건 성능 문제라기보다 AMCL 동작 방식에 가까운 정상 흐름입니다.

### 2. collision은 단순화됐지만 visual은 유지됨
- 이번 변경은 visual mesh를 단순화한 것이 아닙니다.
- 화면에 보이는 온실 / 작물 / 열매 / 잎 메쉬는 유지했고, collision만 치환했습니다.
- 따라서 데모 품질을 떨어뜨리지 않으면서도 물리 부하를 줄이는 방향입니다.

### 3. tomato는 물리 객체가 아니게 됨
- `tomato`를 `static=true`로 바꾸고 collision을 제거했기 때문에, 이제 열매는 충돌 반응을 만드는 동적 물체가 아닙니다.
- 수확을 물리 접촉으로 구현할 계획이라면 이후 별도 구조를 다시 잡아야 합니다.

---

## 기대 효과

- 저장 지도 기반 `AMCL + Nav2` 검증이 한 번에 가능한 실행 경로가 생깁니다.
- RViz에서 목표점 주행 검증을 반복할 수 있어 이후 waypoint 순찰과 mission 로직 작업이 쉬워집니다.
- `farm_world`의 collision 병목이 줄어 Gazebo 물리 경고와 TF 초기화 지연을 완화할 수 있습니다.
- visual 퀄리티를 유지한 채 주행 성능만 개선하는 방향을 팀 기준선으로 남길 수 있습니다.

---

## 후속 작업 제안

- RViz에서 실제 `2D Pose Estimate -> 2D Goal Pose` 왕복 테스트를 여러 구간으로 반복해 goal tolerance 추가 보정
- `S14P-205` waypoint YAML 작성과 `S14P-41` 자동 순찰 노드 구현
- 필요하면 온실 내부 통로 collision proxy를 더 세분화해 costmap과 실제 주행 동선을 더 정밀하게 맞추기
- 수확 로직에서 토마토를 물리 객체로 다시 쓸 필요가 있다면, visual / interaction 전용 구조를 별도 분리

## 변경 파일

- agribot_ws/src/agribot_navigation/config/nav2_params.yaml
- agribot_ws/src/agribot_navigation/launch/navigation.launch.py
- agribot_ws/src/agribot_navigation/package.xml
- agribot_ws/src/agribot_navigation/maps/README.md
- agribot_ws/src/agribot_navigation/rviz/mapping.rviz
- docs/S14P-39_자율주행_파라미터_조정.md
- agribot_ws/src/agribot_description/worlds/farm_world.sdf
- agribot_ws/src/agribot_description/models/greenhouse/model.sdf
- agribot_ws/src/agribot_description/models/tomato_plant/model.sdf
- agribot_ws/src/agribot_description/models/tomato/model.sdf
- agribot_ws/src/agribot_description/models/leaf_scan/model.sdf


[S14P-205] 순찰 좌표 정의

## 개요

S14P-205 순찰 좌표 정의를 진행했습니다.

이번 MR의 목적은 다음 3가지입니다.

1. `greenhouse_01` 기준 순찰 좌표를 행(row) 단위로 정리해 이후 `patrol_node`가 바로 사용할 기준선을 만든다.
2. 각 좌표를 단순 숫자 목록이 아니라 `home`, `connector`, `entry`, `inspect`, `turn`, `exit` 의미를 가진 메타데이터로 구조화한다.
3. 좌표 파일이 깨지지 않았는지 패키지 내부에서 바로 검증할 수 있는 로더와 실행 명령을 함께 남긴다.

이번 작업으로 `agribot_navigation` 패키지에 순찰 좌표 파일 `patrol_waypoints.yaml`을 추가했고, 좌표 참조 무결성을 확인하는 validator와 실행 가이드까지 함께 정리했습니다.

---

## 배경

S14P-39까지 진행한 시점에는 정적 지도, AMCL, Nav2 목표점 이동 기준선은 준비되어 있었지만, 실제 자동 순찰이 사용할 waypoint 계약은 아직 비어 있었습니다.

구체적으로는 아래 문제가 있었습니다.

- 현재 문서 기준으로는 "행(row)과 구역(zone) 중심으로 waypoint를 설계하라"는 원칙은 있었지만, 실제 파일 산출물은 없었음
- 이후 `S14P-41` 자동 순찰 제어에서 사용할 좌표가 없어서, 노드 구현 시 좌표 정의와 제어 로직이 한 티켓에 섞일 위험이 있었음
- 개별 식물마다 목표점을 찍는 방식은 유지보수에 약하므로, 재배 베드 기준의 순찰 anchor를 먼저 고정할 필요가 있었음

즉, 이번 티켓에서는 순찰 제어 로직보다 먼저 "팀 전체가 공통으로 참조할 수 있는 waypoint 기준선"을 파일 형태로 확정하는 것이 핵심이었습니다.

---

## 주요 변경 사항

### 1. 순찰 좌표 메타데이터 파일 추가
- `agribot_ws/src/agribot_navigation/config/patrol_waypoints.yaml`을 새로 추가했습니다.
- 파일에는 아래 공통 메타데이터를 포함했습니다.
- `schema_version`
- `frame_id: map`
- `zone_id: greenhouse_01`
- `home_pose_id`
- 좌표 설계 근거(`coordinate_rationale`)
- 권장 주행/관찰 제약(`robot_constraints`)

### 2. 행(row) 단위 waypoint 구조 정의
- 순찰 좌표는 개별 식물 단위가 아니라 행 단위로 정의했습니다.
- 총 구성은 아래와 같습니다.
- `home` 1개
- `connector` 2개
- 좌측 베드용 `entry / inspect / turn`
- 우측 베드용 `entry / inspect / turn`
- 전체 기준으로는 `15개 waypoint`, `2개 route`, `17개 default patrol sequence`로 정리했습니다.
- 각 `inspect` waypoint에는 관찰 대상 `plant_id`, `tomato_id`를 함께 기록해 이후 perception / mission / harvest 로직이 같은 기준을 재사용할 수 있게 했습니다.

### 3. 좌우 베드 순찰 route 추가
- `routes` 항목에 아래 2개 경로를 정의했습니다.
- `greenhouse_01_left_bed_northbound`
- `greenhouse_01_right_bed_southbound`
- 각 route는 `entry -> inspect_pose_ids -> turn -> exit` 구조를 갖도록 만들었습니다.
- 이를 통해 이후 순찰 노드는 route 단위와 전체 기본 순찰 시퀀스 단위를 둘 다 사용할 수 있습니다.

### 4. 좌표 검증용 loader/validator 추가
- `agribot_ws/src/agribot_navigation/agribot_navigation/patrol_config.py`를 새로 추가했습니다.
- 이 모듈은 아래 검증을 수행합니다.
- waypoint / route 중복 ID 확인
- `home_pose_id` 존재 여부 확인
- `default_patrol_sequence` 참조 무결성 확인
- route가 참조하는 `entry`, `inspect`, `turn`, `exit` waypoint 존재 여부 확인
- 즉, 이번 MR은 좌표 YAML만 추가한 것이 아니라, 이후 작업에서 설정 파일이 깨졌을 때 바로 실패하도록 최소 검증 경로까지 포함합니다.

### 5. 실행 진입점과 가이드 추가
- `agribot_ws/src/agribot_navigation/setup.py`에 `validate_patrol_waypoints` 콘솔 엔트리포인트를 추가했습니다.
- `agribot_ws/src/agribot_navigation/maps/README.md`에 검증 명령을 문서화했습니다.
- 이제 팀원이 아래 명령으로 설치된 패키지 기준 검증을 바로 수행할 수 있습니다.

```bash
ros2 run agribot_navigation validate_patrol_waypoints
```

---

## 검증 방법

아래 순서로 빌드와 좌표 검증을 직접 확인했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_navigation
source install/setup.bash

ros2 run agribot_navigation validate_patrol_waypoints
```

추가로 아래 파일 내용을 직접 확인했습니다.

```bash
sed -n '1,260p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/config/patrol_waypoints.yaml
sed -n '1,260p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/agribot_navigation/patrol_config.py
sed -n '1,220p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/maps/README.md
```

---

## 검증 결과

### 정상 확인

- `agribot_navigation` 패키지 단독 빌드 통과
- `validate_patrol_waypoints` 실행 성공
- `patrol_waypoints.yaml` 로드 성공
- route/sequence 참조 무결성 검증 성공

### 확인 로그 요약

- `ros2 run agribot_navigation validate_patrol_waypoints` 실행 결과 아래 내용이 출력됐습니다.
- `Loaded patrol plan for zone greenhouse_01`
- `15 waypoints, 2 routes, 17 sequence entries`
- `greenhouse_01_left_bed_northbound: 5 inspect poses, 7 plants`
- `greenhouse_01_right_bed_southbound: 3 inspect poses, 3 plants`

즉, 이번 MR은 단순 문서성 좌표 나열이 아니라 실제 패키지 설치 경로 기준으로 읽히고 검증까지 통과한 순찰 기준선입니다.

---

## 확인된 이슈 및 주의사항

### 1. 이번 MR은 좌표 정의와 검증 기준선까지가 범위
- 실제 자동 순찰 실행 노드인 `patrol_node.py`는 아직 포함하지 않았습니다.
- 이 부분은 후속 `S14P-41`에서 waypoint 소비 로직과 start/stop/resume 제어를 붙이는 편이 맞습니다.

### 2. 수확용 세부 접근 좌표는 아직 포함하지 않음
- 이번 파일은 순찰용 행 단위 anchor를 정의하는 범위입니다.
- 특정 토마토에 가까이 접근하는 `approach pose`는 후속 `S14P-42` 또는 수확 로직 단계에서 파생시키는 구조가 적절합니다.

### 3. 좌표는 현재 저장 지도와 월드 메타데이터 기준 baseline
- 이번 좌표는 `farm_world.sdf`, `greenhouse_map.yaml`, `crop_instances.yaml` 기준으로 잡은 기준선입니다.
- 실제 Gazebo / RViz 주행 결과에 따라 `x`, `y`, `yaw`는 후속 튜닝에서 일부 미세 조정될 수 있습니다.

---

## 기대 효과

- 이후 `S14P-41`에서 순찰 제어 로직만 구현하면 같은 좌표 파일을 바로 재사용할 수 있습니다.
- 팀원이 모두 같은 `waypoint_id`, `route_id`, `plant_id`, `tomato_id` 기준으로 순찰 경로를 해석할 수 있습니다.
- 개별 식물마다 goal을 찍는 방식보다 수정 범위가 작아 지도 변경이나 작물 추가에 더 강한 구조를 확보할 수 있습니다.
- perception, mission manager, harvest 접근 로직이 같은 순찰 anchor를 중심으로 연결되기 쉬워집니다.

---

## 후속 작업 제안

- `S14P-41`에서 `patrol_waypoints.yaml`을 읽는 `patrol_node.py` 구현
- RViz / Gazebo에서 기본 순찰 시퀀스 각 waypoint에 대한 실제 도달 가능성 확인
- 수확 이벤트 발생 시 inspect pose에서 파생되는 `approach pose` 계산 로직 추가

## 변경 파일

- agribot_ws/src/agribot_navigation/config/patrol_waypoints.yaml
- agribot_ws/src/agribot_navigation/agribot_navigation/patrol_config.py
- agribot_ws/src/agribot_navigation/setup.py
- agribot_ws/src/agribot_navigation/maps/README.md


[S14P-41] 자동 순찰 제어

## 개요

S14P-41 자동 순찰 제어를 진행했습니다.

이번 MR의 목적은 다음 3가지입니다.

1. `S14P-205`에서 정의한 `patrol_waypoints.yaml`을 읽어 로봇이 waypoint를 순서대로 방문하는 실행 노드를 추가한다.
2. 순찰을 한 번에 끝까지 돌리는 것뿐 아니라, 중간에 멈추고 같은 지점부터 다시 이어서 갈 수 있도록 `start / stop / resume` 제어를 붙인다.
3. Nav2 실행 런치, 패키지 엔트리포인트, README까지 함께 연결해 팀원이 바로 실행하고 검증할 수 있게 만든다.

이번 작업으로 `agribot_navigation` 패키지에 `patrol_node.py`를 추가했고, `/patrol/start`, `/patrol/stop`, `/patrol/resume` 서비스와 `/patrol/status` 상태 토픽을 통해 자동 순찰을 제어할 수 있게 했습니다.

---

## 배경

`S14P-205`까지 진행한 시점에는 순찰 좌표와 route 메타데이터는 정리되어 있었지만, 실제로 그 waypoint를 소비해서 움직이는 실행 노드는 없었습니다.

구체적으로는 아래 문제가 있었습니다.

- `patrol_waypoints.yaml`은 존재하지만 이를 읽어 Nav2 goal로 보내는 순찰 실행 주체가 없었음
- 후속 티켓 요구사항인 "중간 정지 후 재개"를 고려하면 단순 목표점 이동보다 waypoint 진행 상태를 노드 내부에서 직접 관리할 필요가 있었음
- 설치된 패키지 경로 기준으로 설정 파일을 읽고, 서비스 이름까지 고정해 두지 않으면 팀원이 같은 방식으로 재현하기 어려웠음

즉, 이번 티켓의 핵심은 좌표 정의 이후의 다음 단계로서, `S14P-205` 산출물을 실제 주행 제어로 연결하는 최소 실행 경로를 만드는 것이었습니다.

---

## 주요 변경 사항

### 1. 자동 순찰 실행 노드 추가
- `agribot_ws/src/agribot_navigation/agribot_navigation/patrol_node.py`를 새로 추가했습니다.
- 이 노드는 `patrol_waypoints.yaml`의 `default_patrol_sequence`를 읽고 waypoint를 순서대로 방문합니다.
- 내부 구현은 `nav2_waypoint_follower`에 전부 위임하지 않고, `NavigateToPose` 액션을 waypoint 단위로 순차 호출하는 방식으로 구성했습니다.
- 이렇게 구성한 이유는 정지 시점과 재개 지점을 노드 내부 인덱스로 직접 관리하는 편이 `S14P-41` 요구사항에 더 단순하고 명확하기 때문입니다.

### 2. 순찰 상태 머신과 제어 서비스 추가
- 노드 내부에 아래 상태를 두었습니다.
- `idle`
- `starting`
- `running`
- `observing`
- `stopping`
- `stopped`
- `completed`
- `error`
- 외부 제어용 서비스도 함께 추가했습니다.
- `/patrol/start`
- `/patrol/stop`
- `/patrol/resume`
- 순찰 중지 시에는 현재 goal을 cancel하고, 재개 시에는 중단된 waypoint 인덱스부터 다시 시작하도록 만들었습니다.

### 3. inspect waypoint 관찰 대기 로직 추가
- `inspect` 목적의 waypoint에 도달하면 바로 다음 지점으로 넘어가지 않고 잠시 대기하도록 구현했습니다.
- 대기 시간은 `patrol_waypoints.yaml`의 `robot_constraints.recommended_observation_dwell_sec` 값을 재사용합니다.
- 이를 통해 문서에 정의한 "도착 후 잠시 멈추고 관찰" 요구사항이 실제 실행 노드에도 반영됩니다.

### 4. patrol 설정 로더 보강
- 기존 `agribot_ws/src/agribot_navigation/agribot_navigation/patrol_config.py`를 확장했습니다.
- 설치된 패키지 기준 기본 `patrol_waypoints.yaml` 경로를 계산하는 helper를 추가했습니다.
- `recommended_observation_dwell_sec`를 파싱하고 음수 여부를 검증하도록 보강했습니다.
- validator 출력에도 inspect dwell 정보를 포함해, 설치 환경 기준 설정 요약을 더 바로 확인할 수 있게 했습니다.

### 5. navigation.launch.py에 patrol 노드 연결
- `agribot_ws/src/agribot_navigation/launch/navigation.launch.py`에 patrol 관련 launch argument를 추가했습니다.
- `use_patrol`
- `patrol_waypoints_file`
- `patrol_autostart`
- 기본 `navigation.launch.py` 실행 시 patrol 노드도 함께 띄울 수 있고, 필요하면 자동 시작 여부를 launch argument로 조절할 수 있게 했습니다.

### 6. 엔트리포인트, 의존성, 실행 가이드 정리
- `agribot_ws/src/agribot_navigation/setup.py`에 `patrol_node` 콘솔 엔트리포인트를 추가했습니다.
- `agribot_ws/src/agribot_navigation/package.xml`에 `nav2_msgs`, `action_msgs`, `std_srvs`, `std_msgs`, `ament_index_python` 등 필요한 런타임 의존성을 추가했습니다.
- `agribot_ws/src/agribot_navigation/maps/README.md`에 아래 명령을 문서화했습니다.

```bash
ros2 service call /patrol/start std_srvs/srv/Trigger "{}"
ros2 service call /patrol/stop std_srvs/srv/Trigger "{}"
ros2 service call /patrol/resume std_srvs/srv/Trigger "{}"
ros2 topic echo /patrol/status
```

---

## 검증 방법

아래 순서로 문법 검사, 빌드, validator, patrol 노드 기동을 직접 확인했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_navigation
source install/setup.bash

ros2 run agribot_navigation validate_patrol_waypoints
timeout 5s ros2 run agribot_navigation patrol_node
ros2 service list | rg '^/patrol/(start|stop|resume)$'
```

추가로 변경 파일들의 문법과 내용도 직접 확인했습니다.

```bash
python3 -m py_compile \
  ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/agribot_navigation/patrol_config.py \
  ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/agribot_navigation/patrol_node.py \
  ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/launch/navigation.launch.py
```

---

## 검증 결과

### 정상 확인

- `agribot_navigation` 패키지 단독 빌드 통과
- `validate_patrol_waypoints` 실행 성공
- `patrol_node` 설치 경로 기준 기동 성공
- `/patrol/start`, `/patrol/stop`, `/patrol/resume` 서비스 등록 확인

### 확인 로그 요약

- `ros2 run agribot_navigation validate_patrol_waypoints` 실행 결과 아래 내용이 출력됐습니다.
- `Loaded patrol plan for zone greenhouse_01`
- `15 waypoints, 2 routes, 17 sequence entries, 3.0s inspect dwell`
- `greenhouse_01_left_bed_northbound: 5 inspect poses, 7 plants`
- `greenhouse_01_right_bed_southbound: 3 inspect poses, 3 plants`
- `timeout 5s ros2 run agribot_navigation patrol_node` 실행 시 patrol plan 로드 로그가 정상 출력됐습니다.
- `ros2 service list`에서 `/patrol/start`, `/patrol/stop`, `/patrol/resume` 3개 서비스가 확인됐습니다.

즉, 이번 MR은 문서상 계획 수준이 아니라 실제 설치된 ROS 2 패키지에서 patrol 노드가 기동되고 제어 서비스가 올라오는 수준까지 연결한 작업입니다.

---

## 확인된 이슈 및 주의사항

### 1. 이번 MR은 순찰 실행과 제어 기준선까지가 범위
- waypoint 순차 방문, 관찰 대기, 중지/재개는 포함했습니다.
- 하지만 perception 이벤트에 따라 수확 위치로 분기하거나, 작업 후 원래 순찰 지점이나 home으로 복귀하는 로직은 아직 포함하지 않았습니다.
- 이 부분은 후속 `S14P-42`, mission manager 티켓과 자연스럽게 이어지는 범위입니다.

### 2. 상태 토픽은 현재 `std_msgs/String` JSON 형태
- `/patrol/status`는 현재 빠른 연결을 위해 JSON 문자열을 발행합니다.
- 문서에서 제안한 `MissionStatus.msg` 또는 별도 인터페이스가 준비되면 그쪽으로 승격하는 것이 더 적절합니다.

### 3. 이번 턴에서는 Gazebo 실제 순찰 주행까지는 수행하지 않음
- 노드 기동, 서비스 등록, 설정 로딩, 빌드 검증까지는 확인했습니다.
- 다만 실제 Gazebo + AMCL + Nav2 + map 환경에서 17개 waypoint 전체를 완주하는 end-to-end 검증은 아직 별도로 진행해야 합니다.

---

## 기대 효과

- 이제 `agribot_navigation` 패키지 기준으로 자동 순찰의 최소 실행 경로가 생겼습니다.
- 팀원이 `navigation.launch.py`를 띄운 뒤 서비스 호출만으로 순찰을 시작, 중지, 재개할 수 있습니다.
- `S14P-205`에서 정의한 waypoint 메타데이터가 실제 제어 로직에서 재사용되기 시작했기 때문에, 이후 perception / mission / harvest / dashboard 연결이 쉬워집니다.
- 향후 `RunPatrol.action`이나 `MissionStatus.msg`를 도입하더라도, 현재 노드 구조를 기반으로 단계적으로 확장할 수 있습니다.

---

## 후속 작업 제안

- Gazebo + RViz 환경에서 17개 기본 순찰 시퀀스 전체 완주 검증
- `MissionStatus.msg` 또는 `RunPatrol.action`으로 인터페이스 승격
- perception 이벤트 발생 시 inspect waypoint에서 접근 pose로 분기하는 mission 연동 추가
- 수확 또는 예외 처리 후 `home_pose` 복귀 및 원래 순찰 지점 재개 로직 연결

## 변경 파일

- agribot_ws/src/agribot_navigation/agribot_navigation/patrol_node.py
- agribot_ws/src/agribot_navigation/agribot_navigation/patrol_config.py
- agribot_ws/src/agribot_navigation/launch/navigation.launch.py
- agribot_ws/src/agribot_navigation/setup.py
- agribot_ws/src/agribot_navigation/package.xml
- agribot_ws/src/agribot_navigation/maps/README.md


[S14P-42] 접근·복귀 경로 로직

## 개요

S14P-42 접근·복귀 경로 로직을 진행했습니다.

이번 MR의 목적은 다음 3가지입니다.

1. `S14P-205`, `S14P-41`에서 정리한 순찰 inspect waypoint와 작물 메타데이터를 이용해, 특정 토마토에 대한 접근 위치를 계산한다.
2. 수확 작업이 끝난 뒤 로봇이 원래 순찰 지점으로 복귀하거나, 필요하면 `home_pose`로 복귀할 수 있는 정책을 명확히 만든다.
3. patrol 노드와 Nav2 사이에 harvest 전용 조정 노드를 추가해 `정지 -> 접근 -> 작업 대기 -> 복귀 -> 순찰 재개` 흐름을 실제 ROS 2 노드 기준으로 연결한다.

이번 작업으로 `agribot_navigation` 패키지에 접근 pose 계산 유틸리티와 복귀 조정 노드를 추가했고, 설치된 패키지 기준 CLI 계산, 단위 테스트, 빌드까지 통과하는 상태로 정리했습니다.

---

## 배경

`S14P-41`까지 진행한 시점에는 순찰 waypoint를 따라 이동하고 중간 정지/재개까지는 가능했지만, 특정 토마토를 발견했을 때 "어디로 짧게 파고들어 접근할지"와 "작업 후 어디로 복귀할지"를 계산하는 로직은 아직 없었습니다.

구체적으로는 아래 문제가 있었습니다.

- `patrol_waypoints.yaml`에는 inspect anchor까지만 정의되어 있고, 토마토 수확용 세부 접근 좌표는 비어 있었음
- `crop_instances.yaml`에는 식물/토마토 개체 pose가 정리되어 있지만, 이를 순찰 route와 연결해 접근 pose로 바꾸는 코드가 없었음
- 기존 `patrol_node`만으로는 수확 시점에 순찰을 잠시 멈추고, 작업 후 원래 자리나 `home_pose`로 복귀한 뒤 다시 순찰을 이어가는 흐름을 표현하기 어려웠음

즉, 이번 티켓의 핵심은 "토마토를 찾으면 inspect 지점에서 어디까지 접근할지 계산하고, 작업 후 어디로 복귀할지 상태 전환까지 묶는 것"이었습니다.

---

## 주요 변경 사항

### 1. harvest routing 설정과 validator 확장
- `agribot_ws/src/agribot_navigation/config/patrol_waypoints.yaml`에 `harvest_routing` 섹션을 추가했습니다.
- 아래 정책을 설정값으로 분리했습니다.
  - 재배 베드 경계 기준 접근 마진
  - inspect 지점에서 허용할 최대 측면 오프셋
  - 기본 복귀 모드
  - fallback 복귀 모드
- `agribot_ws/src/agribot_navigation/agribot_navigation/patrol_config.py`도 함께 확장해, `coordinate_rationale.source_bounds`와 `harvest_routing` 값을 로드하고 무결성을 검증하도록 만들었습니다.

### 2. 토마토 기준 접근 pose 계산 유틸리티 추가
- `agribot_ws/src/agribot_navigation/agribot_navigation/harvest_routing.py`를 새로 추가했습니다.
- 이 모듈은 아래 3개 데이터를 함께 읽습니다.
  - `patrol_waypoints.yaml`
  - `crop_instances.yaml`
  - route / inspect waypoint 메타데이터
- 내부 동작은 아래 순서로 구성했습니다.
  - `tomato_id`에 해당하는 부모 `plant_id` 확인
  - 해당 토마토를 관찰하는 inspect waypoint와 route 선택
  - 좌우 베드 방향에 따라 재배 베드 경계 안쪽으로 접근 pose 투영
  - `resume_patrol` 또는 `home` 기준 return target 계산
  - fallback return target 계산
- 즉, 접근 좌표를 하드코딩하지 않고 `토마토 ID -> 순찰 route -> 접근 pose -> 복귀 waypoint`로 파생시키는 구조를 만들었습니다.

### 3. patrol 정지/접근/복귀 조정 노드 추가
- `agribot_ws/src/agribot_navigation/agribot_navigation/harvest_route_node.py`를 새로 추가했습니다.
- 이 노드는 아래 입력을 받습니다.
  - `CropStatus`의 `ready_to_harvest=true`
  - 수동 테스트용 `std_msgs/String` 기반 `harvest/request`
  - `patrol/status`
- 내부 흐름은 아래 상태로 구성했습니다.
  - `waiting_for_patrol_pause`
  - `approaching`
  - `harvesting`
  - `returning`
  - `resuming_patrol`
  - `completed`
  - `error`
- 순찰이 돌고 있으면 먼저 `/patrol/stop`을 호출하고, 정지 확인 후 접근 goal을 보냅니다.
- 접근 성공 후에는 짧은 dwell로 수확 작업 대기 시간을 시뮬레이션하고, 이후 복귀 goal을 전송합니다.
- 복귀 성공 시 `return_mode=resume_patrol`이면 `/patrol/resume`을 호출하고, 실패하면 `fallback_return_waypoint_id`로 한 번 더 복귀를 시도합니다.

### 4. navigation launch와 엔트리포인트 연결
- `agribot_ws/src/agribot_navigation/launch/navigation.launch.py`에 아래 launch argument를 추가했습니다.
  - `use_harvest_route`
  - `crop_instances_file`
  - `harvest_return_mode`
- 기본 launch에서 `harvest_route_node`를 함께 띄울 수 있게 연결했습니다.
- `agribot_ws/src/agribot_navigation/setup.py`에는 아래 console script를 추가했습니다.
  - `plan_harvest_route`
  - `harvest_route_node`
- `agribot_ws/src/agribot_navigation/package.xml`에는 `agribot_interfaces` 의존성을 추가했습니다.

### 5. 단위 테스트 추가
- `agribot_ws/src/agribot_navigation/test/test_harvest_routing.py`를 새로 추가했습니다.
- 아래 경우를 테스트했습니다.
  - 우측 베드 토마토에 대해 lane 방향에 맞는 접근 pose 계산
  - `home` 강제 복귀 모드 계산
  - `resume_patrol` 시 preferred return waypoint 반영
- 이 테스트로 접근/복귀 계산 로직을 Gazebo 없이도 빠르게 검증할 수 있게 했습니다.

---

## 검증 방법

아래 순서로 문법 검사, 단위 테스트, 빌드, 설치된 entry point 실행을 직접 확인했습니다.

```bash
cd ~/SSAFY/S14P21A602

python3 -m py_compile \
  agribot_ws/src/agribot_navigation/agribot_navigation/patrol_config.py \
  agribot_ws/src/agribot_navigation/agribot_navigation/harvest_routing.py \
  agribot_ws/src/agribot_navigation/agribot_navigation/harvest_route_node.py \
  agribot_ws/src/agribot_navigation/test/test_harvest_routing.py

python3 -m pytest \
  agribot_ws/src/agribot_navigation/test/test_harvest_routing.py

cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_navigation
source install/setup.bash

ros2 run agribot_navigation plan_harvest_route --tomato-id gh01_plant_09_tomato_01
```

추가로 아래 파일 내용을 직접 확인했습니다.

```bash
sed -n '1,260p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/agribot_navigation/harvest_routing.py
sed -n '1,320p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/agribot_navigation/harvest_route_node.py
sed -n '1,120p' ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/config/patrol_waypoints.yaml
```

---

## 검증 결과

### 정상 확인

- `py_compile` 문법 검사 통과
- `pytest` 기준 `3 passed`
- `agribot_navigation` 패키지 단독 빌드 통과
- 설치된 패키지 기준 `plan_harvest_route` 실행 성공

### 확인 로그 요약

- `python3 -m pytest .../test_harvest_routing.py`
  - `3 passed in 0.08s`
- `ros2 run agribot_navigation plan_harvest_route --tomato-id gh01_plant_09_tomato_01`
  - `route_id = greenhouse_01_right_bed_southbound`
  - `inspect_waypoint_id = greenhouse_01_right_rear_inspect`
  - `approach_pose = (15.3179, 166.456497, yaw 0.0)`
  - `return_mode = resume_patrol`
  - `fallback_return_waypoint_id = greenhouse_01_home`

즉, 이번 MR은 수확 접근·복귀 아이디어 수준이 아니라, 실제 설치된 패키지 기준으로 접근 좌표와 복귀 목표를 계산하고 재사용할 수 있는 상태까지 연결한 작업입니다.

---

## 확인된 이슈 및 주의사항

### 1. 이번 MR은 접근·복귀 경로 기준선까지가 범위
- 접근 pose 계산과 복귀 상태 전환은 포함했습니다.
- 하지만 실제 토마토를 제거하거나 바구니 적재를 기록하는 수확 액션 서버는 아직 포함하지 않았습니다.
- 이 부분은 후속 `S14P-453`, `S14P-454`, `S14P-455`와 자연스럽게 이어지는 범위입니다.

### 2. 수확 작업은 현재 dwell 기반 시뮬레이션
- `harvest_route_node`는 접근 후 `harvest_dwell_sec`만큼 대기한 뒤 복귀하도록 구성했습니다.
- 즉, 현재는 "수확 시퀀스 placeholder" 역할이며, 실제 manipulator/harvest action이 붙으면 이 부분을 교체하는 구조가 맞습니다.

### 3. Gazebo 기반 end-to-end 주행은 아직 별도 검증 필요
- 이번 turn에서는 계산 로직, 단위 테스트, build, 설치된 CLI 실행까지 확인했습니다.
- 실제 Gazebo + AMCL + Nav2 + patrol node가 함께 떠 있는 상태에서 접근 후 복귀까지 완주하는 검증은 후속 통합 세션에서 진행하면 됩니다.

---

## 기대 효과

- perception 또는 mission 쪽에서 `tomato_id`만 넘기면 접근 pose와 복귀 target을 같은 기준으로 계산할 수 있습니다.
- `patrol_node`와 수확 로직 사이에 명확한 연결 지점이 생겨, 이후 수확 액션 서버를 붙이기 쉬워집니다.
- 복귀 정책을 `resume_patrol`과 `home`으로 분리해, 데모 상황에 따라 안전한 fallback을 유지할 수 있습니다.
- 순찰 anchor와 작물 canonical ID가 실제 harvest routing까지 이어지기 시작했기 때문에, 팀원 간 데이터 계약이 더 단단해집니다.

---

## 후속 작업 제안

- `S14P-453` 수확 액션 서버와 연결해 dwell 대신 실제 수확 결과를 받아 복귀 시작
- `S14P-455`에서 `RETURN_HOME -> RESUME` 미션 상태를 별도 인터페이스로 승격
- Gazebo 통합 세션에서 `harvest/request` 발행 후 접근/복귀 완주 검증
- 필요하면 접근 pose 계산 시 토마토 높이, 정면 정렬, 그리퍼 진입 방향까지 반영하도록 고도화

## 변경 파일

- agribot_ws/src/agribot_navigation/agribot_navigation/patrol_config.py
- agribot_ws/src/agribot_navigation/config/patrol_waypoints.yaml
- agribot_ws/src/agribot_navigation/agribot_navigation/harvest_routing.py
- agribot_ws/src/agribot_navigation/agribot_navigation/harvest_route_node.py
- agribot_ws/src/agribot_navigation/launch/navigation.launch.py
- agribot_ws/src/agribot_navigation/setup.py
- agribot_ws/src/agribot_navigation/package.xml
- agribot_ws/src/agribot_navigation/test/test_harvest_routing.py


[test] RViz 초기화 안정화 및 Gazebo 시간 충돌 분리

## 개요

`test` 브랜치에서 목표점 자율주행 실행 흐름을 다시 점검하면서,
팀원이 같은 코드를 pull 받았을 때도 Gazebo, RViz, localization 초기화가 더 안정적으로 재현되도록 정리했습니다.

이번 MR의 목적은 다음 4가지입니다.

1. `navigation.launch.py` 실행 시 Gazebo만 뜨고 RViz가 같이 안 뜨는 문제를 구조적으로 막는다.
2. RViz에서 `Global Status: Error`, `Fixed Frame [map] does not exist`, 검은 화면, `Set Initial Pose` 비활성처럼 보이던 문제를 줄인다.
3. 백그라운드에 남아 있던 다른 `gz sim server` 때문에 `/clock`, `/odom`, `/tf` 시간이 섞이던 문제를 launch 레벨에서 차단한다.
4. 비전공 팀원도 실행 순서와 주의사항을 다시 따라갈 수 있도록 TIL 문서 설명을 보강한다.

이번 작업으로 RViz 자동 실행 충돌, RViz 설정 충돌, startup 시 `map` 프레임 부재, Gazebo transport 혼선 문제를 단계적으로 정리했습니다.

---

## 브랜치 정보

- Source branch: `test`
- 작업 중 생성한 관련 커밋
  - `3113e3c`
  - `b39d0d3`
  - `8bcbb82`

---

## 배경

기존 상태에서는 사용자가 아래와 같은 문제를 연속적으로 겪을 수 있었습니다.

- `ros2 launch agribot_navigation navigation.launch.py` 실행 시 Gazebo만 뜨고 RViz가 자동으로 안 뜸
- 수동으로 RViz를 띄워도 검은 화면만 보이거나 `Fixed Frame [map] does not exist`가 발생함
- `Set Initial Pose`가 클릭 불가처럼 보이거나, 눌러도 localization이 정상적으로 이어지지 않음
- `2D Goal Pose`를 줘도 Gazebo 로봇이 움직이지 않음

원인을 나눠서 확인해보니 크게 4가지였습니다.

- `navigation.launch.py`와 `localization.launch.py`가 같은 `use_rviz` launch 설정 이름을 공유하면서 상위 RViz까지 같이 꺼질 수 있던 구조
- `mapping.rviz` 안에서 `/initialpose`를 서로 다른 방식으로 쓰는 설정 충돌
- localization 시작 직후에는 아직 `map -> odom`이 없어서 RViz가 `map` 프레임을 바로 못 잡는 구간
- 이 머신에 남아 있던 다른 `gz sim server`와 현재 실행이 같은 Gazebo transport 공간을 공유하면서 `/clock`, `/odom`, `/tf` 시간이 섞이던 문제

즉, 이번 이슈는 단순 사용법 문제가 아니라 launch 구조, RViz 설정, Gazebo 실행 격리까지 함께 손봐야 재발을 줄일 수 있는 성격이었습니다.

---

## 주요 변경 사항

### 1. Navigation RViz 자동 실행 충돌 분리
- `agribot_ws/src/agribot_navigation/launch/navigation.launch.py`에서 navigation 쪽 RViz 조건과 localization include 인자를 분리했습니다.
- 기존에는 localization include에 넘긴 `use_rviz:=false`가 상위 navigation RViz 조건까지 덮어 써서, Gazebo만 뜨고 RViz가 안 뜰 수 있었습니다.
- 이 수정으로 `navigation.launch.py` 기준 Gazebo와 RViz가 함께 뜨는 기본 동작을 더 안정적으로 만들었습니다.

### 2. RViz 설정 충돌 제거 및 뷰 정리
- `agribot_ws/src/agribot_navigation/rviz/mapping.rviz`에서 `/initialpose`와 관련된 display/tool 충돌을 정리했습니다.
- `Set Initial Pose`가 클릭 불가처럼 보이던 직접 원인 중 하나를 제거했습니다.
- 기본 뷰는 맵 위에서 초기 자세와 목표점을 찍기 쉬운 `TopDownOrtho` 중심으로 정리했습니다.

### 3. 외장 GPU 우선 사용 환경 보강
- `navigation`, `localization`, `mapping`, `map_preview`, `spawn_agribot` 관련 launch에서 NVIDIA GPU가 있는 환경이면
  - `DRI_PRIME=1`
  - `__NV_PRIME_RENDER_OFFLOAD=1`
  - `__GLX_VENDOR_LIBRARY_NAME=nvidia`
  를 적용하도록 보강했습니다.
- 목표는 내장 그래픽으로만 실행되어 RViz/Gazebo 프레임이 떨어지는 상황을 줄이고, RTX 4070 laptop GPU를 우선 활용하게 만드는 것입니다.

### 4. startup 시 임시 `map -> odom` TF 추가
- `agribot_ws/src/agribot_navigation/agribot_navigation/startup_map_tf_broadcaster.py`를 새로 추가했습니다.
- 이 노드는 localization 시작 직후 AMCL이 아직 실제 `map -> odom`을 내놓기 전까지 identity transform을 임시 발행합니다.
- `agribot_ws/src/agribot_navigation/launch/localization.launch.py`에 이 노드를 연결했고,
  `agribot_ws/src/agribot_navigation/setup.py`에 console script도 등록했습니다.
- 덕분에 RViz에서 startup 직후 `map` 프레임이 완전히 비어 보여 `Fixed Frame [map] does not exist`가 반복되는 구간을 줄였습니다.

### 5. Gazebo 실행마다 독립 partition 사용
- `agribot_ws/src/agribot_description/launch/spawn_agribot.launch.py`에서 실행마다 고유한 `GZ_PARTITION`을 설정하도록 변경했습니다.
- 이 수정이 이번 MR의 핵심입니다.
- 예전에는 이 머신에 남아 있던 다른 `gz sim server`가 현재 launch와 같은 Gazebo transport를 공유해 `/clock`, `/odom`, `/tf`가 섞일 수 있었습니다.
- 실제 확인 결과 `/clock`은 20초대인데 `/odom`은 8000초대인 식으로 시간축이 깨졌고, 이 때문에 `TF_OLD_DATA`, `map frame does not exist`, 목표점 미동작이 연쇄적으로 발생했습니다.
- 이제는 launch마다 독립 partition을 사용하므로, 팀원이 이전 Gazebo 프로세스를 실수로 남겨 둔 상태에서도 현재 실행이 더 안전하게 격리됩니다.

### 6. 사용자 문서 보강
- `/home/ssafy/SSAFY/TIL/MR... 현 프로젝트 진행 상황.md`에 아래 내용을 보강했습니다.
  - `agribot_description`와 `agribot_navigation`를 함께 다시 build해야 한다는 점
  - `Global Status: Error`와 `Fixed Frame [map] does not exist`는 정상 상태가 아니라는 점
  - `Set Initial Pose`, `2D Goal Pose`는 `한 번 클릭`이 아니라 `클릭 후 드래그`로 방향까지 지정해야 한다는 점

---

## 검증 방법

아래 순서로 직접 문법 검사, 빌드, launch, 토픽/TF 확인을 진행했습니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash

python3 -m py_compile \
  src/agribot_description/launch/spawn_agribot.launch.py \
  src/agribot_navigation/launch/localization.launch.py \
  src/agribot_navigation/agribot_navigation/startup_map_tf_broadcaster.py \
  src/agribot_navigation/setup.py

colcon build --symlink-install --packages-select agribot_description agribot_navigation
source install/setup.bash

ros2 launch agribot_navigation navigation.launch.py
```

추가로 아래 명령들로 실제 상태를 점검했습니다.

```bash
ros2 node list
ros2 topic info /clock -v
ros2 topic info /tf -v
ros2 topic echo /clock --once
ros2 topic echo /odom --once
ros2 topic echo /tf --once
ros2 topic echo /map --once
ros2 run tf2_ros tf2_echo map odom
ros2 param get /startup_map_tf_broadcaster use_sim_time
ros2 param get /navigation_rviz use_sim_time
```

또한 실제로 `/initialpose`를 테스트 입력해 AMCL 로그까지 확인했습니다.

```bash
ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  '{header: {frame_id: map}, pose: {pose: {position: {x: 0.0, y: 0.0, z: 0.0}, orientation: {w: 1.0}}}}'
```

---

## 검증 결과

### 정상 확인

- `py_compile` 문법 검사 통과
- `agribot_description`, `agribot_navigation` 동시 빌드 통과
- 수정 후 `navigation.launch.py`에서 Gazebo와 RViz 프로세스가 함께 시작됨
- 이전처럼 `/clock`과 `/odom` 시간이 크게 어긋나는 현상이 재현되지 않음
- 새 launch에서 `/clock`과 `/odom`이 같은 시간축으로 정렬되는 것 확인
- `tf2_echo map odom` 기준 `map` 프레임이 형성되는 것 확인
- `/initialpose` 입력이 AMCL의 `initialPoseReceived` 로그까지 도달하는 것 확인

### 확인 로그 요약

- 문제 재현 시점
  - `/clock`은 약 `1489s`
  - `/odom`은 약 `8057s`
  - `TF_OLD_DATA` 반복
- 수정 후 재검증 시점
  - `/clock`은 약 `22.977s`
  - `/odom`은 약 `22.0s`
  - `/tf`의 `odom -> base_link`도 같은 시간축으로 발행

즉, 이번 MR은 "RViz 버튼 위치 안내" 수준이 아니라, Gazebo transport 혼선과 localization startup 타이밍 문제를 코드 레벨에서 줄여 실제 실행 흐름을 안정화한 작업입니다.

---

## 확인된 이슈 및 주의사항

### 1. `Set Initial Pose`와 `2D Goal Pose`는 드래그까지 해야 함
- 이번 턴에서 확인한 사용자 오해 포인트입니다.
- RViz에서 두 도구 모두 `한 번 클릭만` 하면 방향 정보가 충분히 안 들어갈 수 있습니다.
- 반드시 `클릭 후 드래그`로 화살표를 만들어 방향까지 지정해야 합니다.

### 2. AMCL pose 발행 타이밍은 실제 초기 자세와 맵 일치 여부에 영향받음
- `/initialpose`가 AMCL에 도달하는 것은 확인했습니다.
- 다만 잘못된 위치에 initial pose를 주면 `/amcl_pose`가 바로 안정적으로 잡히지 않을 수 있습니다.
- 따라서 사용자 테스트 시에는 실제 로봇이 있는 위치와 방향에 맞게 초기 자세를 찍는 것이 중요합니다.

### 3. 이번 MR은 startup 안정화가 중심
- RViz 자동 실행, `map` 프레임 startup, Gazebo partition 격리까지는 반영했습니다.
- 하지만 "아무 위치에 goal을 줘도 언제나 바로 주행"까지 보장하는 것은 아닙니다.
- 실제 goal 동작은 올바른 initial pose, 유효한 목표 위치, costmap 상 이동 가능 영역 조건을 만족해야 합니다.

---

## 기대 효과

- 팀원이 `test` 브랜치를 pull 받은 뒤 같은 build 명령만 실행해도 Gazebo/RViz/localization startup을 더 안정적으로 재현할 수 있습니다.
- 예전 Gazebo 프로세스가 남아 있더라도 현재 launch의 `/clock`, `/odom`, `/tf`가 섞일 가능성을 크게 줄였습니다.
- RViz에서 `map` 프레임이 비어 보이거나 `Set Initial Pose`가 막힌 것처럼 보이는 초반 혼란을 줄일 수 있습니다.
- 외장 GPU 우선 사용 환경까지 정리해, RTX 4070 laptop 환경에서 Gazebo/RViz 체감 성능도 더 안정적으로 가져갈 수 있습니다.

---

## 후속 작업 제안

- 실제 사용자 시나리오 기준으로 올바른 initial pose와 reachable goal을 잡아 end-to-end 자율주행 완료까지 다시 검증
- 필요하면 RViz 설정 파일에 사용하지 않는 display를 더 정리해 초보자용 화면을 단순화
- Gazebo GUI 쪽 `libEGL warning`은 현재 기능 차단 이슈는 아니지만, NVIDIA/PRIME 환경에서 추가 최적화 가능성 검토
- navigation 성공/실패 로그를 문서화해 팀원이 `plan`, `local_plan`, `amcl_pose`를 어디서 확인해야 하는지 가이드 보강

## 변경 파일

- agribot_ws/src/agribot_navigation/launch/navigation.launch.py
- agribot_ws/src/agribot_navigation/launch/localization.launch.py
- agribot_ws/src/agribot_navigation/launch/mapping.launch.py
- agribot_ws/src/agribot_navigation/launch/map_preview.launch.py
- agribot_ws/src/agribot_navigation/rviz/mapping.rviz
- agribot_ws/src/agribot_navigation/agribot_navigation/startup_map_tf_broadcaster.py
- agribot_ws/src/agribot_navigation/setup.py
- agribot_ws/src/agribot_description/launch/spawn_agribot.launch.py
- /home/ssafy/SSAFY/TIL/MR... 현 프로젝트 진행 상황.md

---

# S14P-40_RViz 목표 주행 속도 소폭 상향

## MR 제목

`[test] RViz 목표 주행 시 Nav2 선속도 값을 소폭 상향해 이동 응답성 개선`

---

## 브랜치/커밋 정보

- 작업 브랜치: `test`
- 커밋: `9daec83`

---

## 작업 배경

- RViz2에서 `Set Initial Pose`와 `2D Goal Pose`로 자율주행을 시작하면 경로 추종은 되지만, 직선 구간 체감 속도가 다소 느리게 느껴졌습니다.
- 현재 프로젝트에서는 Gazebo diff drive의 최대 선속도가 `0.40 m/s`로 설정되어 있지만, 실제 목표 주행 속도는 Nav2 `RegulatedPurePursuitController`의 `desired_linear_vel` 값 `0.28 m/s`가 먼저 제한하고 있었습니다.
- 이번 요청의 목적은 "로봇 속도를 조금만 올리기"였기 때문에, 물리 모델이나 여러 제어 파라미터를 크게 건드리지 않고 가장 먼저 속도를 제한하는 값만 최소 범위로 조정하는 방향을 선택했습니다.

---

## 이번 MR에서 변경한 내용

### 1. Nav2 목표 선속도 소폭 상향

- 수정 파일
  - `agribot_ws/src/agribot_navigation/config/nav2_params.yaml`
- 변경 내용
  - `desired_linear_vel: 0.28 -> 0.34`

즉, RViz2에서 목표 지점을 주었을 때 `controller_server`의 `FollowPath` 플러그인이 경로 추종 중 사용할 목표 선속도를 약간 높였습니다.

---

## 왜 이 방식으로 수정했는가

### 1. "조금 빠르게"라는 요구에 맞는 최소 변경

- `0.28 m/s`에서 `0.34 m/s`로만 올려 과도한 튜닝을 피했습니다.
- 약 21% 상향이지만 여전히 Gazebo diff drive 상한 `0.40 m/s` 아래라서, 물리 한계를 바로 넘지 않습니다.

### 2. 기존 주행 구조를 최대한 유지

- Gazebo 모델의 `max_linear_velocity`, `max_linear_acceleration`은 건드리지 않았습니다.
- 회전 속도, costmap, collision regulation, recovery behavior도 그대로 유지했습니다.
- 즉, 기존 코드와 주행 구조를 크게 바꾸지 않고도 체감 속도만 조금 개선하는 쪽에 집중했습니다.

### 3. 팀 협업 시 재현성이 좋음

- 팀원이 `test` 브랜치를 pull 받은 뒤 같은 launch 흐름으로 실행하면, 동일한 파라미터 값으로 같은 속도 상향 효과를 재현할 수 있습니다.
- 수정 범위가 작아, 다른 주행 이슈가 생겼을 때 원인 추적도 상대적으로 쉽습니다.

---

## 검증한 내용

### 1. 변경 범위 확인

- `git diff` 기준으로 실제 코드 변경은 `nav2_params.yaml` 한 줄만 수정된 것을 확인했습니다.
- `git diff --check`도 통과하여 공백/형식 문제 없이 정리된 상태임을 확인했습니다.

### 2. 파라미터 연결 경로 확인

- `agribot_navigation/launch/navigation.launch.py`에서 기본 Nav2 파라미터 파일로 `config/nav2_params.yaml`을 읽고 있는 것을 확인했습니다.
- 따라서 이번 수정은 navigation launch 재실행 시 그대로 반영됩니다.

### 3. 이번 턴에서 하지 않은 검증

- Gazebo/ROS2를 실제로 다시 띄워 end-to-end 주행 테스트까지는 수행하지 않았습니다.
- 즉, 이번 MR 문서는 "실제 적용한 변경"과 "정적 검토 결과" 중심으로 정리했습니다.

---

## 기대 효과

- RViz2에서 목적지를 설정했을 때 직선 구간 이동 속도가 이전보다 조금 더 빠르게 느껴집니다.
- Gazebo diff drive 상한은 그대로 두었기 때문에, 너무 공격적인 속도 상승 없이 비교적 안전한 범위에서 조정할 수 있습니다.
- 변경 지점이 명확해, 후속 튜닝이 필요할 때도 기준점으로 삼기 좋습니다.

---

## 주의사항

### 1. 항상 `0.34 m/s`로 달리는 것은 아님

- `RegulatedPurePursuitController`는 곡률, 장애물 비용, goal 접근 상황에 따라 속도를 자동으로 줄입니다.
- 따라서 좁은 통로나 급회전 구간에서는 이전처럼 감속이 발생할 수 있습니다.

### 2. 더 빠르게 만들고 싶으면 다음 단계가 필요

- 이후 체감 속도가 아직 부족하면, 그때는 Gazebo diff drive의 `max_linear_velocity`와 가속도 계수까지 함께 검토해야 합니다.
- 다만 이번 MR은 요청대로 "조금" 올리는 최소 변경만 반영했습니다.

---

## 변경 파일

- `agribot_ws/src/agribot_navigation/config/nav2_params.yaml`
