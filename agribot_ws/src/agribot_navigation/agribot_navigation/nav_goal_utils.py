# 이 모듈은 자율주행과 경로 계획 패키지에서 nav goal utils 기능을 담당한다.
from __future__ import annotations

import math

from builtin_interfaces.msg import Time as TimeMsg
from geometry_msgs.msg import PoseStamped


def build_latest_pose_stamped(
    *,
    frame_id: str,
    x_value: float,
    y_value: float,
    z_value: float = 0.0,
    yaw_value: float,
) -> PoseStamped:
    # latest 위치 자세 stamped를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.

    stamped = PoseStamped()
    stamped.header.stamp = TimeMsg()
    stamped.header.frame_id = frame_id
    stamped.pose.position.x = float(x_value)
    stamped.pose.position.y = float(y_value)
    stamped.pose.position.z = float(z_value)
    stamped.pose.orientation.z = math.sin(float(yaw_value) / 2.0)
    stamped.pose.orientation.w = math.cos(float(yaw_value) / 2.0)
    return stamped
