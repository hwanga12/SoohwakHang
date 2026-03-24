import {
  createContext,
  useContext,
  useEffect,
  useState,
  type PropsWithChildren,
} from 'react'
import { env } from '@/config/env'

export type DevSurfaceStatus = 'live' | 'sample' | 'partial' | 'stub' | 'pending'

type DevInspectorContextValue = {
  isDevelopment: boolean
  isOverlayEnabled: boolean
  setOverlayEnabled: (enabled: boolean) => void
  toggleOverlay: () => void
}

const DEV_OVERLAY_STORAGE_KEY = 'agribot.dev-overlay'

const DevInspectorContext = createContext<DevInspectorContextValue>({
  isDevelopment: false,
  isOverlayEnabled: false,
  setOverlayEnabled: () => {},
  toggleOverlay: () => {},
})

function readStoredOverlayPreference() {
  if (typeof window === 'undefined' || env.mode !== 'development') {
    return false
  }

  const storedValue = window.localStorage.getItem(DEV_OVERLAY_STORAGE_KEY)

  if (storedValue === 'false') {
    return false
  }

  return true
}

export function DevInspectorProvider({ children }: PropsWithChildren) {
  const isDevelopment = env.mode === 'development'
  const [isOverlayEnabled, setOverlayEnabledState] = useState(readStoredOverlayPreference)

  useEffect(() => {
    if (typeof window === 'undefined' || !isDevelopment) {
      return
    }

    window.localStorage.setItem(
      DEV_OVERLAY_STORAGE_KEY,
      isOverlayEnabled ? 'true' : 'false',
    )
  }, [isDevelopment, isOverlayEnabled])

  const setOverlayEnabled = (enabled: boolean) => {
    if (!isDevelopment) {
      return
    }

    setOverlayEnabledState(enabled)
  }

  const toggleOverlay = () => {
    if (!isDevelopment) {
      return
    }

    setOverlayEnabledState((current) => !current)
  }

  return (
    <DevInspectorContext.Provider
      value={{
        isDevelopment,
        isOverlayEnabled: isDevelopment && isOverlayEnabled,
        setOverlayEnabled,
        toggleOverlay,
      }}
    >
      {children}
    </DevInspectorContext.Provider>
  )
}

export function useDevInspector() {
  return useContext(DevInspectorContext)
}
