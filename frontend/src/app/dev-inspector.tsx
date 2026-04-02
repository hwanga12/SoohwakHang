/*
 * 이 모듈은 프론트엔드 앱 골격에서 개발 중 계약과 데이터 흐름을 점검하는 도구를 제공한다.
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from 'react'
import type { DataSource } from '@/lib/api/agribot'
import {
  getRouteKey,
  getRouteVerificationSnapshot,
  subscribeRouteVerification,
  type DevRouteMethod,
} from '@/app/dev-runtime'
import { env } from '@/config/env'

/**
 * 개발용 표면 상태를 화면과 로직에서 공통으로 쓰기 위한 타입이다.
 */
export type DevSurfaceStatus = 'live' | 'sample' | 'partial' | 'contract' | 'pending'

type OpenApiDocument = {
  paths?: Record<string, Record<string, unknown>>
}

type RouteCatalog = {
  isLoaded: boolean
  routeKeys: Set<string>
}

type DevRouteRequirement = {
  method: DevRouteMethod
  path: string
}

type DevQuerySignal = {
  kind: 'query'
  label: string
  routes: DevRouteRequirement[]
  source: DataSource
}

type DevActionSignal = {
  kind: 'action'
  label: string
  routes: DevRouteRequirement[]
  matching: 'all' | 'any'
}

/**
 * 개발용 표면 contract 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type DevSurfaceContract = {
  title: string
  queries?: DevQuerySignal[]
  actions?: DevActionSignal[]
}

type EvaluatedDevSurface = {
  detail: string
  status: DevSurfaceStatus
  title: string
}

type DevInspectorContextValue = {
  isDevelopment: boolean
  isOverlayEnabled: boolean
  setOverlayEnabled: (enabled: boolean) => void
  toggleOverlay: () => void
  catalog: RouteCatalog
  verifiedRoutes: Record<string, 'verified' | 'failed'>
}

const DEV_OVERLAY_STORAGE_KEY = 'agribot.dev-overlay'

const DevInspectorContext = createContext<DevInspectorContextValue>({
  isDevelopment: false,
  isOverlayEnabled: false,
  setOverlayEnabled: () => {},
  toggleOverlay: () => {},
  catalog: {
    isLoaded: false,
    routeKeys: new Set<string>(),
  },
  verifiedRoutes: {},
})

/**
 * get signal을 생성하는 함수다.
 */
export function createGetSignal(
  label: string,
  source: DataSource,
  path: string,
): DevQuerySignal {
  return {
    kind: 'query',
    label,
    routes: [{ method: 'GET', path }],
    source,
  }
}

/**
 * post action을 생성하는 함수다.
 */
export function createPostAction(
  label: string,
  paths: string[],
  matching: 'all' | 'any' = 'all',
): DevActionSignal {
  return {
    kind: 'action',
    label,
    matching,
    routes: paths.map((path) => ({
      method: 'POST',
      path,
    })),
  }
}

function readStoredOverlayPreference() {
  if (typeof window === 'undefined' || env.mode !== 'development') {
    return false
  }

  const storedValue = window.localStorage.getItem(DEV_OVERLAY_STORAGE_KEY)

  return storedValue === 'true'
}

function buildOpenApiUrl() {
  try {
    const url = new URL(env.apiBaseUrl)
    url.pathname = '/openapi.json'
    url.search = ''
    url.hash = ''
    return url.toString()
  } catch {
    return '/openapi.json'
  }
}

function getApiBasePath() {
  try {
    const url = new URL(env.apiBaseUrl)
    return url.pathname.replace(/\/$/, '')
  } catch {
    return ''
  }
}

function normalizeRoutePath(path: string) {
  if (!path.startsWith('/')) {
    return path
  }

  const basePath = getApiBasePath()

  if (!basePath || path.startsWith(`${basePath}/`) || path === basePath) {
    return path
  }

  return `${basePath}${path}`
}

