# CropStatus.msg
# 채소/작물의 상태 정보

string crop_name        # 작물 이름 (예: "tomato", "strawberry")
float32 health_score    # 건강도 (0.0 ~ 1.0)
float32 growth_stage    # 성장 단계 (0.0 ~ 1.0)
bool needs_water        # 물 필요 여부
bool ready_to_harvest   # 수확 가능 여부
geometry_msgs/Point position  # 작물 위치 (3D)
