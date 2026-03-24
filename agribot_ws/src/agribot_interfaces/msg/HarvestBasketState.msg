# HarvestBasketState.msg
# 현재 바구니 적재 상태와 누적 수확 요약

std_msgs/Header header          # 상태 시각과 기준 frame_id
string zone_id                  # 운영 구역 ID
uint32 basket_count             # 현재 바구니 적재 수량
uint32 harvested_count          # 누적 수확 개수
uint32 remaining_ready_count    # 아직 수확 가능한 ready fruit 개수
string last_event_id            # 마지막 성공 수확 이벤트 ID
string last_harvested_fruit_id  # 마지막으로 적재한 fruit ID
string[] loaded_fruit_ids       # 현재 바구니에 적재된 fruit ID 목록
