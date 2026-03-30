"""Helpers for building Nav2 goals that stay robust under simulated time jitter."""

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
    """Build a PoseStamped that asks TF consumers to use the latest available transform.

    Nav2 goal poses are map-frame targets. In simulation, TF producers can briefly lag or
    reorder timestamps while Gazebo, AMCL, and bridges settle. Using a zero timestamp keeps
    the goal anchored to the latest transform instead of a stale sim-time instant that may
    already have fallen out of the TF buffer by the time Nav2 evaluates the goal.
    """

    stamped = PoseStamped()
    stamped.header.stamp = TimeMsg()
    stamped.header.frame_id = frame_id
    stamped.pose.position.x = float(x_value)
    stamped.pose.position.y = float(y_value)
    stamped.pose.position.z = float(z_value)
    stamped.pose.orientation.z = math.sin(float(yaw_value) / 2.0)
    stamped.pose.orientation.w = math.cos(float(yaw_value) / 2.0)
    return stamped
