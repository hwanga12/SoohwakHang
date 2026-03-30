Saved farm and greenhouse maps live in this directory.

Generate the committed hardcoded farm map that matches
`agribot_description/worlds/farm_world.sdf`:

```bash
ros2 run agribot_navigation generate_static_map
```

Preview the saved map in RViz without Gazebo:

```bash
ros2 launch agribot_navigation map_preview.launch.py
```

Run Gazebo with the saved map and AMCL localization:

```bash
ros2 launch agribot_navigation localization.launch.py
```

After RViz opens, use the `2D Pose Estimate` tool to publish `/initialpose`.

Run the full Nav2 stack on top of the saved map and AMCL localization:

```bash
ros2 launch agribot_navigation navigation.launch.py
```

After RViz opens for navigation:

- use `2D Pose Estimate` once to initialize AMCL
- use `2D Goal Pose` to request a goal in the greenhouse aisle
- confirm `/plan` and `/local_plan` update while the robot follows the route
- keep the idle `patrol_node` running so patrol services are available

Validate the committed patrol coordinate file for `S14P-205`:

```bash
ros2 run agribot_navigation validate_patrol_waypoints
```

The default row-level patrol metadata lives at
`agribot_navigation/config/patrol_waypoints.yaml`.

Start, stop, and resume the `S14P-206` patrol sequence with:

```bash
ros2 service call /patrol/start std_srvs/srv/Trigger "{}"
ros2 service call /patrol/stop std_srvs/srv/Trigger "{}"
ros2 service call /patrol/resume std_srvs/srv/Trigger "{}"
```

Watch the patrol state machine over the published status topic:

```bash
ros2 topic echo /patrol/status
```

If you regenerate the map from a live SLAM session later, save it with:

```bash
ros2 run nav2_map_server map_saver_cli -f \
  /home/ssafy/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/maps/greenhouse_map
```
