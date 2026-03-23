from setuptools import setup
import os
from glob import glob

package_name = 'agribot_navigation'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml'))),
        (os.path.join('share', package_name, 'rviz'),
            glob(os.path.join('rviz', '*.rviz'))),
        (os.path.join('share', package_name, 'behavior_trees'),
            glob(os.path.join('behavior_trees', '*.xml'))),
        (os.path.join('share', package_name, 'maps'),
            glob(os.path.join('maps', '*'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='SSAFY A602 Team',
    maintainer_email='team@ssafy.com',
    description='Autonomous navigation for AgriBot using Nav2 and SLAM',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'generate_static_map = agribot_navigation.generate_static_map:main',
            'validate_patrol_waypoints = agribot_navigation.patrol_config:main',
            'plan_harvest_route = agribot_navigation.harvest_routing:main',
            'startup_map_tf_broadcaster = agribot_navigation.startup_map_tf_broadcaster:main',
            'patrol_node = agribot_navigation.patrol_node:main',
            'frontier_explorer = agribot_navigation.frontier_explorer:main',
            'harvest_route_node = agribot_navigation.harvest_route_node:main',
        ],
    },
)
