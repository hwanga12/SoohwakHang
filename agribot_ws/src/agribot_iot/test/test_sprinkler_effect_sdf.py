from xml.etree import ElementTree as ET

from agribot_iot.sprinkler_controller_node import _build_effect_sdf


def test_build_effect_sdf_uses_particle_emitters() -> None:
    root = ET.fromstring(_build_effect_sdf('sprinkler_effect_demo', 'red'))

    model = root.find('./model')
    assert model is not None
    assert model.attrib['name'] == 'sprinkler_effect_demo'
    assert model.find('./link/visual[@name="spray_nozzle"]') is not None

    emitters = model.findall('./link/particle_emitter')
    assert [item.attrib['name'] for item in emitters] == [
        'spray_center',
        'spray_left',
        'spray_right',
        'spray_front',
        'spray_back',
    ]
    assert all(item.attrib['type'] == 'point' for item in emitters)


def test_build_effect_sdf_tints_particles_from_requested_color() -> None:
    root = ET.fromstring(_build_effect_sdf('sprinkler_effect_demo', 'yellow'))

    center = root.find('./model/link/particle_emitter[@name="spray_center"]')
    assert center is not None
    assert center.findtext('color_start') == '1.0 0.85 0.1 0.73'
    assert center.findtext('color_end') == '1.0 0.85 0.1 0.27'


def test_build_effect_sdf_points_center_emitter_upward() -> None:
    root = ET.fromstring(_build_effect_sdf('sprinkler_effect_demo', 'red'))

    center = root.find('./model/link/particle_emitter[@name="spray_center"]')
    assert center is not None
    pose = center.findtext('pose')
    assert pose == '0 0 0.24 0 -1.52 0'
