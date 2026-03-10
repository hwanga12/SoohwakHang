from setuptools import setup
import os
from glob import glob

package_name = 'agribot_description'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Launch files
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*launch.[pxy][yma]*'))),
        # World files
        (os.path.join('share', package_name, 'worlds'),
            glob(os.path.join('worlds', '*.sdf'))),
        # Config files
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml'))),
        # RViz config
        (os.path.join('share', package_name, 'rviz'),
            glob(os.path.join('rviz', '*.rviz'))),
        # URDF/Xacro files
        (os.path.join('share', package_name, 'urdf'),
            glob(os.path.join('urdf', '*.urdf')) +
            glob(os.path.join('urdf', '*.xacro'))),
        # Models (Gazebo SDF)
        (os.path.join('share', package_name, 'models', 'agribot'),
            glob(os.path.join('models', 'agribot', '*.*'))),
        (os.path.join('share', package_name, 'models', 'agribot', 'meshes'),
            glob(os.path.join('models', 'agribot', 'meshes', '*.*'))),
        (os.path.join('share', package_name, 'models', 'greenhouse'),
            glob(os.path.join('models', 'greenhouse', '*.*'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='SSAFY A602 Team',
    maintainer_email='team@ssafy.com',
    description='AgriBot robot model, world files, and launch configurations',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
        ],
    },
)
