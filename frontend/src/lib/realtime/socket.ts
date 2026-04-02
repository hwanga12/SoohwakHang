/*
 * 이 모듈은 프론트엔드에서 실시간 소켓 연결과 이벤트 수신을 담당한다.
 */
import { env } from '@/config/env'

/**
 * 소켓 handlers 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type SocketHandlers = {
  onOpen?: () => void
  onMessage?: (payload: unknown) => void
  onError?: (event: Event) => void
  onClose?: (event: CloseEvent) => void
}

function parsePayload(data: unknown) {
  if (typeof data !== 'string') {
    return data
  }

  try {
    return JSON.parse(data) as unknown
  } catch {
    return data
  }
}

/**
 * 상태 소켓을 생성하는 함수다.
 */
export function createStatusSocket(handlers: SocketHandlers = {}) {
  const socket = new WebSocket(env.wsUrl)

  socket.addEventListener('open', () => {
    handlers.onOpen?.()
  })

  socket.addEventListener('message', (event) => {
    handlers.onMessage?.(parsePayload(event.data))
  })

  socket.addEventListener('error', (event) => {
    handlers.onError?.(event)
  })

  socket.addEventListener('close', (event) => {
    handlers.onClose?.(event)
  })

  return socket
}
