/*
 * 이 훅은 실시간 소켓 연결 상태를 화면 전반에서 공통으로 보여주기 위해 만든다.
 */
import { useEffect, useState } from 'react'
import { createStatusSocket } from '@/lib/realtime/socket'

/**
 * 실시간 상태를 화면과 로직에서 공통으로 쓰기 위한 타입이다.
 */
export type LiveStatus = 'connecting' | 'connected' | 'disconnected'

/**
 * 실시간 연결 상태와 소켓 생명주기 부수효과를 함께 관리하는 훅이다.
 */
export function useLiveStatus() {
  const [status, setStatus] = useState<LiveStatus>('connecting')

  useEffect(() => {
    let disposed = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let reconnectDelayMs = 1000

    const scheduleReconnect = () => {
      if (disposed || reconnectTimer !== null) {
        return
      }
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        reconnectDelayMs = Math.min(reconnectDelayMs * 2, 10000)
        connect()
      }, reconnectDelayMs)
    }

    const connect = () => {
      if (disposed) {
        return
      }
      setStatus('connecting')
      socket = createStatusSocket({
        onOpen: () => {
          reconnectDelayMs = 1000
          setStatus('connected')
        },
        onClose: () => {
          if (disposed) {
            return
          }
          setStatus('disconnected')
          scheduleReconnect()
        },
        onError: () => {
          if (disposed) {
            return
          }
          setStatus('disconnected')
        },
      })
    }

    connect()

    return () => {
      disposed = true
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
      }
      socket?.close()
    }
  }, [])

  return status
}
