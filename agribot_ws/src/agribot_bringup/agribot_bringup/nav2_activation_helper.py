# 이 모듈은 통합 실행과 런치 조율 패키지에서 nav2 activation helper 절차를 담당한다.
from __future__ import annotations

import sys
from typing import Iterable

import rclpy
from lifecycle_msgs.msg import State, Transition
from lifecycle_msgs.srv import ChangeState, GetState
from rclpy.node import Node


class Nav2ActivationHelper(Node):
    # NAV 2 activation 관련 동작과 상태를 함께 다루기 위한 클래스를 정의한다.
    def __init__(self) -> None:
        # Nav2ActivationHelper 인스턴스가 사용할 기본 상태와 의존성을 준비한다.
        super().__init__('nav2_activation_helper')
        self.declare_parameter(
            'node_names',
            ['controller_server', 'planner_server', 'smoother_server', 'bt_navigator'],
        )
        self.declare_parameter('service_wait_timeout_sec', 45.0)
        self.declare_parameter('state_wait_timeout_sec', 30.0)

    def run(self) -> int:
        # 전체 실행 흐름을 시작하거나 마무리한다.
        node_names = list(self.get_parameter('node_names').value)
        service_wait_timeout_sec = float(self.get_parameter('service_wait_timeout_sec').value)
        state_wait_timeout_sec = float(self.get_parameter('state_wait_timeout_sec').value)

        self.get_logger().info(f'Nav2 activation helper starting for nodes: {node_names}')

        for node_name in node_names:
            if not self._wait_for_lifecycle_services(node_name, service_wait_timeout_sec):
                return 1

        for node_name in node_names:
            state_id = self._get_state(node_name, state_wait_timeout_sec)
            if state_id is None:
                return 1
            if state_id == State.PRIMARY_STATE_UNCONFIGURED:
                if not self._change_state(
                    node_name, Transition.TRANSITION_CONFIGURE, state_wait_timeout_sec
                ):
                    return 1

        for node_name in node_names:
            state_id = self._get_state(node_name, state_wait_timeout_sec)
            if state_id is None:
                return 1
            if state_id == State.PRIMARY_STATE_INACTIVE:
                if not self._change_state(
                    node_name, Transition.TRANSITION_ACTIVATE, state_wait_timeout_sec
                ):
                    return 1

        for node_name in node_names:
            state_id = self._get_state(node_name, state_wait_timeout_sec)
            if state_id != State.PRIMARY_STATE_ACTIVE:
                self.get_logger().error(
                    f'Node {node_name} failed to reach ACTIVE state. current_state={state_id}'
                )
                return 1

        self.get_logger().info('Nav2 activation helper completed successfully.')
        return 0

    def _wait_for_lifecycle_services(self, node_name: str, timeout_sec: float) -> bool:
        # lifecycle 서비스이 준비될 때까지 기다린다.
        get_state_client = self.create_client(GetState, f'/{node_name}/get_state')
        change_state_client = self.create_client(ChangeState, f'/{node_name}/change_state')
        get_ok = get_state_client.wait_for_service(timeout_sec=timeout_sec)
        change_ok = change_state_client.wait_for_service(timeout_sec=timeout_sec)
        if not get_ok or not change_ok:
            self.get_logger().error(
                f'Lifecycle services for {node_name} were not available within {timeout_sec:.1f}s'
            )
            return False
        return True

    def _get_state(self, node_name: str, timeout_sec: float) -> int | None:
        # 상태를 읽거나 조회해 호출부가 바로 사용할 수 있게 돌려준다.
        client = self.create_client(GetState, f'/{node_name}/get_state')
        request = GetState.Request()
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)
        if not future.done() or future.result() is None:
            self.get_logger().error(f'Failed to read lifecycle state for {node_name}')
            return None
        return int(future.result().current_state.id)

    def _change_state(self, node_name: str, transition_id: int, timeout_sec: float) -> bool:
        # change 상태 정보를 계산해 반환한다.
        client = self.create_client(ChangeState, f'/{node_name}/change_state')
        request = ChangeState.Request()
        request.transition.id = transition_id
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)
        if not future.done() or future.result() is None:
            self.get_logger().error(
                f'Lifecycle transition {transition_id} for {node_name} timed out.'
            )
            return False
        if not future.result().success:
            self.get_logger().error(
                f'Lifecycle transition {transition_id} for {node_name} was rejected.'
            )
            return False
        return True


def main(args: Iterable[str] | None = None) -> None:
    # 스크립트 실행 진입점에서 전체 흐름을 순서대로 실행한다.
    rclpy.init(args=args)
    node = Nav2ActivationHelper()
    try:
        code = node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()
    if code != 0:
        raise SystemExit(code)


if __name__ == '__main__':
    main(sys.argv)
