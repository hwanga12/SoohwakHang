Saved greenhouse maps live in this directory.

Generate the committed baseline map from the shared greenhouse metadata:

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

If you regenerate the map from a live SLAM session later, save it with:

```bash
ros2 run nav2_map_server map_saver_cli -f \
  /home/ssafy/SSAFY/S14P21A602/agribot_ws/src/agribot_navigation/maps/greenhouse_map
```
