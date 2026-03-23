# HarvestEvent.msg
# 수확 시퀀스 결과 기록

std_msgs/Header header          # 이벤트 시각과 기준 frame_id
string event_id                 # 수확 이벤트 ID
string mission_id               # 연계된 미션 ID
string zone_id                  # 수확이 발생한 구역
string plant_id                 # 부모 식물 ID
string fruit_id                 # 수확 대상 과실 ID
bool success                    # 성공 여부
string failure_reason           # 실패 사유. 성공이면 빈 문자열
uint32 basket_count             # 현재 적재 바구니 수량
