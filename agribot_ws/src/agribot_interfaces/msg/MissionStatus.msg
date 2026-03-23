# MissionStatus.msg
# 장시간 미션의 상태 요약

std_msgs/Header header          # 상태 시각
string mission_id               # 미션 ID
string mission_type             # 예: "PATROL", "HARVEST", "RETURN_HOME"
string state                    # 예: "PENDING", "RUNNING", "PAUSED"
string current_phase            # 예: "APPROACH", "OBSERVE", "DOCK"
string zone_id                  # 대상 구역
string target_id                # fruit_id, waypoint_id 등 현재 타깃 식별자
float32 progress_pct            # 0.0 ~ 100.0
uint32 retry_count              # 재시도 횟수
string detail_message           # 사용자 표시용 상세 메시지
