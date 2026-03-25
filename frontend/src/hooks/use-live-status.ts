import { useEffect, useState } from 'react'
import { createStatusSocket } from '@/lib/realtime/socket'

export type LiveStatus = 'connecting' | 'connected' | 'disconnected'

export function useLiveStatus() {
  const [status, setStatus] = useState<LiveStatus>('connecting')

  useEffect(() => {
    const socket = createStatusSocket({
      onOpen: () => {
        setStatus('connected')
      },
      onClose: () => {
        setStatus('disconnected')
      },
      onError: () => {
        setStatus('disconnected')
      },
    })

    return () => {
      socket.close()
    }
  }, [])

  return status
}