function summarizeLabels(labels: string[]) {
  if (labels.length <= 2) {
    return labels.join(', ')
  }

  return `${labels.slice(0, 2).join(', ')} 외 ${labels.length - 2}건`
}

function hasRoute(catalog: RouteCatalog, requirement: DevRouteRequirement) {
  if (!catalog.isLoaded) {
    return false
  }

  const normalizedPath = normalizeRoutePath(requirement.path)
  const candidatePaths = normalizedPath.endsWith('/')
    ? [normalizedPath, normalizedPath.slice(0, -1)]
    : [normalizedPath, `${normalizedPath}/`]

  return candidatePaths.some((path) =>
    catalog.routeKeys.has(getRouteKey(requirement.method, path)),
  )
}

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function isRouteVerified(
  verifiedRoutes: Record<string, 'verified' | 'failed'>,
  requirement: DevRouteRequirement,
) {
  const directKey = getRouteKey(requirement.method, requirement.path)

  if (verifiedRoutes[directKey] === 'verified') {
    return true
  }

  const pattern = new RegExp(
    `^${escapeRegex(requirement.method)} ${escapeRegex(requirement.path).replace(/\\\{[^}]+\\\}/g, '[^/]+')}$`,
  )

  return Object.entries(verifiedRoutes).some(
    ([routeKey, state]) => state === 'verified' && pattern.test(routeKey),
  )
}

function evaluateContract(
  contract: DevSurfaceContract,
  catalog: RouteCatalog,
  verifiedRoutes: Record<string, 'verified' | 'failed'>,
): EvaluatedDevSurface {
  const liveQueries: string[] = []
  const contractQueries: string[] = []
  const sampleQueries: string[] = []
  const verifiedActions: string[] = []
  const contractActions: string[] = []
  const partialActions: string[] = []
  const pendingActions: string[] = []

  for (const query of contract.queries ?? []) {
    const routesReady = query.routes.every((route) => hasRoute(catalog, route))

    if (query.source === 'live') {
      liveQueries.push(query.label)
      continue
    }

    if (routesReady) {
      contractQueries.push(query.label)
      continue
    }

    sampleQueries.push(query.label)
  }

  for (const action of contract.actions ?? []) {
    const routeStates = action.routes.map((route) => ({
      exists: hasRoute(catalog, route),
      verified: isRouteVerified(verifiedRoutes, route),
    }))

    const existsCount = routeStates.filter((state) => state.exists).length
    const verifiedCount = routeStates.filter((state) => state.verified).length
    const readyByCatalog =
      action.matching === 'any'
        ? existsCount > 0
        : existsCount === routeStates.length && routeStates.length > 0
    const verifiedByRuntime =
      action.matching === 'any'
        ? verifiedCount > 0
        : verifiedCount === routeStates.length && routeStates.length > 0

    if (verifiedByRuntime) {
      verifiedActions.push(action.label)
      continue
    }

    if (readyByCatalog) {
      contractActions.push(action.label)
      continue
    }

    if (existsCount > 0) {
      partialActions.push(action.label)
      continue
    }

    pendingActions.push(action.label)
  }

  const hasLiveLike = liveQueries.length > 0 || verifiedActions.length > 0
  const hasContract = contractQueries.length > 0 || contractActions.length > 0
  const hasSample = sampleQueries.length > 0
  const hasPartial = partialActions.length > 0
  const hasPending = pendingActions.length > 0

  let status: DevSurfaceStatus = 'sample'

  if (hasLiveLike && !hasContract && !hasSample && !hasPartial && !hasPending) {
    status = 'live'
  } else if (hasLiveLike || hasPartial || (hasContract && (hasSample || hasPending))) {
    status = 'partial'
  } else if (hasContract && !hasSample && !hasPending) {
    status = 'contract'
  } else if (hasPending && !hasSample && !hasContract) {
    status = 'pending'
  }

  const detailParts: string[] = []

  if (liveQueries.length > 0) {
    detailParts.push(`실데이터: ${summarizeLabels(liveQueries)}`)
  }

  if (verifiedActions.length > 0) {
    detailParts.push(`실행 확인: ${summarizeLabels(verifiedActions)}`)
  }

  const contractLabels = [...contractQueries, ...contractActions]
  if (contractLabels.length > 0) {
    detailParts.push(`계약 확인: ${summarizeLabels(contractLabels)}`)
  }

  if (sampleQueries.length > 0) {
    detailParts.push(`샘플 표시: ${summarizeLabels(sampleQueries)}`)
  }

  if (partialActions.length > 0) {
    detailParts.push(`일부 라우트만 준비: ${summarizeLabels(partialActions)}`)
  }

  if (pendingActions.length > 0) {
    detailParts.push(`미구현: ${summarizeLabels(pendingActions)}`)
  }

  if (!catalog.isLoaded) {
    detailParts.push('OpenAPI 카탈로그 확인 중')
  }

  return {
    status,
    title: contract.title,
    detail: detailParts.join(' · ') || '의존 계약 정보를 아직 수집하지 못했습니다.',
  }
}

