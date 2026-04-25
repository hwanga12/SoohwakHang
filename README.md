# 🌱 수확행

![main](./img/main.png "메인")

![gazebo](./img/top.gif "가제보 진단하기")

**스마트 농장 무인 관제 및 AI 진단 로봇 시뮬레이션 시스템**

---

## 1. 프로젝트 개요

- **기간**: 2026.02.09 – 2026.04.03 (6인)
- **유형**: Web · AI · ROS2 · IoT 풀체인 통합 시뮬레이션
- **목표**: 스마트팜의 완전 무인화를 위한 로봇–서버–IoT 오케스트레이션 구현

### 핵심 키워드

- 하이브리드 통신 아키텍처 (HTTP / ROS Topic / MQTT / JSON)
- 엣지–클라우드 2단 AI 진단 파이프라인 (YOLOv8)
- ROS2 & Gazebo 기반 자율주행
- 명령 유실 방지 및 상태 동기화 설계

---

## 2. 역할

### 황가연 Fullstack, ROS  (기여도 30%)

- Web(React/FastAPI) ↔ ROS2 이기종 통신 브리지 설계
- Nav2 자율주행 파라미터 튜닝 및 TF 트러블슈팅
- AI 확정 추론 + Rule Engine 기반 IoT 자동 제어
- FastAPI 기반 백엔드 구축

---

## 3. 기획 의도

기존 스마트팜은 좁은 통로 구조로 인해 대형 장비 운용이 어려움
이에 따라 본 프로젝트는 **작고 민첩한 로봇이 '진단'을 담당하고, 물리적 조치는 IoT가 수행하는 구조**를 설계

> 로봇 = 두뇌 (진단)
> IoT = 손발 (실행)

**무인 스마트 농장 운영 시스템**

---

## 4. 서비스 시나리오 (Full-Chain)

1. **자율주행**

   - 로봇이 지정된 작물 위치로 이동
2. **엣지 AI (1차 추론)**

   - 작물 탐지 및 의심 영역 Crop 후 서버 전송
3. **클라우드 AI (2차 추론)**

   - 병해 및 숙도 최종 판별
   - DB 저장
4. **자동 처방 (Rule Engine)**

   - 병해 발생 시 IoT 스프링클러 자동 작동
5. **외부 관제**

   - MQTT 기반 실시간 상태 모니터링

---

## 5. 주요 기능

### 웹 기반 관제 (React + FastAPI)

- 2D 맵 기반 로봇 위치 시각화
- 클릭 기반 목적지 전송 (Waypoint)
- 비동기 Polling 기반 상태 추적

---

### 자율주행 (ROS2 Nav2)

- IMU + LiDAR 센서 융합
- 작업 통로 기반 충돌 회피 로직
- 실환경 반영 경로 계획

---

### AI 진단 시스템 (YOLOv8)

#### 병해 탐지

- YOLOv8 Nano (5.4MB)
- 5종 질병 탐지
- mAP50: 0.96

#### 숙도 분류

- YOLOv8 Classification 모델
- Class imbalance 해결

---

### IoT 자동 제어

- Rule Engine 기반 의사결정
- ROS Topic 직접 발행 (지연 최소화)
- MQTT 기반 외부 시스템 연동

---

## 6. 기술 스택

| 영역          | 기술                                    |
| ------------- | --------------------------------------- |
| Backend       | Python, FastAPI, SQLAlchemy, PostgreSQL |
| Frontend      | React, TypeScript, Vite, Zustand        |
| Robotics      | ROS2 (Jazzy), Gazebo                    |
| AI            | YOLOv8, PyTorch                         |
| Communication | REST API, ROS Topic, MQTT, JSON         |

---

## 7. 기능 화면

## System Architecture

![system-architecture](./img/System_Architecture.png)

## FRONT

![gazebo](./img/gazebo.png "gazebo")

![front](./img/front.png "front")

## ERD

![ERD](./img/ERD.png)

---

## 8. 핵심 트러블슈팅

### 1. Polling 구조의 한계 → MQTT 리팩토링

**문제**

- JSON 파일 기반 Polling → 1~2초 지연 발생

**해결**

- MQTT Pub/Sub 구조로 전환
- QoS 기반 신뢰성 확보

**결과**

- 지연 → ms 단위 감소
- 확장성 확보

---

### 2. 도메인 갭 문제 (시뮬레이터 vs 실제 이미지)

**문제**

- Gazebo 3D 모델 → 실제 병해 인식 불가

**해결**

- 실제 이미지 직접 주입 (Thin Client 전략)

**결과**

- Full-Chain 파이프라인 검증 성공

---

### 3. TF 트리 붕괴

**문제**

- 위치 튐 / 자율주행 실패

**해결**

- TF 복구 (odom ↔ base_link)
- 시뮬레이션 시간 통일

---

### 4. 비효율 경로 문제

**문제**

- 직진 주행 → 충돌 / 우회 과다

**해결**

- 2단계 경로 계획 도입

#### 2-Step Path Planning

1. 통로 중앙 진입
2. 작물 앞 정밀 접근

- 도착 허용 반경 (55cm) 적용

---

## 8. 프로젝트 성과

### 하이브리드 통신 아키텍처 완성

- JSON / MQTT / ROS Topic 역할 분리
- 시스템 안정성 및 확장성 확보

### 실무형 자율주행 구현

- 물리적 환경 제약 반영
- 자연스러운 경로 생성

### Full-Chain 검증 성공

- 주행 → AI → DB → IoT 자동 제어 완성

---

## 9. 한 줄 요약

> **"로봇이 판단하고, IoT가 실행하는 완전 무인 스마트팜 오케스트레이션"**
