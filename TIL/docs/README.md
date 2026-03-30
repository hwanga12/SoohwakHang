# Hardcoded Map Navigation Notes

## 목적

이 문서는 `farm_world.sdf` 기반 Gazebo 시뮬레이션에서
하드코딩된 정적 맵으로 Nav2 + patrol 자율주행을 다시 살린 과정과
현재 실행 방법을 정리한다.

## 내가 실제로 사용한 실행 순서

`simulation.launch.py` 하나로 Gazebo + RViz + bridge + Nav2 + patrol node가 같이 올라온다.

기존 프로세스가 꼬였을 때 먼저 정리:

```bash
pkill -f 'ros2 launch agribot_bringup simulation.launch.py|gz sim|rviz2|controller_server|planner_server|bt_navigator|patrol_node|startup_map_tf_broadcaster|cmd_vel_watchdog|odom_tf_broadcaster|ros_gz_|map_server|amcl|lifecycle_manager' || true
```

정적 맵 재생성부터 실행까지:

워크스페이스 루트에서:

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ssafy/Desktop/pjt/S14P21A602/agribot_ws
python3 src/agribot_navigation/agribot_navigation/generate_static_map.py \
  --output-prefix src/agribot_navigation/maps/farm_map \
  --boundary-yaml src/agribot_navigation/maps/farm_exploration_boundary.yaml
colcon build --packages-select agribot_description agribot_navigation agribot_bringup
source install/setup.bash
ros2 launch agribot_bringup simulation.launch.py
```

patrol 시작:

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ssafy/Desktop/pjt/S14P21A602/agribot_ws
source install/setup.bash
ros2 service call /patrol/start std_srvs/srv/Trigger "{}"
```

상태 확인:

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ssafy/Desktop/pjt/S14P21A602/agribot_ws
source install/setup.bash
ros2 topic echo /patrol/status
```

주행 로그 확인:

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ssafy/Desktop/pjt/S14P21A602/agribot_ws
source install/setup.bash
ros2 topic echo /rosout
```

## 현재 실행 명령어

자율주행 시작:

```bash
ros2 service call /patrol/start std_srvs/srv/Trigger "{}"
```

중지 / 재시작:

```bash
ros2 service call /patrol/stop std_srvs/srv/Trigger "{}"
ros2 service call /patrol/resume std_srvs/srv/Trigger "{}"
```

상태 확인:

```bash
ros2 topic echo /patrol/status
```

patrol 메타데이터 검증:

```bash
ros2 run agribot_navigation validate_patrol_waypoints
```

## 확인된 문제와 해결

아래 항목은 이번 하드코딩 맵 주행을 다시 살리는 동안 실제로 확인한 순서대로 정리했다.

### 1. 이전 Gazebo / Nav2 프로세스가 남아서 stale 상태로 다시 붙는 문제

- 증상: 새로 띄웠는데도 시뮬레이션 시간이 이어지거나 planner 상태가 이상하게 남음
- 대응: 기존 `gz sim`, `rviz2`, Nav2 관련 프로세스를 정리한 뒤 클린 런치로 재검증

### 2. `map -> odom` TF를 spawn 단계에서 고정으로 내보내던 문제

- 증상: 하드코딩 맵 정렬과 AMCL 정렬이 섞이면서 frame 해석이 꼬임
- 해결: `simulation.launch.py` 에서 spawn-time `map -> odom` static TF 비활성화
- 적용 파일: `src/agribot_bringup/launch/simulation.launch.py`

### 3. AMCL LiDAR 토픽이 실제 브리지 토픽과 달랐던 문제

- 증상: AMCL이 실제 스캔 대신 잘못된 토픽을 보고 있었음
- 해결: `scan_topic` 을 `/agribot/lidar` 로 수정
- 적용 파일: `src/agribot_navigation/config/amcl.yaml`

### 4. 하드코딩 patrol 웨이포인트가 `odom` 기준으로 작성돼 있던 문제

