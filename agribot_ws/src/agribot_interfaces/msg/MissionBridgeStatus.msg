# MissionBridgeStatus.msg
# Structured mission bridge status mirrored by the ROS executor.

std_msgs/Header header
string mission_id
string command_id
string request_type
string robot_id
string requested_by
string status
string message
string error
string result
string[] zone_ids
bool has_loop_count
uint32 loop_count
string patrol_mode
string plant_id
string fruit_id
string tomato_id
string inspect_waypoint_id
string[] inspect_waypoint_ids
string received_at
string started_at
string completed_at
string updated_at
