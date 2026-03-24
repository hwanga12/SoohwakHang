import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AppIcon } from '@/components/app-icon'
import { DevSurface } from '@/components/dev-surface'
import { MetricCard } from '@/components/metric-card'
import {
  dashboardFallback,
  getDashboardPageData,
  sendRobotControlAction,
} from '@/lib/api/agribot'
import { MockupImage } from '@/components/mockup-image'

export function DashboardPage() {
  const queryClient = useQueryClient()
  const dashboardQuery = useQuery({
    queryKey: ['page', 'dashboard'],
    queryFn: getDashboardPageData,
    initialData: dashboardFallback,
    refetchInterval: 20_000,
  })
  const controlMutation = useMutation({
    mutationFn: sendRobotControlAction,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
    },
  })
  const page = dashboardQuery.data
  const feedbackMessage = controlMutation.isSuccess
    ? controlMutation.data
    : controlMutation.isError
      ? controlMutation.error.message
      : null

  return (
    <div className="screen">
      <section className="hero-grid hero-grid--dashboard">
        <DevSurface
          as="article"
          className="hero-panel hero-panel--accent"
          detail="dashboard/summary, robot/status, environment/latest, alerts 응답이 아직 고정되어 있어 발표용 샘플 데이터로 운영 서사를 재현합니다."
          status="sample"
          title="운영 요약 패널"
        >
          <div className="hero-topline">
            <span className="panel-kicker">운영 상태</span>
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
          <div style={{ marginTop: '16px' }}>
            <MockupImage
              alt="온실 전경 시뮬레이션"
              className="hero-photo"
              height={160}
              src="/mock-images/greenhouse-overview.png"
            />
          </div>
        </DevSurface>

        <DevSurface
          as="article"
          className="hero-panel hero-panel--compact"
          detail="robot/commands와 mission 명령은 요청 수신까지 연결돼 있지만, 실제 로봇 상태 반영과 결과 피드백은 아직 ROS 런타임과 완전히 이어지지 않았습니다."
          status="stub"
          title="빠른 로봇 제어"
        >
          <div className="status-stack">
            <div className="status-pill-row">
              <span className="panel-kicker">배터리</span>
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
            <button
              className="action-button action-button--danger"
              disabled={controlMutation.isPending}
              onClick={() => {
                controlMutation.mutate('emergency')
              }}
              type="button"
            >
              <AppIcon filled name="emergency_home" />
              비상 정지
            </button>
            <button
              className="action-button action-button--soft"
              disabled={controlMutation.isPending}
              onClick={() => {
                controlMutation.mutate('resume')
              }}
              type="button"
            >
              <AppIcon name="play_circle" />
              재개
            </button>
            <button
              className="action-button action-button--soft"
              disabled={controlMutation.isPending}
              onClick={() => {
                controlMutation.mutate('pause')
              }}
              type="button"
            >
              <AppIcon name="pause_circle" />
              일시정지
            </button>
          </div>
          {feedbackMessage ? <p className="muted">{feedbackMessage}</p> : null}

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
        </DevSurface>
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
        <DevSurface
          as="article"
          className="panel"
          detail="alerts와 realtime 이벤트 스트림이 아직 완전한 목록/타임라인 응답을 제공하지 않아 최근 활동은 발표용 이벤트 시퀀스로 채워집니다."
          status="sample"
          title="최근 활동 피드"
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">실시간 피드</span>
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
        </DevSurface>

        <DevSurface
          as="article"
          className="panel"
          detail="운영 큐는 문서상의 역할 분담과 실제 데모 흐름을 반영한 샘플 카드입니다."
          status="sample"
          title="운영 큐"
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">운영 큐</span>
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
        </DevSurface>
      </section>

      <DevSurface
        as="section"
        className="panel"
        detail="zones 엔드포인트는 최소 구조만 내려오고, 구역 상태 해석과 우선순위 문장은 아직 프론트 fallback 로직에서 보강합니다."
        status="partial"
        title="구역 상태 요약"
      >
        <div className="section-head">
          <div>
            <span className="section-eyebrow">구역 요약</span>
            <h3 className="section-title">온실 구역 상태</h3>
            <p className="section-description">
              `zones`, `alerts`, `environment/latest` 관점에서 구역 단위 우선순위를 읽도록 구성했습니다.
            </p>
          </div>
          <span className="table-tag table-tag--healthy">
            {page.source === 'live' ? '실 API' : '준비 데이터'}
          </span>
        </div>

        <div className="zone-grid">
          {page.zones.map((zone) => (
            <article className={`zone-card zone-card--${zone.tone}`} key={zone.id}>
              <div className="split-row">
                <div>
                  <span className="panel-kicker">{zone.id}</span>
                  <h4 className="list-title">{zone.name}</h4>
                </div>
                <span className={`table-tag table-tag--${zone.tone === 'critical' ? 'danger' : zone.tone}`}>
                  {zone.tone === 'healthy' ? '안정' : zone.tone === 'warning' ? '확인 필요' : '우선 대응'}
                </span>
              </div>
              <p>{zone.summary}</p>
            </article>
          ))}
        </div>
      </DevSurface>
    </div>
  )
}
