import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createGetSignal, createPostAction } from '@/app/dev-inspector'
import { AppIcon } from '@/components/app-icon'
import { DevSurface } from '@/components/dev-surface'
import {
  acknowledgeAlert,
  alertsFallback,
  getAlertsPageData,
} from '@/lib/api/agribot'

function toneToTag(tone: 'accent' | 'warning' | 'danger') {
  if (tone === 'danger') {
    return 'danger'
  }

  if (tone === 'warning') {
    return 'warning'
  }

  return 'healthy'
}

export function AlertsPage() {
  const queryClient = useQueryClient()
  const alertsQuery = useQuery({
    queryKey: ['page', 'alerts'],
    queryFn: getAlertsPageData,
    initialData: alertsFallback,
    refetchInterval: 15_000,
  })
  const ackMutation = useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'alerts'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'plants'] })
    },
  })
  const page = alertsQuery.data
  const querySource = (path: string) => page.debug.querySources[path] ?? 'fallback'
  const pendingItems = page.items.filter((item) => !item.acknowledged)
  const feedbackMessage = ackMutation.isSuccess
    ? ackMutation.data
    : ackMutation.isError
      ? ackMutation.error.message
      : null

  return (
    <div className="screen">
      <section className="hero-grid hero-grid--alerts">
        <DevSurface
          as="article"
          className="hero-panel hero-panel--warning"
          contract={{
            title: '알림 센터 요약',
            queries: [
              createGetSignal('알림 목록', querySource('/alerts'), '/alerts'),
            ],
            actions: [
              createPostAction('읽음 처리', ['/alerts/{alert_id}/ack']),
            ],
          }}
        >
          <div className="hero-topline">
            <span className="panel-kicker">알림 센터</span>
            <span className="live-pill live-pill--soft">
              {page.source === 'live' ? '실시간 알림 반영' : '준비 데이터 알림'}
            </span>
          </div>
          <h3 className="hero-title">{page.summary}</h3>
          <p className="hero-copy">
            `alerts`, `alerts/{'{id}'}/ack`, `realtime/live` 흐름을 기준으로 병해와 설비 경고를 한 화면에 모았습니다.
          </p>
          <div className="hero-stat-row">
            <div className="hero-stat">
              <span className="hero-stat-label">미처리 알림</span>
              <strong>{page.unreadCount}</strong>
            </div>
            <div className="hero-stat">
              <span className="hero-stat-label">심각 알림</span>
              <strong>{page.criticalCount}</strong>
            </div>
          </div>
        </DevSurface>

        <DevSurface
          as="article"
          className="hero-panel hero-panel--compact"
          contract={{
            title: '알림 운영 가이드',
            queries: [
              createGetSignal('알림 목록', querySource('/alerts'), '/alerts'),
            ],
          }}
        >
          <div className="status-stack">
            <div className="status-inline">
              <AppIcon className="status-inline-icon" filled name="warning" />
              <span>병해 탐지와 설비 경고를 같은 우선순위 기준으로 검토합니다.</span>
            </div>
            <div className="status-inline">
              <AppIcon className="status-inline-icon" name="task_alt" />
              <span>읽음 처리를 해두면 대시보드와 작물 화면 큐도 함께 정리됩니다.</span>
            </div>
          </div>
          {feedbackMessage ? <p className="muted">{feedbackMessage}</p> : null}
        </DevSurface>
      </section>

      <section className="content-grid content-grid--alerts">
        <DevSurface
          as="article"
          className="panel"
          contract={{
            title: '알림 타임라인',
            queries: [
              createGetSignal('알림 목록', querySource('/alerts'), '/alerts'),
            ],
            actions: [
              createPostAction('읽음 처리', ['/alerts/{alert_id}/ack']),
            ],
          }}
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">타임라인</span>
              <h3 className="section-title">전체 알림 흐름</h3>
              <p className="section-description">
                심각도, 위치, 발생 시각 기준으로 최근 알림을 정렬했습니다.
              </p>
            </div>
          </div>

          <div className="timeline">
            {page.items.map((item) => (
              <article className={`timeline-item timeline-item--${item.tone}`} key={item.id}>
                <div className={`timeline-marker timeline-marker--${item.tone}`} />
                <div className="timeline-body">
                  <div className="split-row">
                    <div>
                      <h4 className="list-title">{item.title}</h4>
                      <p className="list-meta">{item.location}</p>
                    </div>
                    <span className={`table-tag table-tag--${toneToTag(item.tone)}`}>
                      {item.acknowledged ? '읽음' : '미처리'}
                    </span>
                  </div>
                  <p className="timeline-copy">{item.detail}</p>
                  <div className="timeline-meta">
                    <span>{item.meta}</span>
                    <button
                      className="ghost-chip"
                      disabled={item.acknowledged || ackMutation.isPending}
                      onClick={() => {
                        ackMutation.mutate(item.id)
                      }}
                      type="button"
                    >
                      {item.acknowledged ? '처리됨' : '읽음 처리'}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </DevSurface>

        <DevSurface
          as="article"
          className="panel"
          contract={{
            title: '우선 대응 큐',
            queries: [
              createGetSignal('알림 목록', querySource('/alerts'), '/alerts'),
            ],
          }}
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">우선 대응</span>
              <h3 className="section-title">미처리 알림 큐</h3>
              <p className="section-description">
                아직 읽지 않은 알림만 따로 모아 운영자가 먼저 봐야 하는 항목을 줄였습니다.
              </p>
            </div>
          </div>

          <div className="stacked-list">
            {(pendingItems.length > 0 ? pendingItems : page.items.slice(0, 2)).map((item) => (
              <article className="queue-card" key={item.id}>
                <div className="split-row">
                  <span className={`table-tag table-tag--${toneToTag(item.tone)}`}>
                    {item.tone === 'danger' ? '심각' : item.tone === 'warning' ? '주의' : '정보'}
                  </span>
                  <span className="list-meta">{item.meta}</span>
                </div>
                <h4 className="list-title">{item.title}</h4>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
        </DevSurface>
      </section>
    </div>
  )
}
