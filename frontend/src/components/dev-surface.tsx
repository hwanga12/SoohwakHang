/*
 * 이 컴포넌트는 프론트엔드 화면에서 개발 점검용 표면 역할을 맡는다.
 */
import type { PropsWithChildren } from 'react'
import {
  useEvaluatedDevSurface,
  useDevInspector,
  type DevSurfaceContract,
  type DevSurfaceStatus,
} from '@/app/dev-inspector'

type BaseProps = PropsWithChildren<{
  as?: 'article' | 'aside' | 'div' | 'section'
  className?: string
  hideNote?: boolean
}>

type DevSurfaceProps = BaseProps & (
  | {
      contract: DevSurfaceContract
      detail?: never
      status?: never
      title?: never
    }
  | {
      contract?: never
      detail: string
      status: DevSurfaceStatus
      title: string
    }
)

const statusLabels: Record<DevSurfaceStatus, string> = {
  live: '실연동',
  sample: '샘플 표시',
  partial: '혼합 상태',
  contract: '계약 확인',
  pending: '미구현',
}

/**
 * DEV 표면 화면 조각을 렌더링하는 컴포넌트다.
 */
export function DevSurface(props: DevSurfaceProps) {
  const {
    as = 'article',
    children,
    className = '',
    hideNote = false,
  } = props
  const fallbackTitle =
    'title' in props && typeof props.title === 'string' ? props.title : ''
  const fallbackStatus =
    'status' in props && typeof props.status === 'string' ? props.status : 'sample'
  const fallbackDetail =
    'detail' in props && typeof props.detail === 'string' ? props.detail : ''
  const evaluatedContract = useEvaluatedDevSurface(
    props.contract ?? {
      title: fallbackTitle,
      queries: [],
      actions: [],
    },
  )
  const status = props.contract ? evaluatedContract.status : fallbackStatus
  const title = props.contract ? evaluatedContract.title : fallbackTitle
  const detail = props.contract ? evaluatedContract.detail : fallbackDetail
  const { isOverlayEnabled } = useDevInspector()
  const Component = as

  return (
    <Component
      className={`${className}${isOverlayEnabled ? ` dev-surface dev-surface--${status}` : ''}`}
      data-dev-status={status}
    >
      {children}
      {isOverlayEnabled && !hideNote ? (
        <div className="dev-surface-note">
          <span className={`dev-surface-badge dev-surface-badge--${status}`}>
            {statusLabels[status]}
          </span>
          <div className="dev-surface-copy">
            <strong>{title}</strong>
            <p>{detail}</p>
          </div>
        </div>
      ) : null}
    </Component>
  )
}
