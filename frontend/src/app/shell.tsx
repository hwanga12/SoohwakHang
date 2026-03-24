import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { navigationItems } from '@/app/navigation'
import { env } from '@/config/env'

function matchCurrentPath(path: string, pathname: string) {
  if (path === '/') {
    return pathname === '/'
  }

  return pathname.startsWith(path)
}

export default function AppShell() {
  const location = useLocation()
  const currentItem =
    navigationItems.find((item) =>
      matchCurrentPath(item.path, location.pathname),
    ) ?? navigationItems[0]

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-kicker">AGRIBOT OPS</span>
          <h1 className="brand-title">{env.appName}</h1>
          <p className="brand-copy">
            라우팅, 공통 레이아웃, API/실시간 연결 설정을 포함한 초기 골격
          </p>
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
              <span className="nav-label">{item.label}</span>
              <span className="nav-caption">{item.caption}</span>
            </NavLink>
          ))}
        </nav>

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
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <span className="page-kicker">{currentItem.label}</span>
            <h2 className="page-title">{currentItem.caption}</h2>
            <p className="muted">{currentItem.description}</p>
          </div>
          <span className="mode-pill">Base Setup Ready</span>
        </header>

        <Outlet />
      </main>
    </div>
  )
}
