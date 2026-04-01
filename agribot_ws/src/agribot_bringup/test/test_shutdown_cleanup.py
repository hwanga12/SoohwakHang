# 이 테스트는 통합 실행과 런치 조율 패키지의 shutdown cleanup 동작을 검증한다.
import signal

from agribot_bringup.shutdown_cleanup import (
    SessionProcess,
    cleanup_launch_session,
    cleanup_user_simulation_processes,
)
import agribot_bringup.shutdown_cleanup as shutdown_cleanup


def test_cleanup_launch_session_only_signals_live_tagged_processes(monkeypatch) -> None:
    # 정리 작업 launch session only signals live tagged processes 동작과 회귀 여부를 검증한다.
    shutdown_cleanup._CLEANED_SESSION_IDS.clear()
    live_process = SessionProcess(pid=101, ppid=10, state='S', command='gz sim')
    zombie_process = SessionProcess(pid=202, ppid=10, state='Z', command='planner_server')
    signaled: list[tuple[int, signal.Signals]] = []

    monkeypatch.setattr(
        shutdown_cleanup,
        '_collect_session_processes',
        lambda session_id: [live_process, zombie_process],
    )
    monkeypatch.setattr(
        shutdown_cleanup,
        '_remaining_live_processes',
        lambda processes: [],
    )
    monkeypatch.setattr(
        shutdown_cleanup.os,
        'kill',
        lambda pid, sig: signaled.append((pid, sig)),
    )

    cleaned = cleanup_launch_session('session-129-safe-cleanup', grace_period_sec=0.5)

    assert cleaned == [live_process]
    assert signaled == [(101, signal.SIGTERM)]


def test_cleanup_launch_session_runs_once_per_session(monkeypatch) -> None:
    # 정리 작업 launch session runs once PER session 동작과 회귀 여부를 검증한다.
    shutdown_cleanup._CLEANED_SESSION_IDS.clear()
    signaled: list[tuple[int, signal.Signals]] = []
    process = SessionProcess(pid=301, ppid=30, state='S', command='rviz2')

    monkeypatch.setattr(
        shutdown_cleanup,
        '_collect_session_processes',
        lambda session_id: [process],
    )
    monkeypatch.setattr(
        shutdown_cleanup,
        '_remaining_live_processes',
        lambda processes: [],
    )
    monkeypatch.setattr(
        shutdown_cleanup.os,
        'kill',
        lambda pid, sig: signaled.append((pid, sig)),
    )

    first = cleanup_launch_session('session-129-guard', grace_period_sec=0.0)
    second = cleanup_launch_session('session-129-guard', grace_period_sec=0.0)

    assert first == [process]
    assert second == []
    assert signaled == [(301, signal.SIGTERM)]


def test_cleanup_user_simulation_processes_only_signals_live_targets(monkeypatch) -> None:
    # 정리 작업 user 시뮬레이션 processes only signals live targets 동작과 회귀 여부를 검증한다.
    live_process = SessionProcess(pid=401, ppid=40, state='S', command='ros2 launch agribot_bringup simulation.launch.py')
    zombie_process = SessionProcess(pid=402, ppid=40, state='Z', command='gz sim greenhouse.sdf')
    signaled: list[tuple[int, signal.Signals]] = []

    monkeypatch.setattr(
        shutdown_cleanup,
        '_collect_user_simulation_processes',
        lambda **kwargs: [live_process, zombie_process],
    )
    monkeypatch.setattr(
        shutdown_cleanup,
        '_remaining_live_processes',
        lambda processes: [],
    )
    monkeypatch.setattr(
        shutdown_cleanup.os,
        'kill',
        lambda pid, sig: signaled.append((pid, sig)),
    )

    cleaned = cleanup_user_simulation_processes(
        grace_period_sec=0.5,
        workspace_path='/tmp/agribot_ws',
        user_uid=1000,
    )

    assert cleaned == [live_process]
    assert signaled == [(401, signal.SIGTERM)]


def test_matches_user_cleanup_target_prefers_agribot_processes_only() -> None:
    # matches user 정리 작업 target prefers agribot processes only 동작과 회귀 여부를 검증한다.
    assert shutdown_cleanup._matches_user_cleanup_target(
        ['ros2', 'launch', 'agribot_bringup', 'simulation.launch.py'],
        '/home/ssafy/SSAFY/S14P21A602/agribot_ws',
    ) is True
    assert shutdown_cleanup._matches_user_cleanup_target(
        ['gz', 'sim', 'greenhouse.sdf'],
        '/home/ssafy/SSAFY/S14P21A602/agribot_ws',
    ) is True
    assert shutdown_cleanup._matches_user_cleanup_target(
        [
            'python3',
            '/home/ssafy/SSAFY/S14P21A602/agribot_ws/install/agribot_bringup/lib/agribot_bringup/mission_bridge_executor',
        ],
        '/home/ssafy/SSAFY/S14P21A602/agribot_ws',
    ) is True
    assert shutdown_cleanup._matches_user_cleanup_target(
        ['ros2', 'launch', 'turtlebot3_gazebo', 'empty_world.launch.py'],
        '/home/ssafy/SSAFY/S14P21A602/agribot_ws',
    ) is False
    assert shutdown_cleanup._matches_user_cleanup_target(
        ['gnome-shell'],
        '/home/ssafy/SSAFY/S14P21A602/agribot_ws',
    ) is False


def test_matches_user_cleanup_target_includes_safe_ros_support_processes() -> None:
    # matches user 정리 작업 target includes safe ROS support processes 동작과 회귀 여부를 검증한다.
    workspace_path = '/home/ssafy/SSAFY/S14P21A602/agribot_ws'

    assert shutdown_cleanup._matches_user_cleanup_target(
        ['python3', '/opt/ros/jazzy/bin/ros2', 'topic', 'hz', '/amcl_pose'],
        workspace_path,
    ) is True
    assert shutdown_cleanup._matches_user_cleanup_target(
        [
            'python3',
            '/opt/ros/jazzy/bin/ros2',
            'topic',
            'echo',
            '--once',
            '/agribot/imu',
        ],
        workspace_path,
    ) is True
    assert shutdown_cleanup._matches_user_cleanup_target(
        [
            'python3',
            '-c',
            'from ros2cli.daemon.daemonize import main; main()',
            '--name',
            'ros2-daemon',
            '--ros-domain-id',
            '0',
        ],
        workspace_path,
    ) is True
    assert shutdown_cleanup._matches_user_cleanup_target(
        ['python3', '/opt/ros/jazzy/bin/ros2', 'topic', 'hz', '/camera/image_raw'],
        workspace_path,
    ) is False
