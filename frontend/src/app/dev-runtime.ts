export type DevRouteMethod = 'GET' | 'POST'
export type DevRouteVerificationState = 'verified' | 'failed'

type RouteSnapshot = Record<string, DevRouteVerificationState>
type Listener = () => void

const listeners = new Set<Listener>()
const routeSnapshot: RouteSnapshot = {}

function toRouteKey(method: DevRouteMethod, path: string) {
  return `${method.toUpperCase()} ${path}`
}

function notify() {
  for (const listener of listeners) {
    listener()
  }
}

export function markRouteVerified(method: DevRouteMethod, path: string) {
  routeSnapshot[toRouteKey(method, path)] = 'verified'
  notify()
}

export function markRouteFailed(method: DevRouteMethod, path: string) {
  routeSnapshot[toRouteKey(method, path)] = 'failed'
  notify()
}

export function getRouteVerificationSnapshot(): RouteSnapshot {
  return { ...routeSnapshot }
}

export function subscribeRouteVerification(listener: Listener) {
  listeners.add(listener)

  return () => {
    listeners.delete(listener)
  }
}

export function getRouteKey(method: DevRouteMethod, path: string) {
  return toRouteKey(method, path)
}
