• 결론부터 말하면, 가제보 실행 코드도 있고, 지도 기능도 있고, 자율주행 코드도 있습니다.
  다만 상태는 "목표점 자율주행과 기본 순찰까지는 연결되어 있음"이고,
  "17개 순찰 지점을 끝까지 항상 안정적으로 완주한다까지 완전히 증명된 상태"로 보긴 아직 이릅니다.
  제가 방금 이 환경에서 `validate_patrol_waypoints`를 직접 돌려보니
  `greenhouse_01`, `15 waypoints`, `2 routes`, `17 sequence entries`는 정상 로드됐습니다.

어떤 코드가 뭐 하는지

- 가제보를 실제로 띄우는 메인 코드는 `S14P21A602/agribot_ws/src/agribot_description/launch/spawn_agribot.launch.py:20`입니다.
  여기서 Gazebo를 켜고, `/odom`, `/agribot/lidar/scan`, 카메라, `/cmd_vel_safe` 브리지를 연결합니다.
- 실시간으로 맵을 그리는 코드는 `S14P21A602/agribot_ws/src/agribot_navigation/launch/mapping.launch.py:12`입니다.
  이 파일이 `spawn_agribot.launch.py`를 포함하고 `slam_toolbox`를 같이 띄웁니다.
- 저장된 맵으로 현재 위치를 잡는 코드는 `S14P21A602/agribot_ws/src/agribot_navigation/launch/localization.launch.py:12`입니다.
  `map_server + AMCL + RViz`를 띄웁니다.
- 자율주행 전체는 `S14P21A602/agribot_ws/src/agribot_navigation/launch/navigation.launch.py:12`입니다.
  여기서 localization 위에 Nav2 planner/controller를 올리고,
  순찰 노드 `S14P21A602/agribot_ws/src/agribot_navigation/agribot_navigation/patrol_node.py:24`도 같이 붙습니다.
- 맵만 따로 확인하는 가장 쉬운 코드는 `S14P21A602/agribot_ws/src/agribot_navigation/launch/map_preview.launch.py:11`입니다.
  이건 Gazebo 없이 저장된 맵만 RViz에 띄웁니다.

자율주행이 되는 방식은 간단히 말하면 이 흐름입니다.
Gazebo에서 라이다와 오도메트리가 나오고, 그걸 바탕으로 SLAM 또는 AMCL이 로봇 위치를 잡고, Nav2가 길을 만들고, controller가 속도 명령을 보내서 로봇이 움직입니다.
planner/controller 설정은 `S14P21A602/agribot_ws/src/agribot_navigation/config/nav2_params.yaml:20`에 있고,
현재 `SmacPlanner2D`와 `RegulatedPurePursuitController`를 쓰도록 되어 있습니다.

중요한 점이 하나 있습니다.
현재 저장소에 들어 있는 기본 맵은 "실시간 SLAM으로 방금 그린 결과"라기보다,
`S14P21A602/agribot_ws/src/agribot_navigation/agribot_navigation/generate_static_map.py:18`로
`zones.yaml`과 작물 메타데이터를 이용해 재현 가능한 baseline map입니다.
그래도 실시간 SLAM 기능 자체는 `S14P21A602/agribot_ws/src/agribot_navigation/launch/mapping.launch.py:83`에 따로 있습니다.

초보자용 확인 순서

터미널 번호를 헷갈리지 않도록 아래에서는 이렇게 부르겠습니다.

- 터미널 1: 메인 launch를 띄워두는 창
- 터미널 2: 추가 제어 명령을 넣는 창
- 터미널 3: 상태 확인이나 맵 저장 같은 보조 명령을 넣는 창

2번, 3번은 각각 단독 확인용이라 동시에 띄울 필요는 없습니다.
2번을 보고 바로 3번을 할 때는 터미널 1에서 `Ctrl+C`로 기존 launch를 종료한 뒤, 같은 터미널 1을 다시 써도 됩니다.

1. 먼저 공통 준비를 합니다.

터미널 1에서 먼저 실행:

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
```

이후 2번, 3번처럼 단독 확인을 할 때는 이 터미널 1을 계속 재사용하면 됩니다.

2. 제일 쉬운 확인은 "저장된 맵만 보기"입니다.

터미널 1에서 실행:

```bash
ros2 launch agribot_navigation map_preview.launch.py
```

이렇게 하면 RViz에 맵만 뜹니다. 파일 자체는 `S14P21A602/agribot_ws/src/agribot_navigation/maps/greenhouse_map.pgm`와
`S14P21A602/agribot_ws/src/agribot_navigation/maps/greenhouse_map.yaml:1`입니다.
가장 부담 없는 확인 방법입니다.

3. "목표점 자율주행"을 보고 싶으면 이걸 실행하세요.

터미널 1에서 실행:

```bash
ros2 launch agribot_navigation navigation.launch.py
```

이 명령은 **Gazebo가 같이 뜨는 것이 정상**입니다.
`navigation.launch.py`가 내부적으로 localization을 포함하고 있고, 그 localization이 Gazebo 시뮬레이터를 같이 띄우는 구조이기 때문입니다.

정상이라면 Gazebo와 함께 RViz도 같이 떠야 합니다.
최신 수정 기준으로는 `navigation.launch.py` 안에서 localization 쪽 RViz 설정과 navigation 쪽 RViz 설정이 서로 충돌하지 않도록 고쳐둔 상태라, 팀원이 최신 코드를 pull 받고 `agribot_description`와 `agribot_navigation` 패키지를 다시 build했다면 Gazebo와 RViz가 같이 떠야 맞습니다.
만약 여전히 Gazebo만 뜬다면, 예전 build 결과를 쓰고 있을 수 있으니 아래를 한 번 다시 실행한 뒤 재시작하세요.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select agribot_description agribot_navigation
source install/setup.bash
```

