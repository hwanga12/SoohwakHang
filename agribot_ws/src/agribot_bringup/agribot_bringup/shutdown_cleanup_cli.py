from __future__ import annotations

# 스크립트와 launch 종료 훅에서 같은 정리 로직을 재사용할 수 있게 CLI로 노출한다.
import argparse
import os

from agribot_bringup.shutdown_cleanup import (
    cleanup_launch_session,
    cleanup_user_simulation_processes,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Safely clean up AgriBot simulation processes.',
    )
    parser.add_argument(
        '--scope',
        choices=('session', 'user'),
        default='user',
        help='Cleanup only the current launch session or all current-user AgriBot simulation processes.',
    )
    parser.add_argument(
        '--session-id',
        default='',
        help='Launch session id to clean when --scope=session is used.',
    )
    parser.add_argument(
        '--workspace-path',
        default=os.environ.get('AGRIBOT_WS', ''),
        help='Workspace path used to detect project-owned processes for --scope=user.',
    )
    parser.add_argument(
        '--grace-period',
        type=float,
        default=float(os.environ.get('CLEANUP_SLEEP_SECONDS', '2')),
        help='Seconds to wait after SIGTERM before SIGKILL.',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)

    if args.scope == 'session':
        cleanup_launch_session(
            args.session_id or None,
            grace_period_sec=args.grace_period,
        )
        return 0

    cleanup_user_simulation_processes(
        grace_period_sec=args.grace_period,
        workspace_path=args.workspace_path,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
