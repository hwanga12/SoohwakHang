# 이 모듈은 상위 제어와 의사결정 패키지에서 setup 판단과 실행 보조 로직을 담당한다.
from setuptools import setup
import os
from glob import glob

package_name = 'agribot_control'

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
    description='Motor control and drive interface for AgriBot',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'actuation_request_node = agribot_control.actuation_request_node:main',
            'climate_decision_node = agribot_control.climate_decision_node:main',
            'manual_actuation_guard_node = agribot_control.manual_actuation_guard_node:main',
            'mission_manager = agribot_control.mission_manager:main',
            'watering_decision_node = agribot_control.watering_decision_node:main',
        ],
    },
)
