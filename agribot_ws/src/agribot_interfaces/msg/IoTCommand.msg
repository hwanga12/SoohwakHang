# IoTCommand.msg
# IoT 기기 제어 명령

std_msgs/Header header  # 발행 시각과 frame_id
string command_id       # 명령 ID
string zone_id          # 대상 구역 ID
string device_id        # IoT 기기 ID
string device_type      # 장치 종류 (예: "watering", "fan")
string command_type     # 명령 유형 (예: "set_humidity", "open_curtain")
float32 target_value    # 목표 값
string unit             # 단위 (예: "%", "celsius", "lux")
bool requires_approval  # 승인 필요 여부
bool auto_execute       # 자동 즉시 실행 여부
string requested_by     # 명령 발행 주체
string reason           # 명령 사유
