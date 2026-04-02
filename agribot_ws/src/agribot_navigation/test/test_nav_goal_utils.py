# 이 테스트는 자율주행과 경로 계획 패키지의 nav goal utils 동작을 검증한다.
from agribot_navigation.nav_goal_utils import build_latest_pose_stamped


def test_build_latest_pose_stamped_uses_latest_tf_lookup_stamp() -> None:
    # build latest 위치 자세 stamped uses latest TF lookup stamp 동작과 회귀 여부를 검증한다.
    stamped = build_latest_pose_stamped(
        frame_id='map',
        x_value=1.25,
        y_value=-2.5,
        z_value=0.0,
        yaw_value=1.5708,
    )

    assert stamped.header.frame_id == 'map'
    assert stamped.header.stamp.sec == 0
    assert stamped.header.stamp.nanosec == 0
    assert stamped.pose.position.x == 1.25
    assert stamped.pose.position.y == -2.5
    assert stamped.pose.orientation.z != 0.0
    assert stamped.pose.orientation.w != 0.0
