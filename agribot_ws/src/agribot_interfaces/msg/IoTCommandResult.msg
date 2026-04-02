# IoTCommandResult.msg
# Structured IoT command execution result used across ROS, backend, and MQTT.

std_msgs/Header header
string command_id
string zone_id
string device_id
string device_type
string command_type
bool success
string state
float32 target_value
string unit
float32 planned_duration_sec
float32 executed_duration_sec
string detail_message
string requested_by
string treatment_type
string effect_color
string nutrient_type
float32 speed_level
float32 opening_ratio
float32 source_speed_level
float32 source_opening_ratio
