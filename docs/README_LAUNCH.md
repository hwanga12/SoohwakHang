# AgriBot ROS 2 Workspace & Launch Guide

이 문서는 AgriBot 워크스페이스의 폴더 구조와 각 런치파일의 역할을 설명합니다.

## 1. 폴더 구조 (Folder Roles)

| 폴더 | 역할 | 상세 설명 |
| :--- | :--- | :--- |
| **`agribot_bringup`** | **통합 실행 (Orchestration)** | 전체 시스템을 하나로 묶어 실행하는 최상위 패키지입니다. |
| **`agribot_description`** | **로봇 정의 (Identity)** | 로봇의 3D 모델(URDF), Gazebo 월드, 초기 스폰 로직을 포함합니다. |
| **`agribot_navigation`** | **이동 및 지도 (Movement)** | 내비게이션(Nav2), 지역화(AMCL), 지도 생성(SLAM) 설정을 포함합니다. |
| **`agribot_interfaces`** | **통신 정의 (Interfaces)** | 커스텀 메시지(msg)와 서비스(srv) 정의가 들어있습니다. |

---

## 2. 런치파일 사용 가이드 (Launch File Guide)

가장 자주 사용하게 될 키워드별 실행 명령어입니다.

| 기능 | 명령어 | 설명 |
| :--- | :--- | :--- |
| **전체 실행** | `ros2 launch agribot_bringup simulation.launch.py` | Gazebo 시뮬레이션 + 로봇 스폰 + 내비게이션 + RViz를 한 번에 실행합니다. |
| **지도 생성** | `ros2 launch agribot_navigation mapping.launch.py` | 새로운 지도를 만들기 위해 SLAM Toolbox를 함께 실행합니다. |
| **로봇만 소환** | `ros2 launch agribot_description spawn_agribot.launch.py` | 내비게이션 없이 시뮬레이션 환경에 로봇만 띄웁니다. |
| **지도 확인** | `ros2 launch agribot_navigation map_preview.launch.py` | 저장된 지도를 RViz로 미리 확인합니다. |

---

## 3. 구조적 특징 (Modular Design)

- **계층적 구조**: `simulation.launch.py`는 `spawn_agribot.launch.py`와 `navigation.launch.py`를 내부적으로 호출합니다. 
- **재사용성**: 각 기능이 독립된 패키지로 나뉘어 있어, 특정 기능(예: 내비게이션)만 따로 테스트하거나 수정하기 용이합니다.
- **표준 준수**: ROS 2의 표준 모듈화 방식을 따르고 있어 유지보수와 확장이 쉽습니다.
