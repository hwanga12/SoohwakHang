/*
 * 이 모듈은 프론트엔드 앱 골격에서 공통 앱 셸 레이아웃을 구성한다.
 */
import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { AppIcon } from '@/components/app-icon'
import { navigationItems } from '@/app/navigation'
import { useDevInspector } from '@/app/dev-inspector'
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

/**
 * APP 앱 셸 화면 조각을 렌더링하는 컴포넌트다.
 */
export default function AppShell() {
  const [showDevInfo, setShowDevInfo] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const liveStatus = useLiveStatus()
  const { isDevelopment, isOverlayEnabled, toggleOverlay } = useDevInspector()
  const modeLabel = formatModeLabel(env.mode)

  const liveLabel =
    liveStatus === 'connected'
      ? '실시간 파이프라인 연결'
      : liveStatus === 'connecting'
        ? '실시간 연결 시도 중'
        : '실시간 연결 안 됨'
  const villageWeather =
    liveStatus === 'connected'
      ? '햇살 좋은 운영일'
      : liveStatus === 'connecting'
        ? '산책로 점검 중'
        : '조용한 준비 시간'

  return (
    <div className="app-shell">
      <div aria-hidden="true" className="shell-atmosphere">
        <span className="shell-cloud shell-cloud--one" />
        <span className="shell-cloud shell-cloud--two" />
        <span className="shell-leaf shell-leaf--one" />
        <span className="shell-leaf shell-leaf--two" />
      </div>

      <header className="shell-header">
        <div className="shell-brand">
          <div className="brand-mark">
            <AppIcon className="brand-mark-icon" filled name="eco" />
          </div>
          <div className="brand-copy">
            <span className="brand-kicker">스마트 온실 운영</span>
            <div className="brand-heading-row">
              <h1 className="brand-title">{env.appName}</h1>
              <AppIcon
                className="brand-sprout"
                name="potted_plant"
                style={{ color: 'var(--primary)', width: '24px', height: '24px' }}
              />
            </div>
            <p className="brand-note">
              밭, 로봇, 작물, 수확 흐름을 포근한 마을 게시판처럼 한눈에 정리했습니다.
            </p>
          </div>
        </div>

        <div className="shell-header-actions">
          <div className="season-chip">
            <span className="season-chip__label">오늘의 온실 날씨</span>
            <strong>{villageWeather}</strong>
          </div>
          <div 
            className={`live-pill${liveStatus === 'connected' ? '' : ' live-pill--soft'}`}
            style={liveStatus === 'connected' ? { backgroundColor: 'var(--primary-soft)', color: 'var(--primary)', border: '2px solid var(--primary-soft)' } : { backgroundColor: 'var(--secondary-soft)', color: 'var(--secondary)', border: '2px solid var(--secondary-soft)' }}
          >
            <span className="live-dot" style={liveStatus === 'connected' ? { background: 'var(--primary)' } : { background: 'var(--secondary)' }} />
            {liveLabel}
          </div>
          <button
            aria-label="알림 센터"
            className={`icon-button${matchCurrentPath('/alerts', location.pathname) ? ' icon-button--active' : ''}`}
            onClick={() => {
              if (location.pathname === '/alerts') {
                navigate(-1)
              } else {
                navigate('/alerts')
              }
            }}
            type="button"
          >
            <AppIcon name="notifications" />
          </button>
        </div>
      </header>

      <div className="shell-layout">
        <aside className="sidebar">
          <section className="sidebar-panel island-board">
            <div>
              <span className="panel-kicker">마을 게시판</span>
              <h2 className="sidebar-title">오늘의 온실 산책</h2>
            </div>
            <p className="sidebar-copy">
              필요한 화면을 골라 밭 상태, 순찰 동선, 자동 제어 흐름을 차례대로 둘러보세요.
            </p>
            <div className="village-chip-row">
              <span className="village-chip">
                <AppIcon name="potted_plant" />
                작물 둘러보기
              </span>
              <span className="village-chip">
                <AppIcon name="navigation" />
                로봇 산책로 점검
              </span>
              <span className="village-chip">
                <AppIcon name="water_drop" />
                급수 추천 확인
              </span>
            </div>
          </section>

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

          <section className="sidebar-panel sidebar-panel--muted field-note">
            <div className="split-row">
              <div>
                <span className="panel-kicker">오늘의 메모</span>
                <h3 className="sidebar-title sidebar-title--compact">차분한 운영 루틴</h3>
              </div>
              <span className="table-tag table-tag--healthy">{modeLabel}</span>
            </div>
            <div className="field-note-list">
              <div className="field-note-item">
                <AppIcon name="task_alt" />
                미처리 알림과 검수 대상을 먼저 확인합니다.
              </div>
              <div className="field-note-item">
                <AppIcon name="water_drop" />
                밭 탭에서 물주기와 영양 보충 메모를 확인합니다.
              </div>
              <div className="field-note-item">
                <AppIcon name="rocket_launch" />
                수확 또는 순찰 미션을 차분히 이어갑니다.
              </div>
            </div>
          </section>

          {isDevelopment && (
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
                  <div className="sidebar-panel-section">
                    <div className="split-row">
                      <div>
                        <span className="panel-kicker">개발자 오버레이</span>
                        <p className="muted">같은 화면 위에서 샘플 데이터와 미연동 영역만 강조해서 보여줍니다.</p>
                      </div>
                      <button
                        className={`ghost-chip${isOverlayEnabled ? ' ghost-chip--active' : ''}`}
                        onClick={toggleOverlay}
                        type="button"
                      >
                        {isOverlayEnabled ? '끄기' : '켜기'}
                      </button>
                    </div>
                    <div className="dev-legend">
                      <span className="dev-legend-item dev-legend-item--live">실연동</span>
                      <span className="dev-legend-item dev-legend-item--sample">샘플 표시</span>
                      <span className="dev-legend-item dev-legend-item--partial">혼합 상태</span>
                      <span className="dev-legend-item dev-legend-item--contract">계약 확인</span>
                      <span className="dev-legend-item dev-legend-item--pending">미구현</span>
                    </div>
                  </div>
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
                  <span className="nav-caption">
                    {isOverlayEnabled ? '오버레이 표시 중' : '오버레이 숨김'}
                  </span>
                </div>
              </button>
            </div>
          )}
        </aside>

        <main className="workspace">
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
