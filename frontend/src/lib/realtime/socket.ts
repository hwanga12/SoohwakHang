import { env } from '@/config/env'

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
