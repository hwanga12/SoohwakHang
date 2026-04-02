# MissionRequest.msg
# Structured mission request published by the backend.

std_msgs/Header header
string command_id
string mission_id
string request_type
string robot_id
string requested_by
string[] zone_ids
uint32 loop_count
string patrol_mode
string plant_id
string fruit_id
string tomato_id
string inspect_waypoint_id
string[] inspect_waypoint_ids
