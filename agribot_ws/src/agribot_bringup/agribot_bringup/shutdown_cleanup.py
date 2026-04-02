# 이 모듈은 통합 실행과 런치 조율 패키지에서 shutdown cleanup 절차를 담당한다.
from __future__ import annotations

# 세션 태그와 안전한 허용 목록을 기준으로 AgriBot 관련 프로세스만 정리한다.
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import time
import uuid

from launch.actions import OpaqueFunction, RegisterEventHandler
from launch.event_handlers import OnShutdown


LAUNCH_SESSION_ENV_VAR = 'AGRIBOT_LAUNCH_SESSION_ID'
_CLEANED_SESSION_IDS: set[str] = set()
_SAFE_USER_CLEANUP_EXECUTABLES = frozenset(
    {
        'amcl',
        'behavior_server',
        'bt_navigator',
        'cmd_vel_watchdog',
        'collision_monitor',
        'component_container',
        'component_container_mt',
        'controller_server',
        'ekf_node',
        'frontier_explorer',
        'gazebo',
        'gzclient',
        'gzserver',
        'ignition-gazebo',
        'image_bridge',
        'lifecycle_manager',
        'map_server',
        'nav2_container',
        'odom_tf_broadcaster',
        'parameter_bridge',
        'planner_server',
        'robot_state_publisher',
        'rviz2',
        'slam_toolbox',
        'smoother_server',
        'static_transform_publisher',
        'waypoint_follower',
    }
)
_AGRIBOT_WORKSPACE_PROCESS_MARKERS = (
    '/build/agribot_',
    '/install/agribot_',
    '/src/agribot_',
)
_SAFE_USER_CLEANUP_ROS_TOPIC_COMMANDS = frozenset({'echo', 'hz'})
_SAFE_USER_CLEANUP_ROS_TOPICS = frozenset(
    {
        '/amcl_pose',
        '/clock',
        '/joint_states',
        '/map',
        '/odom',
        '/tf',
        '/tf_static',
    }
)
_SAFE_USER_CLEANUP_ROS_TOPIC_PREFIXES = ('/agribot/',)


@dataclass(frozen=True, slots=True)
class SessionProcess:
    # session 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    pid: int
    ppid: int
    state: str
    command: str


def resolve_launch_session_id(explicit_session_id: str | None = None) -> str:
    # 현재 입력 조건을 바탕으로 launch session ID를 계산하거나 결정한다.
    value = str(explicit_session_id or os.environ.get(LAUNCH_SESSION_ENV_VAR, '')).strip()
    if value:
        return value
    return f'agribot-launch-{uuid.uuid4().hex[:12]}'


def ensure_launch_session_id_env(explicit_session_id: str | None = None) -> str:
    # launch session ID ENV가 기대한 계약을 만족하는지 확인하고 필요한 보정을 수행한다.
    resolved_session_id = resolve_launch_session_id(explicit_session_id)
    os.environ[LAUNCH_SESSION_ENV_VAR] = resolved_session_id
    return resolved_session_id


def build_shutdown_cleanup_handler(
    session_id: str | None = None,
    *,
    grace_period_sec: float = 1.0,
) -> RegisterEventHandler:
    # shutdown 정리 작업 handler를 다른 계층에서 바로 사용할 수 있는 형태로 구성한다.
    resolved_session_id = resolve_launch_session_id(session_id)

    def _cleanup_on_shutdown(_context, *_args, **_kwargs):
        # cleanup on shutdown 정보를 계산해 반환한다.
        cleanup_launch_session(
            resolved_session_id,
            grace_period_sec=grace_period_sec,
        )
        return []

    return RegisterEventHandler(
        OnShutdown(
            on_shutdown=[
                OpaqueFunction(function=_cleanup_on_shutdown),
            ]
        )
    )


def cleanup_launch_session(
    session_id: str | None = None,
    *,
    grace_period_sec: float = 1.0,
) -> list[SessionProcess]:
    # cleanup 실행 session 정보를 계산해 반환한다.
    resolved_session_id = resolve_launch_session_id(session_id)
    if resolved_session_id in _CLEANED_SESSION_IDS:
        return []

    _CLEANED_SESSION_IDS.add(resolved_session_id)
    session_processes = _collect_session_processes(resolved_session_id)
    live_processes = [process for process in session_processes if process.state != 'Z']
    if not live_processes:
        return []

    _signal_processes(live_processes, signal.SIGTERM)
    remaining = _remaining_live_processes(live_processes)
    if remaining and grace_period_sec > 0.0:
        deadline = time.monotonic() + grace_period_sec
        while remaining and time.monotonic() < deadline:
            time.sleep(0.1)
            remaining = _remaining_live_processes(remaining)

    if remaining:
        _signal_processes(remaining, signal.SIGKILL)

    return live_processes