- 증상: 정적 맵 주행인데 waypoint frame이 런타임 localization frame과 맞지 않음
- 해결: `frame_id: map` 으로 수정
- 적용 파일:
  - `src/agribot_navigation/config/patrol_waypoints.yaml`
  - `src/agribot_navigation/config/nav2_params.yaml`
  - `src/agribot_navigation/behavior_trees/navigate_to_pose_w_backout_recovery.xml`

### 5. live LiDAR obstacle layer가 정적 맵과 미세하게 어긋나서 통로를 막던 문제

- 증상:
  - planner 에서 `no valid path found`
  - global obstacle layer가 실제로 비어 있는 중심 통로를 `255` 비용으로 마킹
  - RViz에서 검정 정적 맵과 live obstacle 십자/벽이 반대로 보이는 현상
- 원인 정리:
  - 정적 맵 자체는 정상
  - 문제는 hardcoded map 기준 주행에 live obstacle layer를 그대로 합치면서 생긴 misalignment
- 해결:
  - 하드코딩 맵 모드에서는 local/global `obstacle_layer.enabled=false`
  - 정적 맵 + inflation 기준으로 planner/controller가 동작하도록 고정
- 적용 파일: `src/agribot_navigation/config/nav2_params.yaml`

### 6. 외곽 통로 웨이포인트가 벽에 조금 타이트했던 문제

- 증상: 실제 주행은 되지만 외곽 벽 근처에서 박거나 질질 끄는 느낌이 남음
- 해결:
  - 외곽 lane x를 다시 `±9.0` 으로 되돌려 crop row 쪽 여유를 확보
  - 남북 connector y와 home pose y를 다시 `±9.0` 기준으로 맞춰 row end에서 더 떨어지게 조정
  - controller를 더 느린 속도, 짧은 lookahead, 작은 heading 오차에도 제자리 회전을 우선하는 값으로 재튜닝
  - `NavigateToPose` 재계획 주기를 낮춰 코너에서 goal 쪽으로 과하게 인코스로 감기지 않게 조정
- 적용 파일:
  - `src/agribot_navigation/config/patrol_waypoints.yaml`
  - `src/agribot_navigation/config/nav2_params.yaml`
  - `src/agribot_navigation/behavior_trees/navigate_to_pose_w_backout_recovery.xml`

### 7. simulation patrol node가 존재하지 않는 `/odometry/filtered` 를 보던 문제

- 증상:
  - patrol status는 살아 있는데 내부 robot pose 추적이 비어 있음
  - 실제 주행 중 soft-complete / already-reached 판단이 부정확해짐
- 원인:
  - 시뮬레이션에서는 `/odom` 만 bridge 되고 `/odometry/filtered` publisher가 없음
- 해결:
  - `navigation.launch.py` 에 `patrol_robot_pose_topic` launch argument 추가
  - `simulation.launch.py` 에서 patrol pose topic을 `/odom` 으로 override
- 적용 파일:
  - `src/agribot_navigation/launch/navigation.launch.py`
  - `src/agribot_bringup/launch/simulation.launch.py`

### 8. startup_map_tf_broadcaster 가 AMCL 시작 뒤에도 계속 콜백을 먹던 문제

- 증상:
  - `/amcl_pose` 수신 뒤에도 temp broadcaster 프로세스가 남아 불필요한 CPU/로그 부하를 유발
- 해결:
  - 첫 `/amcl_pose` 수신 후 타이머와 subscriptions 를 정리하도록 수정
- 적용 파일:
  - `src/agribot_navigation/agribot_navigation/startup_map_tf_broadcaster.py`

### 9. Gazebo/bridge/Nav2 동시 기동 시 localization lifecycle 이 startup timeout 으로 멎는 문제

- 증상:
  - `map_server change_state timeout`
  - `amcl` 이 configure/activate 되지 못하고 `planner_server` 가 `Robot is out of bounds of the costmap!` 를 반복
