# Mission State Diagram

`S14P-402` 기준선용 미션 상태머신 초안입니다.

```mermaid
stateDiagram-v2
    [*] --> IDLE

    IDLE --> PATROL: patrol_start
    IDLE --> OBSERVE: observe_start
    IDLE --> HARVEST: harvest_start
    IDLE --> RETURN_HOME: return_home
    IDLE --> IOT_ACTION: iot_action

    PATROL --> OBSERVE: detect_target
    PATROL --> HARVEST: harvest_start
    PATROL --> RETURN_HOME: return_home
    OBSERVE --> HARVEST: target_confirmed
    HARVEST --> RETURN_HOME: harvest_complete
    IOT_ACTION --> RETURN_HOME: actuation_complete

    PATROL --> STOPPED: pause
    OBSERVE --> STOPPED: pause
    HARVEST --> STOPPED: pause
    RETURN_HOME --> STOPPED: pause
    IOT_ACTION --> STOPPED: pause

    STOPPED --> PATROL: resume
    STOPPED --> OBSERVE: resume
    STOPPED --> HARVEST: resume
    STOPPED --> RETURN_HOME: resume
    STOPPED --> IOT_ACTION: resume

    PATROL --> ERROR: fail
    OBSERVE --> ERROR: fail
    HARVEST --> ERROR: fail
    RETURN_HOME --> ERROR: fail
    IOT_ACTION --> ERROR: fail

    PATROL --> IDLE: complete
    OBSERVE --> IDLE: complete
    HARVEST --> IDLE: complete
    RETURN_HOME --> IDLE: complete
    IOT_ACTION --> IDLE: complete

    ERROR --> IDLE: reset
    STOPPED --> IDLE: cancel
```

## 구현 메모

- 로봇 모드는 API 문서의 `robot.status` enum을 기준으로 맞춘다.
- 미션 상태는 API 문서의 `missions.status` enum을 기준으로 맞춘다.
- 실제 순찰/수확 액션 서버 연동은 `S14P-403`, `S14P-453` 이후에 붙인다.
- 현재는 `/mission/command`의 문자열 명령으로 상태 전이만 검증할 수 있게 둔다.