def cleanup_user_simulation_processes(
    *,
    grace_period_sec: float = 1.0,
    user_uid: int | None = None,
    workspace_path: str | os.PathLike[str] | None = None,
) -> list[SessionProcess]:
    # cleanup user 시뮬레이션 processes 정보를 계산해 반환한다.
    resolved_workspace_path = ''
    if workspace_path:
        resolved_workspace_path = str(Path(workspace_path).resolve())

    user_processes = _collect_user_simulation_processes(
        user_uid=os.getuid() if user_uid is None else user_uid,
        workspace_path=resolved_workspace_path,
    )
    live_processes = [process for process in user_processes if process.state != 'Z']
    if not live_processes:
        return []

    _signal_processes(live_processes, signal.SIGTERM)
    remaining = _remaining_live_processes(live_processes)
    if remaining and grace_period_sec > 0.0:
        deadline = time.monotonic() + grace_period_sec
        while remaining and time.monotonic() < deadline:
            time.sleep(0.1)
            remaining = _remaining_live_processes(remaining)

    if remaining:
        _signal_processes(remaining, signal.SIGKILL)

    return live_processes


def _collect_session_processes(session_id: str) -> list[SessionProcess]:
    # session processes를 모아 순회하기 쉬운 형태로 정리한다.
    session_processes: list[SessionProcess] = []
    excluded_pids = _current_process_lineage()
    ppid_map: dict[int, int] = {}

    for entry in os.scandir('/proc'):
        if not entry.name.isdigit():
            continue

        pid = int(entry.name)
        if pid in excluded_pids:
            continue

        if not _process_has_session_id(pid, session_id):
            continue

        stat = _read_process_stat(pid)
        if stat is None:
            continue

        process = SessionProcess(
            pid=pid,
            ppid=stat['ppid'],
            state=stat['state'],
            command=_read_process_command(pid),
        )
        session_processes.append(process)
        ppid_map[pid] = process.ppid

    session_processes.sort(
        key=lambda process: (_process_depth(process.pid, ppid_map), process.pid),
        reverse=True,
    )
    return session_processes


def _collect_user_simulation_processes(
    *,
    user_uid: int,
    workspace_path: str,
) -> list[SessionProcess]:
    # user 시뮬레이션 processes를 모아 순회하기 쉬운 형태로 정리한다.
    simulation_processes: list[SessionProcess] = []
    excluded_pids = _current_process_lineage()
    ppid_map: dict[int, int] = {}

    for entry in os.scandir('/proc'):
        if not entry.name.isdigit():
            continue

        pid = int(entry.name)
        if pid in excluded_pids:
            continue

        if _process_owner_uid(pid) != user_uid:
            continue

        stat = _read_process_stat(pid)
        if stat is None:
            continue

        argv = _read_process_argv(pid)
        if not _matches_user_cleanup_target(argv, workspace_path):
            continue

        command = ' '.join(argv).strip()
        if not command:
            command = _read_process_command(pid)

        process = SessionProcess(
            pid=pid,
            ppid=stat['ppid'],
            state=stat['state'],
            command=command,
        )
        simulation_processes.append(process)
        ppid_map[pid] = process.ppid

    simulation_processes.sort(
        key=lambda process: (_process_depth(process.pid, ppid_map), process.pid),
        reverse=True,
    )
    return simulation_processes


def _process_has_session_id(pid: int, session_id: str) -> bool:
    # process has session id 정보를 계산해 반환한다.
    environ_path = Path(f'/proc/{pid}/environ')
    try:
        payload = environ_path.read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return False
    target = f'{LAUNCH_SESSION_ENV_VAR}={session_id}'.encode()
    return target in payload.split(b'\0')


def _read_process_stat(pid: int) -> dict[str, int | str] | None:
    # process stat를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    stat_path = Path(f'/proc/{pid}/stat')
    try:
        payload = stat_path.read_text(encoding='utf-8')
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None

    closing_paren = payload.rfind(')')
    if closing_paren < 0:
        return None

    fields = payload[closing_paren + 2:].split()
    if len(fields) < 2:
        return None

    try:
        return {
            'state': fields[0],
            'ppid': int(fields[1]),
        }
    except ValueError:
        return None


def _read_process_command(pid: int) -> str:
    # process 명령를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    cmdline_path = Path(f'/proc/{pid}/cmdline')
    try:
        payload = cmdline_path.read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return ''
    command = payload.replace(b'\0', b' ').decode('utf-8', errors='replace').strip()
    return command


def _read_process_argv(pid: int) -> list[str]:
    # process argv를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
    cmdline_path = Path(f'/proc/{pid}/cmdline')
    try:
        payload = cmdline_path.read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return []

    return [
        segment.decode('utf-8', errors='replace')
        for segment in payload.split(b'\0')
        if segment
    ]


def _process_owner_uid(pid: int) -> int | None:
    # process owner uid 정보를 계산해 반환한다.
    proc_path = Path(f'/proc/{pid}')
    try:
        return proc_path.stat().st_uid
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
        return None


