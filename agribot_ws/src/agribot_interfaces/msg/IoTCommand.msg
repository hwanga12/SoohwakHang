# IoTCommand.msg
# IoT 기기 제어 명령

string device_id        # IoT 기기 ID
string command_type     # 명령 유형 (예: "set_humidity", "turn_on_light")
float32 target_value    # 목표 값
string unit             # 단위 (예: "%", "celsius", "lux")
