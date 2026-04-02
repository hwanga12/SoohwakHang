# RobotCommand.msg
# Structured robot command request published by the backend.

std_msgs/Header header
string command_id
string requested_command_type
string command_type
string robot_id
string requested_by
bool preempt_current_navigation
string map_id
string target_zone_id
string plant_id
string inspect_waypoint_id
string[] inspect_waypoint_ids
string home_waypoint_id
bool has_target_pose
TargetPose target_pose
ObservationGoalCandidate[] observation_candidates
