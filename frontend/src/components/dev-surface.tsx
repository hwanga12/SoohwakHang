import type { PropsWithChildren } from 'react'
import {
  useDevInspector,
  type DevSurfaceStatus,
} from '@/app/dev-inspector'

type DevSurfaceProps = PropsWithChildren<{
  as?: 'article' | 'aside' | 'div' | 'section'
  className?: string
  status: DevSurfaceStatus
  title: string
  detail: string
}>

const statusLabels: Record<DevSurfaceStatus, string> = {
  live: '실연동',
  sample: '발표용 샘플',
  partial: '부분 연동',
  stub: '요청 수신만 구현',
  pending: '미구현',
}

export function DevSurface({
  as = 'article',
  children,
  className = '',
  status,
  title,
  detail,
}: DevSurfaceProps) {
  const { isOverlayEnabled } = useDevInspector()
  const Component = as

  return (
    <Component
      className={`${className}${isOverlayEnabled ? ` dev-surface dev-surface--${status}` : ''}`}
      data-dev-status={status}
    >
      {children}
      {isOverlayEnabled ? (
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
