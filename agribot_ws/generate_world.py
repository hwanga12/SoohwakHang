import sys

x_centers = [-8.0, -6.0, -4.0, -2.0, 2.0, 4.0, 6.0, 8.0]
y_tomatoes = [-8.0, -6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0, 8.0]

world = """<?xml version="1.0" ?>
<sdf version="1.9">
  <world name="farm_world">
    <physics name="1ms" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>

    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.8 0.8 0.8 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <direction>-0.5 0.1 -0.9</direction>
    </light>

    <model name="ground_plane">
      <pose>0 0 0 0 0 0</pose>
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry><plane><normal>0 0 1</normal><size>20 20</size></plane></geometry>
        </collision>
        <visual name="visual">
          <geometry><plane><normal>0 0 1</normal><size>20 20</size></plane></geometry>
          <material><ambient>0.4 0.3 0.2 1</ambient><diffuse>0.5 0.4 0.3 1</diffuse></material>
        </visual>
      </link>
    </model>

    <!-- Invisible boundary walls -> Outer 20x20m mapped border -->
    <model name="invisible_boundaries">
      <static>true</static>
      <link name="link">
        <collision name="north_wall"><pose>0 10 0.5 0 0 0</pose><geometry><box><size>20 0.5 1</size></box></geometry></collision>
        <visual name="north_v"><pose>0 10 0.5 0 0 0</pose><geometry><box><size>20 0.5 1</size></box></geometry><material><ambient>1 0 0 1</ambient><diffuse>1 0 0 1</diffuse></material><transparency>0.8</transparency><cast_shadows>false</cast_shadows></visual>
        
        <collision name="south_wall"><pose>0 -10 0.5 0 0 0</pose><geometry><box><size>20 0.5 1</size></box></geometry></collision>
        <visual name="south_v"><pose>0 -10 0.5 0 0 0</pose><geometry><box><size>20 0.5 1</size></box></geometry><material><ambient>1 0 0 1</ambient><diffuse>1 0 0 1</diffuse></material><transparency>0.8</transparency><cast_shadows>false</cast_shadows></visual>
        
        <collision name="east_wall"><pose>10 0 0.5 0 0 0</pose><geometry><box><size>0.5 20 1</size></box></geometry></collision>
        <visual name="east_v"><pose>10 0 0.5 0 0 0</pose><geometry><box><size>0.5 20 1</size></box></geometry><material><ambient>1 0 0 1</ambient><diffuse>1 0 0 1</diffuse></material><transparency>0.8</transparency><cast_shadows>false</cast_shadows></visual>
        
        <collision name="west_wall"><pose>-10 0 0.5 0 0 0</pose><geometry><box><size>0.5 20 1</size></box></geometry></collision>
        <visual name="west_v"><pose>-10 0 0.5 0 0 0</pose><geometry><box><size>0.5 20 1</size></box></geometry><material><ambient>1 0 0 1</ambient><diffuse>1 0 0 1</diffuse></material><transparency>0.8</transparency><cast_shadows>false</cast_shadows></visual>
      </link>
    </model>

    <!-- 8 Crop row impassable boundaries (width 0.5m, length 16m) -->
    <model name="crop_rows">
      <static>true</static>
      <link name="link">
"""

for x in x_centers:
    # row width 0.5m, length 16m
    world += f'        <collision name="row_c_{x}"><pose>{x} 0 0.5 0 0 0</pose><geometry><box><size>0.5 16 1</size></box></geometry></collision>\n'
    world += f'        <visual name="row_v_{x}"><pose>{x} 0 0.5 0 0 0</pose><geometry><box><size>0.5 16 1</size></box></geometry><material><ambient>0 1 0 1</ambient><diffuse>0 1 0 1</diffuse></material><transparency>0.8</transparency><cast_shadows>false</cast_shadows></visual>\n'

world += """      </link>
    </model>

    <include>
      <uri>model://field_streaks</uri>
      <pose>0 0 0.05 0 0 0</pose>
    </include>

    <include>
      <uri>model://agribot</uri>
      <!-- Starts at exact dead center -->
      <pose>0 0 0.5 0 0 1.5708</pose>
    </include>

"""

t_id = 0
for x in x_centers:
    for y in y_tomatoes:
        world += f"""    <include>
      <name>tomato_{t_id}</name>
      <uri>model://tomato_plant</uri>
      <pose>{x} {y} 0.05 0 0 0</pose>
    </include>
"""
        t_id += 1

# Add 4 sprinklers inside the crop rows with perfect symmetry
sprinkler_poses = [(-4.0, 3.0), (-4.0, -3.0), (4.0, 3.0), (4.0, -3.0)]
for i, (sx, sy) in enumerate(sprinkler_poses):
    world += f"""    <include>
      <name>sprinkler_{i}</name>
      <uri>model://sprinkler</uri>
      <pose>{sx} {sy} 0.1 0 0 0</pose>
    </include>
"""

world += """  </world>
</sdf>
"""

with open("src/agribot_description/worlds/farm_world.sdf", "w") as f:
    f.write(world)
