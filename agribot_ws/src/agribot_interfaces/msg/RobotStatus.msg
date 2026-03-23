# RobotStatus.msg
# 로봇 상태와 주행 상태의 요약

std_msgs/Header header          # 상태 시각과 기준 frame_id
string robot_id                 # 로봇 식별자
string zone_id                  # 현재 운영 구역
string mission_id               # 수행 중인 미션 ID. 없으면 빈 문자열
string mode                     # 예: "IDLE", "PATROL", "HARVEST"
string state                    # 예: "RUNNING", "PAUSED", "FAILED"
geometry_msgs/Pose pose         # 현재 pose
geometry_msgs/Vector3 linear_velocity   # 선속도
geometry_msgs/Vector3 angular_velocity  # 각속도
bool is_returning_home          # 홈 복귀 여부
bool has_error                  # 오류 상태 여부
string error_code               # 오류 코드. 없으면 빈 문자열
string error_message            # 오류 설명. 없으면 빈 문자열
