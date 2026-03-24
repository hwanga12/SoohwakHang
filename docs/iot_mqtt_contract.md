# AgriBot IoT MQTT Contract

## Scope

This document covers the minimum contract added for:

- `S14P-501` IoT device and zone mapping
- `S14P-502` simulated environment sensor publishing
- `S14P-503` MQTT topic and payload agreement
- `S14P-504` watering controller execution
- `S14P-505` curtain controller execution
- `S14P-506` fan controller execution

## Shared Device Mapping

The source of truth for zone and device naming is:

- `agribot_ws/src/agribot_iot/config/iot_devices.yaml`

Current canonical IDs:

- Zone: `farm_01`
- Watering: `farm_01_watering`
- Curtain: `farm_01_curtain`
- Fan: `farm_01_fan`
- Nutrient: `farm_01_nutrient`

## ROS Topics

- `/environment_data`
  - type: `agribot_interfaces/msg/EnvironmentData`
  - publisher: `environment_sensor_node`
- `/iot/commands/manual`
  - type: `agribot_interfaces/msg/IoTCommand`
  - source: MQTT bridge inbound command topic
- `/iot/commands/dispatch`
  - type: `agribot_interfaces/msg/IoTCommand`
  - source: control arbitration
- `/iot/device_state`
  - type: `agribot_interfaces/msg/IoTDeviceState`
  - publisher: IoT controller nodes
- `/iot/command_result`
  - type: `std_msgs/msg/String`
  - payload: JSON execution result

## MQTT Topics

- `agribot/environment/{zone_id}`
  - direction: ROS -> MQTT
  - payload fields:
    - `zone_id`
    - `temperature`
    - `humidity`
    - `soil_moisture`
    - `light_level`
    - `co2_level`
- `agribot/iot/device_state`
  - direction: ROS -> MQTT
  - payload fields:
    - `device_id`
    - `zone_id`
    - `device_type`
    - `state`
    - `opening_ratio`
    - `speed_level`
    - `current_value`
    - `unit`
    - `is_available`
    - `detail_message`
- `agribot/iot/command_result`
  - direction: ROS -> MQTT
  - payload fields:
    - `command_id`
    - `zone_id`
    - `device_id`
    - `device_type`
    - `command_type`
    - `success`
    - `state`
    - `target_value`
    - `unit`
    - `planned_duration_sec`
    - `executed_duration_sec`
    - `detail_message`
- `agribot/commands/actuation`
  - direction: MQTT -> ROS
  - forwarded ROS topic: `/iot/commands/manual`
  - payload fields:
    - `command_id`
    - `zone_id`
    - `device_id`
    - `device_type`
    - `command_type`
    - `target_value`
    - `unit`
    - `requires_approval`
    - `auto_execute`
    - `requested_by`
    - `reason`

## Notes

- The current MQTT bridge supports a log-only fallback when `paho-mqtt` is not installed.
- The watering controller currently handles:
  - `dispense_water`
  - `stop_watering`
  - `hold_watering`
- The curtain controller currently handles:
  - `open_curtain`
  - `close_curtain`
  - `set_curtain_position`
- `set_curtain_position` accepts `percent_open`, `percent`, and `percent_closed`.
- The fan controller currently handles:
  - `turn_on_fan`
  - `turn_off_fan`
  - `set_fan_level`
  - `set_fan_speed`
- Fan state uses `speed_level` for the current stage and `current_value` with `unit=sec` for run time.
- Curtain, fan, and nutrient controllers follow the same `IoTCommand` -> `IoTDeviceState` -> JSON result pattern.
