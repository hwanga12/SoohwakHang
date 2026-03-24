import { useQuery } from '@tanstack/react-query'
import { AppIcon } from '@/components/app-icon'
import { MetricCard } from '@/components/metric-card'
import {
  dashboardFallback,
  getDashboardPageData,
} from '@/lib/api/agribot'

export function DashboardPage() {
  const dashboardQuery = useQuery({
    queryKey: ['page', 'dashboard'],
    queryFn: getDashboardPageData,
    initialData: dashboardFallback,
    refetchInterval: 20_000,
  })
  const page = dashboardQuery.data

  return (
    <div className="screen">
      <section className="hero-grid hero-grid--dashboard">
        <article className="hero-panel hero-panel--accent">
          <div className="hero-topline">
            <span className="panel-kicker">System Status</span>
            <span className="live-pill live-pill--soft">{page.heroStatus}</span>
          </div>
          <h3 className="hero-title">로봇 상태, 환경, 병해 알림을 운영자가 한 번에 읽는 메인 화면입니다.</h3>
          <p className="hero-copy">
            `dashboard/summary`, `robots/status`, `alerts`, `environment/latest`,
            `realtime/live` 기준으로 필요한 카드 밀도를 한 화면에 맞췄습니다.
          </p>
          <div className="hero-stat-row">
            <div className="hero-stat">
              <span className="hero-stat-label">현재 위치</span>
              <strong>{page.location}</strong>
            </div>
            <div className="hero-stat">
              <span className="hero-stat-label">활성 작업</span>
              <strong>{page.activeTask}</strong>
            </div>
          </div>
        </article>

        <article className="hero-panel hero-panel--compact">
          <div className="status-stack">
            <div className="status-pill-row">
              <span className="panel-kicker">Battery</span>
              <span className="table-tag table-tag--healthy">{page.battery}</span>
            </div>
            <div className="status-inline">
              <AppIcon className="status-inline-icon" filled name="battery_charging_80" />
              <span>{page.batteryMeta}</span>
            </div>
            <div className="status-inline">
              <AppIcon className="status-inline-icon" name="precision_manufacturing" />
              <span>{page.robotLabel}</span>
            </div>
          </div>

          <div className="quick-action-grid">
            <button className="action-button action-button--danger" type="button">
              <AppIcon filled name="emergency_home" />
              비상 정지
            </button>
            <button className="action-button action-button--soft" type="button">
              <AppIcon name="play_circle" />
              재개
            </button>
            <button className="action-button action-button--soft" type="button">
              <AppIcon name="pause_circle" />
              일시정지
            </button>
          </div>

          <div className="mini-metric-row">
            {page.environmentStats.map((stat) => (
              <article className="mini-metric-card" key={stat.label}>
                <div className="split-row">
                  <span className="mini-metric-label">{stat.label}</span>
                  <span className="mini-metric-delta">{stat.delta}</span>
                </div>
                <strong className="mini-metric-value">{stat.value}</strong>
              </article>
            ))}
          </div>
        </article>
      </section>

      <section className="metric-row">
        {page.metrics.map((card) => (
          <MetricCard
            key={card.label}
            label={card.label}
            meta={card.meta}
            tone={card.tone}
            value={card.value}
          />
        ))}
      </section>

      <section className="content-grid content-grid--dashboard">
        <article className="panel">
          <div className="section-head">
            <div>
              <span className="section-eyebrow">Live Feed</span>
              <h3 className="section-title">최근 활동</h3>
              <p className="section-description">
                운영 개입이 필요한 이벤트만 짧고 선명하게 남깁니다.
              </p>
            </div>
            <button className="ghost-chip" type="button">
              {dashboardQuery.isFetching ? '동기화 중' : '일지 보기'}
            </button>
          </div>

          <div className="stacked-list">
            {page.events.map((event) => (
              <article className="log-item" key={event.title}>
                <span className={`log-dot log-dot--${event.tone}`} />
                <div className="log-copy">
                  <div className="split-row">
                    <h4 className="list-title">{event.title}</h4>
                    <span className="list-meta">{event.time}</span>
                  </div>
                  <p>{event.detail}</p>
                </div>
              </article>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="section-head">
            <div>
              <span className="section-eyebrow">Snapshot</span>
              <h3 className="section-title">운영 포인트</h3>
              <p className="section-description">
                오늘 당장 확인해야 하는 운영 큐를 별도 카드로 분리했습니다.
              </p>
            </div>
          </div>

          <div className="stacked-list">
            {page.queue.map((item) => (
              <article className="queue-card" key={`${item.label}-${item.title}`}>
                <span className={`table-tag table-tag--${item.tone}`}>{item.label}</span>
                <h4 className="list-title">{item.title}</h4>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
        </article>
      </section>
    </div>
  )
}