def _matches_user_cleanup_target(argv: list[str], workspace_path: str) -> bool:
    # matches user cleanup 대상 정보를 계산해 반환한다.
    if not argv:
        return False

    ros2_cli_arguments = _extract_ros2_cli_arguments(argv)
    if ros2_cli_arguments is not None:
        return (
            (
                len(ros2_cli_arguments) >= 3
                and ros2_cli_arguments[0] == 'launch'
                and ros2_cli_arguments[1].startswith('agribot_')
                and any(
                    argument.endswith('.launch.py')
                    for argument in ros2_cli_arguments[2:]
                )
            )
            or _matches_ros2_topic_monitor(ros2_cli_arguments)
        )

    if _matches_ros2_daemon_process(argv):
        return True

    executable_name = Path(argv[0]).name
    if executable_name == 'gz':
        return len(argv) >= 2 and argv[1] == 'sim'

    if executable_name == 'ign':
        return len(argv) >= 2 and argv[1] == 'gazebo'

    if executable_name in _SAFE_USER_CLEANUP_EXECUTABLES:
        return True

    return any(
        _is_workspace_process_argument(argument, workspace_path)
        for argument in _workspace_process_arguments(argv)
    )


def _extract_ros2_cli_arguments(argv: list[str]) -> list[str] | None:
    # 원본 데이터에서 ros2 CLI arguments만 골라 추출한다.
    executable_name = Path(argv[0]).name
    if executable_name == 'ros2':
        return argv[1:]

    if executable_name.startswith('python') and len(argv) >= 2:
        if Path(argv[1]).name == 'ros2':
            return argv[2:]
        if len(argv) >= 3 and argv[1] == '-m' and argv[2] == 'ros2cli':
            return argv[3:]

    return None


def _matches_ros2_topic_monitor(ros2_cli_arguments: list[str]) -> bool:
    # matches ROS 2 topic monitor 정보를 계산해 반환한다.
    if len(ros2_cli_arguments) < 3:
        return False
    if ros2_cli_arguments[0] != 'topic':
        return False
    if ros2_cli_arguments[1] not in _SAFE_USER_CLEANUP_ROS_TOPIC_COMMANDS:
        return False

    topic_name = _extract_ros_topic_name(ros2_cli_arguments[2:])
    if not topic_name:
        return False

    return topic_name in _SAFE_USER_CLEANUP_ROS_TOPICS or any(
        topic_name.startswith(prefix)
        for prefix in _SAFE_USER_CLEANUP_ROS_TOPIC_PREFIXES
    )


def _extract_ros_topic_name(arguments: list[str]) -> str:
    # 원본 데이터에서 ROS topic 이름만 골라 추출한다.
    for argument in arguments:
        if argument.startswith('/'):
            return argument
    return ''


def _matches_ros2_daemon_process(argv: list[str]) -> bool:
    # matches ROS 2 daemon process 정보를 계산해 반환한다.
    return (
        'ros2-daemon' in argv
        and any('ros2cli.daemon.daemonize' in argument for argument in argv)
    )


def _is_workspace_process_argument(argument: str, workspace_path: str) -> bool:
    # workspace process argument인지 여부를 불리언 값으로 판단한다.
    if not workspace_path or workspace_path not in argument:
        return False

    return any(marker in argument for marker in _AGRIBOT_WORKSPACE_PROCESS_MARKERS)


def _workspace_process_arguments(argv: list[str]) -> list[str]:
    # workspace process arguments 정보를 계산해 반환한다.
    if not argv:
        return []

    executable_name = Path(argv[0]).name
    if executable_name.startswith('python'):
        if len(argv) >= 2 and argv[1] != '-m':
            return [argv[1]]
        return []

    return [argv[0]]


def _process_depth(pid: int, ppid_map: dict[int, int]) -> int:
    # process depth 정보를 계산해 반환한다.
    depth = 0
    current_pid = pid
    seen: set[int] = set()
    while current_pid in ppid_map and current_pid not in seen:
        seen.add(current_pid)
        current_pid = ppid_map[current_pid]
        depth += 1
    return depth


def _current_process_lineage() -> set[int]:
    # 현재 process lineage 정보를 계산해 반환한다.
    lineage: set[int] = set()
    current_pid = os.getpid()

    while current_pid > 0 and current_pid not in lineage:
        lineage.add(current_pid)
        stat = _read_process_stat(current_pid)
        if stat is None:
            break
        current_pid = int(stat['ppid'])

    return lineage


def _signal_processes(processes: list[SessionProcess], sig: signal.Signals) -> None:
    # signal processes 정보를 계산해 반환한다.
    for process in processes:
        try:
            os.kill(process.pid, sig)
        except ProcessLookupError:
            continue
        except PermissionError:
            continue


def _remaining_live_processes(processes: list[SessionProcess]) -> list[SessionProcess]:
    # remaining 실시간 processes 정보를 계산해 반환한다.
    remaining: list[SessionProcess] = []
    for process in processes:
        try:
            os.kill(process.pid, 0)
        except ProcessLookupError:
            continue
        except PermissionError:
            remaining.append(process)
            continue
        remaining.append(process)
    return remaining
