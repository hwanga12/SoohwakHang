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

export default function AppShell() {
  const location = useLocation()
  const liveStatus = useLiveStatus()
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
          <div>
            <span className="brand-kicker">Smart Greenhouse Suite</span>
            <h1 className="brand-title">{env.appName}</h1>
          </div>
        </div>

        <div className="shell-header-actions">
          <div className={`live-pill${liveStatus === 'connected' ? '' : ' live-pill--soft'}`}>
            <span className="live-dot" />
            {liveLabel}
          </div>
          <button className="icon-button" type="button">
            <AppIcon name="notifications" />
          </button>
        </div>
      </header>

      <div className="shell-layout">
        <aside className="sidebar">
          <div className="sidebar-panel">
            <span className="panel-kicker">Mission Frame</span>
            <h2 className="sidebar-title">{currentItem.caption}</h2>
            <p className="sidebar-copy">{currentItem.description}</p>
          </div>

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

          <div className="sidebar-panel sidebar-panel--muted">
            <span className="panel-kicker">Connection</span>
            <dl className="sidebar-meta">
              <div>
                <dt>Mode</dt>
                <dd>{env.mode}</dd>
              </div>
              <div>
                <dt>REST API</dt>
                <dd className="code-chip">{env.apiBaseUrl}</dd>
              </div>
              <div>
                <dt>WebSocket</dt>
                <dd className="code-chip">{env.wsUrl}</dd>
              </div>
            </dl>
          </div>
        </aside>

        <main className="workspace">
          <header className="workspace-header">
            <div>
              <span className="page-kicker">{currentItem.label}</span>
              <h2 className="page-title">{currentItem.caption}</h2>
              <p className="muted">{currentItem.description}</p>
            </div>
            <div className="workspace-pills">
              <span className="mode-pill">Live Ops</span>
              <span className="mode-pill mode-pill--ghost">
                {env.mode.toUpperCase()}
              </span>
            </div>
          </header>

          <div className="workspace-scroll">
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
