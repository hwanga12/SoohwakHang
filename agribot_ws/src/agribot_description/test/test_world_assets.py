"""월드, 작물 카탈로그, 로봇팔/바구니 자산이 서로 어긋나지 않는지 검증한다."""

from pathlib import Path
import xml.etree.ElementTree as ET

import yaml


DESCRIPTION_ROOT = Path(__file__).resolve().parents[1]
WORLD_PATH = DESCRIPTION_ROOT / 'worlds' / 'farm_world.sdf'
CROP_INSTANCES_PATH = DESCRIPTION_ROOT / 'config' / 'crop_instances.yaml'
AGRIBOT_MODEL_PATH = DESCRIPTION_ROOT / 'models' / 'agribot' / 'model.sdf'
TOMATO_MODEL_PATH = DESCRIPTION_ROOT / 'models' / 'tomato' / 'model.sdf'
AGRIBOT_URDF_PATH = DESCRIPTION_ROOT / 'urdf' / 'agribot.urdf'


def _parse_xml(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def test_world_physics_and_tomato_catalog_stay_in_sync() -> None:
    world_root = _parse_xml(WORLD_PATH)
    crop_instances = yaml.safe_load(CROP_INSTANCES_PATH.read_text(encoding='utf-8'))

    max_step_size = world_root.findtext('./world/physics/max_step_size')
    assert max_step_size == '0.004'

    tomato_model_names = {
        include.findtext('name')
        for include in world_root.findall('./world/include')
        if include.findtext('uri') == 'model://tomato'
    }
    assert len(tomato_model_names) == 24

    catalog_tomato_names = {
        str(item['world_model_name'])
        for item in crop_instances['tomatoes']
    }
    assert tomato_model_names == catalog_tomato_names


def test_tomato_model_uses_gazebo_mesh_and_half_scale_collision_volume() -> None:
    tomato_root = _parse_xml(TOMATO_MODEL_PATH)

    assert tomato_root.findtext('./model/link/visual/geometry/mesh/uri') == 'meshes/tomato_gazebo.obj'
    assert tomato_root.findtext('./model/link/visual/geometry/mesh/scale') == '0.03 0.03 0.03'
    assert tomato_root.findtext('./model/link/visual/material/ambient') == '0.55 0.08 0.06 1'
    assert tomato_root.findtext('./model/link/visual/material/diffuse') == '0.86 0.16 0.10 1'
    assert tomato_root.findtext('./model/link/collision/pose') == '0 0 -0.002 0 0 0'
    assert tomato_root.findtext('./model/link/collision/geometry/sphere/radius') == '0.029'


def test_tomato_gazebo_mesh_stays_low_poly_for_simulation() -> None:
    tomato_mesh_path = (
        DESCRIPTION_ROOT / 'models' / 'tomato' / 'meshes' / 'tomato_gazebo.obj'
    )
    mesh_lines = tomato_mesh_path.read_text(encoding='utf-8').splitlines()

    vertex_count = sum(1 for line in mesh_lines if line.startswith('v '))
    face_count = sum(1 for line in mesh_lines if line.startswith('f '))

    assert vertex_count <= 64
    assert face_count <= 80


def test_harvest_arm_pose_and_basket_collision_surfaces_match() -> None:
    agribot_root = _parse_xml(AGRIBOT_MODEL_PATH)
    agribot_urdf_root = _parse_xml(AGRIBOT_URDF_PATH)

    assert (
        agribot_root.find("./model/link[@name='harvest_arm_link']").findtext('pose')
        == '0.04 0 0.29 0 0.15 0'
    )
    assert (
        agribot_urdf_root.find("./joint[@name='harvest_arm_joint']").find('origin').attrib['xyz']
        == '0.04 0 0.29'
    )
    assert (
        agribot_urdf_root.find("./joint[@name='harvest_arm_joint']").find('origin').attrib['rpy']
        == '0 0.15 0'
    )
    assert (
        agribot_root.find("./model/link[@name='harvest_arm_link']/visual[@name='arm_mesh_visual']")
        .findtext('pose')
        == '-0.025 0 0.081 3.1416 -1.5708 -1.5708'
    )
    assert agribot_root.find("./model/joint[@name='harvest_arm_joint']").attrib['type'] == 'revolute'
    assert agribot_urdf_root.find("./joint[@name='harvest_arm_joint']").attrib['type'] == 'revolute'
    assert (
        agribot_root.findtext("./model/plugin[joint_name='harvest_arm_joint']/topic")
        == '/agribot/harvest_arm_joint/cmd_pos'
    )
    wrist_collision_pose = agribot_root.findtext(
        "./model/link[@name='harvest_arm_link']/collision[@name='arm_wrist_collision']/pose"
    )
    left_gripper_pose = agribot_root.findtext(
        "./model/link[@name='harvest_arm_link']/collision[@name='gripper_left_collision']/pose"
    )
    right_gripper_pose = agribot_root.findtext(
        "./model/link[@name='harvest_arm_link']/collision[@name='gripper_right_collision']/pose"
    )
    assert wrist_collision_pose == '0.25 0 0.22 0 0 0'
    assert left_gripper_pose == '0.29 0.028 0.27 0 0 0'
    assert right_gripper_pose == '0.29 -0.028 0.27 0 0 0'

    basket_collision_names = {
        collision.attrib['name']
        for collision in agribot_root.findall("./model/link[@name='harvest_basket_link']/collision")
    }
    assert basket_collision_names == {
        'basket_floor_collision',
        'basket_left_wall_collision',
        'basket_right_wall_collision',
        'basket_front_wall_collision',
        'basket_back_wall_collision',
    }

    for collision_name in basket_collision_names:
        mu_value = agribot_root.findtext(
            "./model/link[@name='harvest_basket_link']"
            f"/collision[@name='{collision_name}']/surface/friction/ode/mu"
        )
        assert mu_value is not None
