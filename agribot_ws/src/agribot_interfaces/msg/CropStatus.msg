# CropStatus.msg
# 개별 식물/토마토 과실 상태 정보

std_msgs/Header header  # 측정 시각과 frame_id
string crop_id          # 상태 대상의 canonical ID
string zone_id          # 운영 구역 ID (예: "greenhouse_01")
string plant_id         # 부모 식물 ID. 식물 상태 메시지면 crop_id와 동일
string tomato_id        # 토마토 과실 ID. 식물 상태 메시지면 빈 문자열
string source_model_name  # Gazebo world include name
string crop_name        # 작물 이름 (예: "tomato")
string crop_type        # "plant" 또는 "tomato_fruit"
float32 health_score    # 건강도 (0.0 ~ 1.0)
float32 growth_stage    # 성장 단계 (0.0 ~ 1.0)
bool needs_water        # 물 필요 여부
bool ready_to_harvest   # 수확 가능 여부
geometry_msgs/Point position  # 작물 위치 (3D)
