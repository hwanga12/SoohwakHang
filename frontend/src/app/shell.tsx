import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { AppIcon } from '@/components/app-icon'
import { navigationItems } from '@/app/navigation'
import { env } from '@/config/env'
import { useLiveStatus } from '@/hooks/use-live-status'

function matchCurrentPath(path: string, pathname: string) {
  if (path === '/') {
    return pathname === '/'
  }

  return pathname.startsWith(path)
}

function formatModeLabel(mode: string) {
  if (mode === 'development') {
    return '개발'
  }

  if (mode === 'production') {
    return '운영'
  }

  return mode
}

export default function AppShell() {
  const [showDevInfo, setShowDevInfo] = useState(false)
  const location = useLocation()
  const liveStatus = useLiveStatus()
  const modeLabel = formatModeLabel(env.mode)
  const currentItem =
    navigationItems.find((item) =>
      matchCurrentPath(item.path, location.pathname),
    ) ?? navigationItems[0]
  const liveLabel =
    liveStatus === 'connected'
      ? '실시간 파이프라인 연결'
      : liveStatus === 'connecting'
        ? '실시간 연결 시도 중'
        : '실시간 연결 안 됨'

  return (
    <div className="app-shell">
      <header className="shell-header">
        <div className="shell-brand">
          <div className="brand-mark">
            <AppIcon className="brand-mark-icon" filled name="eco" />
          </div>
          <div style={{ position: 'relative' }}>
            <span className="brand-kicker">스마트 온실 운영</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 className="brand-title">{env.appName}</h1>
              <AppIcon name="potted_plant" className="brand-mark-icon" style={{ color: 'var(--primary)', width: '24px', height: '24px' }} />
            </div>
          </div>
        </div>

        <div className="shell-header-actions">
          <div 
            className={`live-pill${liveStatus === 'connected' ? '' : ' live-pill--soft'}`}
            style={liveStatus === 'connected' ? { backgroundColor: 'var(--primary-soft)', color: 'var(--primary)', border: '2px solid var(--primary-soft)' } : { backgroundColor: 'var(--secondary-soft)', color: 'var(--secondary)', border: '2px solid var(--secondary-soft)' }}
          >
            <span className="live-dot" style={liveStatus === 'connected' ? { background: 'var(--primary)' } : { background: 'var(--secondary)' }} />
            {liveLabel}
          </div>
          <NavLink
            aria-label="알림 센터"
            className={`icon-button${matchCurrentPath('/alerts', location.pathname) ? ' icon-button--active' : ''}`}
            to="/alerts"
          >
            <AppIcon name="notifications" />
          </NavLink>
        </div>
      </header>

      <div className="shell-layout">
        <aside className="sidebar">

          <nav aria-label="주요 메뉴" className="nav-list">
            {navigationItems.map((item) => (
              <NavLink
                key={item.path}
                className={({ isActive }) =>
                  `nav-item${isActive ? ' active' : ''}`
                }
                end={item.path === '/'}
                to={item.path}
              >
                <AppIcon
                  className="nav-icon"
                  filled={matchCurrentPath(item.path, location.pathname)}
                  name={item.icon}
                />
                <div className="nav-copy">
                  <span className="nav-label">{item.label}</span>
                  <span className="nav-caption">{item.caption}</span>
                </div>
              </NavLink>
            ))}
          </nav>

          {env.mode === 'development' && (
            <div style={{ position: 'relative', marginTop: 'auto' }}>
              {showDevInfo && (
                <div className="sidebar-panel sidebar-panel--muted" style={{ position: 'absolute', bottom: '100%', left: 0, right: 0, marginBottom: '8px', zIndex: 50, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className="panel-kicker">시스템 진단 정보</span>
                    <button onClick={() => setShowDevInfo(false)} style={{ color: 'var(--muted)', fontSize: '1rem' }}>✕</button>
                  </div>
                  <dl className="sidebar-meta" style={{ marginTop: '12px' }}>
                    <div>
                      <dt>모드</dt>
                      <dd>{modeLabel}</dd>
                    </div>
                    <div>
                      <dt>REST API</dt>
                      <dd className="code-chip" style={{ wordBreak: 'break-all', display: 'block' }}>{env.apiBaseUrl}</dd>
                    </div>
                    <div>
                      <dt>웹소켓</dt>
                      <dd className="code-chip" style={{ wordBreak: 'break-all', display: 'block' }}>{env.wsUrl}</dd>
                    </div>
                  </dl>
                </div>
              )}
              <button 
                className={`nav-item ${showDevInfo ? 'active' : ''}`}
                onClick={() => setShowDevInfo(!showDevInfo)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', background: 'transparent', cursor: 'pointer', border: 'none' }}
              >
                <AppIcon className="nav-icon" name="router" />
                <div className="nav-copy" style={{ textAlign: 'left' }}>
                  <span className="nav-label">시스템 정보 (개발용)</span>
                </div>
              </button>
            </div>
          )}
        </aside>

        <main className="workspace">
          <div className="workspace-scroll">
            <header className="workspace-header">
              <div>
                <span className="page-kicker">{currentItem.label}</span>
                <h2 className="page-title">{currentItem.caption}</h2>
                <p className="muted">{currentItem.description}</p>
              </div>
              <div className="workspace-pills">
                <span className="mode-pill">실시간 운영</span>
                <span className="mode-pill mode-pill--ghost">
                  {modeLabel}
                </span>
              </div>
            </header>
            <Outlet />
          </div>
        </main>
      </div>

      <nav aria-label="모바일 메뉴" className="mobile-dock">
        {navigationItems.map((item) => (
          <NavLink
            key={item.path}
            className={({ isActive }) =>
              `mobile-dock-item${isActive ? ' active' : ''}`
            }
            end={item.path === '/'}
            to={item.path}
          >
            <AppIcon
              className="mobile-dock-icon"
              filled={matchCurrentPath(item.path, location.pathname)}
              name={item.icon}
            />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