- 해결:
  - simulation launch 에서 navigation/localization bringup 을 5초 지연시켜 Gazebo/bridge 초기 부하를 먼저 안정화
- 적용 파일:
  - `src/agribot_bringup/launch/simulation.launch.py`

### 10. 제자리 회전 구간에서 차체가 살짝 뒤로 밀려 보이는 문제

- 증상:
  - Nav2 는 전진/제자리 회전만 주는데 Gazebo 에서는 차체가 순간적으로 뒤로 밀리는 것처럼 보임
  - `/cmd_vel` 은 음수가 아니어도 `/odom` 에서 짧은 음수 `linear.x` 가 관측됨
- 원인:
  - rotate-to-heading 보정이 다소 공격적이어서 정지 후 회전 전환이 급했고
  - Gazebo diff-drive 가속도/jerk 한계도 높아 물리적으로 출렁임이 커졌음
- 해결:
  - controller 목표 속도, 접근 속도, rotate-to-heading 속도/가속도, cancel deceleration 을 더 보수적으로 조정
  - Gazebo diff-drive plugin 의 linear/angular acceleration, jerk 한계를 낮춤
- 적용 파일:
  - `src/agribot_navigation/config/nav2_params.yaml`
  - `src/agribot_description/models/agribot/model.sdf`

## 현재 반영된 핵심 설정

- hardcoded map 주행에서 `map -> odom` 정렬은 AMCL이 담당
- AMCL scan topic은 `/agribot/lidar`
- patrol waypoint frame은 `map`
- hardcoded map 모드에서는 Nav2 obstacle layer 비활성화
- 외곽 lane / connector / home pose는 turn clearance 중심으로 보정

## 현재 하드코딩 농장 레이아웃

- crop row collision은 `x = -6, -2, 2, 6` 의 4열 대칭 배치
- 초록색 collision row 길이는 4열 모두 동일하게 `14.0 m`
- 꽃(토마토) 배치는 `y = -6, -4, -2, 2, 4, 6` 의 6개 높이에 맞춰 총 `24개`
- 스프링클러는 `(-6, 0)`, `(-2, 0)`, `(2, 0)`, `(6, 0)` 에 4개 대칭 배치
- harvest patrol은 4개 lane 기준으로 다시 작성되어 각 lane inspect pose가 현재 plant 배치와 1:1로 맞음

## 검증 포인트

- 런치 후 RViz에서 빨간 직사각형은 Nav2 footprint 표시이므로 정상
- `ros2 param get /global_costmap/global_costmap obstacle_layer.enabled` 결과가 `False` 여야 함
- `ros2 service call /patrol/start std_srvs/srv/Trigger "{}"` 후
  - `Begin navigating from current location ...`
  - `Passing new path to controller.`
  - `Reached the goal!`
  로그가 순서대로 보이면 정상
- 메타데이터/테스트 검증은 아래 명령으로 다시 확인 가능

```bash
ros2 run agribot_navigation validate_patrol_waypoints
python3 -m pytest \
  src/agribot_navigation/test/test_generate_static_map.py \
  src/agribot_navigation/test/test_harvest_routing.py \
  src/agribot_navigation/test/test_mapping_patrol_plan.py \
  src/agribot_navigation/test/test_patrol_batching.py
```

## 남은 known issue

- LiDAR obstacle layer와 hardcoded static map 사이의 정렬 오차 원인은 아직 근본적으로 분리하지 못했다.
- 그래서 현재 hardcoded map 주행 모드에서는 obstacle layer를 꺼 두는 것이 안전하다.
- 이후 live obstacle 회피까지 같이 쓰려면
  - LiDAR frame 해석
  - Gazebo sensor frame / TF 일관성
  - AMCL / map alignment
  를 다시 맞춘 뒤 obstacle layer를 재활성화해야 한다.