`Global Status: Error` 또는 `Fixed Frame [map] does not exist`가 뜨는 것은 정상 상태가 아닙니다.
예전에는 백그라운드에 남아 있던 다른 `gz sim server`와 토픽이 섞이면 `/clock`, `/odom`, `/tf` 시간이 꼬여서 이런 증상이 날 수 있었는데,
최신 코드에서는 Gazebo partition을 실행마다 분리하고, AMCL이 초기화되기 전까지 임시 `map -> odom` TF를 보내도록 수정해 두었습니다.
따라서 팀원이 최신 코드를 pull 받은 뒤 위 build를 다시 하면, 같은 증상을 훨씬 안정적으로 피할 수 있습니다.

만약 Gazebo만 뜨고 RViz 창이 안 보이면, RViz가 뒤로 숨어 있거나 자동 실행에 실패한 경우일 수 있으니 새 터미널 2에서 아래처럼 RViz를 직접 실행하세요.

터미널 2:

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
rviz2 -d ~/SSAFY/S14P21A602/agribot_ws/install/agribot_navigation/share/agribot_navigation/rviz/mapping.rviz
```

RViz가 열리면:

- 왼쪽 또는 상단 도구에서 `Set Initial Pose`를 누릅니다.
  (`2D Pose Estimate`와 같은 역할인데, RViz에서는 `Set Initial Pose`로 보일 수 있습니다.)
- 맵 위에서 "로봇이 지금 있는 곳"을 클릭한 뒤, 마우스를 끌어서 로봇이 보는 방향을 맞춥니다.
- `한 번만 클릭`하면 pose가 제대로 안 들어갈 수 있으니, 반드시 `클릭 후 드래그`로 방향 화살표까지 만들어야 합니다.
- 그 다음 `2D Goal Pose`를 누르고, 가고 싶은 위치를 클릭해서 방향까지 끌어줍니다.
- 목표점도 마찬가지로 `클릭 후 드래그`까지 해야 goal이 제대로 들어갑니다.
- 잘 되면 로봇이 움직이고, RViz에 빨간 `/plan`, 파란 `/local_plan` 선이 보입니다.
RViz 설정은 `S14P21A602/agribot_ws/src/agribot_navigation/rviz/mapping.rviz:51` 쪽에 이미 잡혀 있습니다.

4. "자동 순찰"은 navigation을 켠 상태에서 별도 터미널로 시작합니다.

여기서는 `3번`의 `navigation.launch.py`가 이미 터미널 1에서 실행 중이라고 가정하면 됩니다.
추천 방식은 터미널을 나눠 쓰는 것입니다.

터미널 2:

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 service call /patrol/start std_srvs/srv/Trigger "{}"
```

터미널 3:

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 topic echo /patrol/status
```

아래 기존 예시는 한 터미널에 순서대로 적어둔 것이고, 실제로는 `ros2 topic echo /patrol/status`가 계속 점유하므로 위처럼 터미널 2와 3으로 나눠 쓰는 편이 더 편합니다.

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash

ros2 service call /patrol/start std_srvs/srv/Trigger "{}"
ros2 topic echo /patrol/status
```

멈추려면 stop, 다시 하려면 resume입니다.

정지/재개 명령은 터미널 2에서 실행하세요. 터미널 3이 `ros2 topic echo /patrol/status`를 보고 있어도 그대로 두면 됩니다.

```bash
ros2 service call /patrol/stop std_srvs/srv/Trigger "{}"
ros2 service call /patrol/resume std_srvs/srv/Trigger "{}"
```

다만 이 순찰은 "코드와 서비스는 연결되어 있음" 수준이고, 저장소 문서상 17개 waypoint 전체 완주 end-to-end 검증은 아직 별도 확인이 더 필요합니다.

5. "실시간으로 진짜 맵 그리는 것"을 보려면 SLAM을 실행해야 합니다.

터미널 1:

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch agribot_navigation mapping.launch.py
```

터미널 2:

```bash
cd ~/SSAFY/S14P21A602/agribot_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r cmd_vel:=/cmd_vel
```

참고로 키보드 조종 코드는 저장소 안에 있는 게 아니라, 문서 기준 `teleop_twist_keyboard` ROS 패키지를 쓰는 방식입니다.
이 상태에서 로봇을 돌아다니게 하면 RViz의 `/map`이 점점 채워집니다. 다 그렸으면 저장:

터미널 3 (새 터미널):

```bash
ros2 run nav2_map_server map_saver_cli -f ~/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/maps/greenhouse_map
```

그 다음 다시 `map_preview.launch.py`로 저장된 맵을 확인하면 됩니다.

가장 쉬운 확인 루트만 한 줄로 줄이면 이겁니다.
`map_preview.launch.py`로 맵 보기, `navigation.launch.py`로 목표점 자율주행 보기, `mapping.launch.py`로 실시간 맵 그리기 보기.
