from setuptools import setup
import os
from glob import glob

package_name = 'agribot_iot'

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
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='SSAFY A602 Team',
    maintainer_email='team@ssafy.com',
    description='IoT device communication for AgriBot',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'environment_sensor_node = agribot_iot.environment_sensor_node:main',
            'mqtt_bridge_node = agribot_iot.mqtt_bridge_node:main',
            'watering_controller_node = agribot_iot.watering_controller_node:main',
            'nutrient_controller_node = agribot_iot.nutrient_controller_node:main',
            'sprinkler_controller_node = agribot_iot.sprinkler_controller_node:main',
        ],
    },
)
