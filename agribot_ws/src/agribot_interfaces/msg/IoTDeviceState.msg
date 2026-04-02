# IoTDeviceState.msg
# 주변 장치의 현재 상태 요약

std_msgs/Header header          # 상태 시각
string device_id                # 장치 ID
string zone_id                  # 장치가 속한 구역
string device_type              # 예: "watering", "nutrient", "sprinkler"
string state                    # 예: "OFF", "ON", "OPEN", "ERROR"
float32 opening_ratio           # 장치별 보조 상태값. 없으면 0.0
float32 speed_level             # 장치별 단계값. 없으면 0.0
float32 current_value           # 현재 측정/설정 값
string unit                     # current_value 단위
bool is_available               # 장치 사용 가능 여부
string detail_message           # 추가 상태 메시지