export function DevInspectorProvider({ children }: PropsWithChildren) {
  const isDevelopment = env.mode === 'development'
  const [isOverlayEnabled, setOverlayEnabledState] = useState(readStoredOverlayPreference)
  const [catalog, setCatalog] = useState<RouteCatalog>({
    isLoaded: false,
    routeKeys: new Set<string>(),
  })
  const [verifiedRoutes, setVerifiedRoutes] = useState(getRouteVerificationSnapshot)

  useEffect(() => {
    if (typeof window === 'undefined' || !isDevelopment) {
      return
    }

    window.localStorage.setItem(
      DEV_OVERLAY_STORAGE_KEY,
      isOverlayEnabled ? 'true' : 'false',
    )
  }, [isDevelopment, isOverlayEnabled])

  useEffect(() => {
    if (!isDevelopment) {
      return
    }

    let isDisposed = false

    fetch(buildOpenApiUrl())
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('OpenAPI 응답을 읽지 못했습니다.')
        }

        const document = (await response.json()) as OpenApiDocument
        const routeKeys = new Set<string>()

        for (const [path, methods] of Object.entries(document.paths ?? {})) {
          for (const method of Object.keys(methods ?? {})) {
            const upperMethod = method.toUpperCase() as DevRouteMethod | string

            if (upperMethod === 'GET' || upperMethod === 'POST') {
              routeKeys.add(getRouteKey(upperMethod as DevRouteMethod, path))
            }
          }
        }

        if (!isDisposed) {
          setCatalog({
            isLoaded: true,
            routeKeys,
          })
        }
      })
      .catch(() => {
        if (!isDisposed) {
          setCatalog({
            isLoaded: true,
            routeKeys: new Set<string>(),
          })
        }
      })

    return () => {
      isDisposed = true
    }
  }, [isDevelopment])

  useEffect(() => {
    if (!isDevelopment) {
      return
    }

    return subscribeRouteVerification(() => {
      setVerifiedRoutes(getRouteVerificationSnapshot())
    })
  }, [isDevelopment])

/**
 * 오버레이 enabled을 설정하는 함수다.
 */
  const setOverlayEnabled = (enabled: boolean) => {
    if (!isDevelopment) {
      return
    }

    setOverlayEnabledState(enabled)
  }

/**
 * 오버레이을 전환하는 함수다.
 */
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
        catalog,
        verifiedRoutes,
      }}
    >
      {children}
    </DevInspectorContext.Provider>
  )
}

export function useDevInspector() {
  return useContext(DevInspectorContext)
}

export function useEvaluatedDevSurface(contract: DevSurfaceContract) {
  const { catalog, verifiedRoutes } = useDevInspector()

  return useMemo(
    () => evaluateContract(contract, catalog, verifiedRoutes),
    [catalog, contract, verifiedRoutes],
  )
}
