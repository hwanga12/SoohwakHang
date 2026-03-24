# PlantObservation.msg
# 작물 관측 결과의 구조화 이벤트

std_msgs/Header header          # 관측 시각과 frame_id
string observation_id           # 관측 이벤트 ID
string mission_id               # 연계된 미션 ID. 없으면 빈 문자열
string zone_id                  # 운영 구역 ID
string plant_id                 # 관측한 식물 ID
string fruit_id                 # 특정 과실 관측이면 fruit ID, 아니면 빈 문자열
string class_name               # 예: "ripe_tomato", "diseased_leaf"
float32 confidence              # 분류/탐지 confidence
float32 health_score            # 건강도 추정치
bool needs_water                # 급수 필요 여부
bool ready_to_harvest           # 수확 가능 여부
string growth_stage             # 성장 단계. 없으면 빈 문자열
geometry_msgs/Pose pose         # 관측 대상의 3D pose
string image_path               # 저장된 스냅샷 경로. 없으면 빈 문자열
