# 수확행

![메인 화면](./img/main.png)

스마트팜 관제 화면, FastAPI 서버, ROS2·Gazebo 로봇 시뮬레이션과 AI 진단 결과를 하나의 흐름으로 연결한 프로젝트입니다.

## 프로젝트 개요

| 항목 | 내용 |
| --- | --- |
| 기간 | 2026.02.09 - 2026.04.03 |
| 팀 구성 | 6인 |
| 개인 기여도 | 20% |
| 담당 | Backend · System Integration |

## 담당 역할

- FastAPI 기반 로봇·미션·추론·IoT API 구현
- React 관제 화면의 이동·정지·순찰·수확 미션 명령 연동
- FastAPI와 ROS2 사이의 명령·미션 브리지 및 Runtime File Fallback 구현
- REST API, ROS Topic·Action, MQTT와 JSON Runtime File의 통신 책임 분리 검증
- YOLOv8 확정 추론 결과를 Rule Engine의 IoT 처방 명령으로 연결

## 기술 스택

| 영역 | 기술 |
| --- | --- |
| Backend | Python, FastAPI, SQLAlchemy, PostgreSQL |
| Frontend | React, TypeScript, Vite, Zustand |
| Robotics | ROS2 Jazzy, Gazebo, Nav2 |
| AI | YOLOv8, PyTorch |
| Communication | REST API, ROS Topic·Action, MQTT, JSON Runtime File |

## 시스템 구조

![시스템 아키텍처](./img/System_Architecture.png)

1. React 관제 화면에서 로봇 이동, 정지, 순찰과 수확 미션을 요청합니다.
2. FastAPI가 요청을 검증하고 로봇 명령 및 미션 상태를 관리합니다.
3. 명령 브리지가 요청 종류에 따라 ROS2 런타임 또는 Runtime File Fallback으로 전달합니다.
4. ROS2·Gazebo 환경에서 Nav2가 이동 경로와 미션을 실행합니다.
5. YOLOv8 추론 결과를 서버에 저장하고, 확정된 병해 라벨을 Rule Engine의 처방 규칙과 연결합니다.
6. 생성된 처방 요청은 MQTT를 통해 IoT 장치 명령으로 전달됩니다.

모든 데이터를 하나의 통신 방식으로 처리하지 않고, 요청과 상태의 성격에 따라 통신 책임을 나눴습니다.

## 핵심 구현

### 1. 웹 명령과 ROS2 실행 경로 연결

관제 화면의 HTTP 요청을 ROS2 명령으로 바로 간주하면 웹 요청 상태와 실제 로봇 실행 상태가 섞일 수 있습니다. FastAPI가 명령을 접수하고 미션 상태를 관리하며, 브리지 계층이 ROS2 런타임에 전달하도록 역할을 나눴습니다.

- 이동·정지·순찰·수확 명령 API 구성
- 웹 요청 스키마와 ROS2 메시지 형식 사이 변환
- 로봇 명령과 미션 진행 상태를 별도로 관리
- ROS2 런타임을 사용할 수 없는 경우를 위한 Runtime File Fallback 유지

### 2. 통신 방식별 책임 분리

초기 구조에서 JSON 파일은 프로세스 사이 명령 전달과 상태 공유에 함께 사용됐습니다. 파일 폴링만으로 모든 흐름을 처리하지 않고 각 방식의 용도를 다음과 같이 구분했습니다.

| 방식 | 담당 범위 |
| --- | --- |
| REST API | 관제 화면의 명령 요청과 데이터 조회 |
| ROS Topic·Action | 로봇 주행 명령과 실행 상태 전달 |
| MQTT | 외부 관제 데이터와 IoT 장치 명령 연동 |
| JSON Runtime File | ROS2 런타임 연결이 어려운 상황의 제한적인 Fallback |

동일 조건으로 측정한 원본 결과가 없어 통신 지연은 정량적인 개선 수치로 표현하지 않았습니다.

### 3. AI 진단 결과와 처방 명령 연결

AI 추론 결과를 화면에 표시하는 데서 끝내지 않고 서버가 후속 처방 여부를 판단할 수 있도록 흐름을 연결했습니다.

- YOLOv8 추론 요청과 결과 저장 API 구현
- 추론 결과에서 확정된 병해 라벨과 신뢰도 저장
- 병해 라벨별 Rule Engine 정책 적용
- 정책 결과를 스프링클러 등 IoT 장치의 처방 요청으로 변환
- 처방 명령의 요청·전송 상태를 분리해 기록

### 4. 좁은 통로의 로봇 접근 경로 개선

농장 통로에서 작물 좌표로 바로 이동하면 울타리와 충돌하거나 경로가 과도하게 우회하는 문제가 있었습니다. 주행 목표를 한 번에 전달하지 않고 통로 진입점과 최종 관측 지점으로 나누는 방식을 적용했습니다.

1. 통로 중앙의 진입 지점으로 이동
2. 작물 앞 관측 지점으로 정밀 접근

이는 실제 농장 자율주행의 완료를 의미하지 않으며, ROS2·Gazebo 시뮬레이션에서 경로 제약을 확인한 결과입니다.

## 구현 범위와 검증 수준

- 관제 명령, ROS2 실행, AI 추론 결과 저장과 IoT 처방 요청이 연결되는 시뮬레이션 흐름을 구현했습니다.
- 실제 농장과 실제 로봇에서 장기간 운영한 결과는 아닙니다.
- 공개 저장소에 모델 평가 원본이 없어 정확도 수치를 기재하지 않았습니다.
- 동일 조건의 지연 시간 측정 자료가 없어 통신 성능을 정량적으로 비교하지 않았습니다.
- 실제 농장 운영 성과가 아니라 시뮬레이션에서 구현하고 확인한 연결 범위만 기록했습니다.

## 화면

### Gazebo 시뮬레이션

![Gazebo](./img/top.gif)

### 로봇 관제 화면

![관제 화면](./img/front.png)

### ERD

![ERD](./img/ERD.png)

## 디렉터리 구조

```text
.
├── backend/       # FastAPI API와 브리지 서비스
├── frontend/      # React 관제 화면
├── agribot_ws/    # ROS2 패키지와 Gazebo 시뮬레이션
├── artifacts/     # 모델·실행 결과 관리
├── scripts/       # 서비스 실행 및 점검 스크립트
└── TIL/           # 설계 문서와 실행 기록
```
