/*
 * 이 모듈은 프론트엔드 앱 골격에서 개발 환경에서만 쓰는 보조 런타임 설정을 모은다.
 */
/**
 * 개발용 경로 메서드 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type DevRouteMethod = 'GET' | 'POST'
/**
 * 개발용 경로 검증 상태를 화면과 로직에서 공통으로 쓰기 위한 타입이다.
 */
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

/**
 * 경로를 검증 성공 상태로 기록하는 함수다.
 */
export function markRouteVerified(method: DevRouteMethod, path: string) {
  routeSnapshot[toRouteKey(method, path)] = 'verified'
  notify()
}

/**
 * 경로를 검증 실패 상태로 기록하는 함수다.
 */
export function markRouteFailed(method: DevRouteMethod, path: string) {
  routeSnapshot[toRouteKey(method, path)] = 'failed'
  notify()
}

/**
 * 현재까지 기록된 경로 검증 스냅샷을 복사해 반환하는 함수다.
 */
export function getRouteVerificationSnapshot(): RouteSnapshot {
  return { ...routeSnapshot }
}

/**
 * 경로 검증 변경을 구독할 리스너를 등록하는 함수다.
 */
export function subscribeRouteVerification(listener: Listener) {
  listeners.add(listener)

  return () => {
    listeners.delete(listener)
  }
}

/**
 * 경로 키를 조회해 반환하는 함수다.
 */
export function getRouteKey(method: DevRouteMethod, path: string) {
  return toRouteKey(method, path)
}
