import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AppIcon } from '@/components/app-icon'
import {
  approveWateringRecommendation,
  environmentFallback,
  getEnvironmentPageData,
  triggerNutrientInjection,
} from '@/lib/api/agribot'

function normalizePercent(value?: string) {
  if (!value) {
    return '80%'
  }

  if (value.includes('%')) {
    return value
  }

  const parsed = Number(value)
  if (Number.isFinite(parsed) && parsed <= 1) {
    return `${Math.round(parsed * 100)}%`
  }

  return `${value}%`
}

export function EnvironmentPage() {
  const queryClient = useQueryClient()
  const environmentQuery = useQuery({
    queryKey: ['page', 'environment'],
    queryFn: getEnvironmentPageData,
    initialData: environmentFallback,
    refetchInterval: 15_000,
  })
  const approveMutation = useMutation({
    mutationFn: approveWateringRecommendation,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'environment'] })
    },
  })
  const nutrientMutation = useMutation({
    mutationFn: triggerNutrientInjection,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'environment'] })
    },
  })
  const page = environmentQuery.data
  const feedbackMessage = approveMutation.isSuccess
    ? approveMutation.data
    : nutrientMutation.isSuccess
      ? nutrientMutation.data
      : approveMutation.isError
        ? approveMutation.error.message
        : nutrientMutation.isError
          ? nutrientMutation.error.message
          : null

  return (
    <div className="screen">
      <section className="hero-grid hero-grid--environment">
        <article className="hero-panel hero-panel--environment">
          <div className="hero-topline">
            <div>
              <span className="panel-kicker">정밀 제어</span>
              <h3 className="hero-title">{page.recommendation}</h3>
            </div>
            <span className="live-pill">
              {page.source === 'live' ? '실시간 장치 상태' : '준비 데이터 장치 상태'}
            </span>
          </div>
          <div className="recommendation-strip">
            <div className="recommendation-icon">
              <AppIcon filled name="lightbulb" />
            </div>
            <div className="recommendation-copy">
              <span className="section-eyebrow">추천 알림</span>
              <strong>{page.recommendation}</strong>
            </div>
            <div className="recommendation-actions">
              <button
                className="action-button"
                disabled={approveMutation.isPending}
                onClick={() => {
                  approveMutation.mutate()
                }}
                type="button"
              >
                {approveMutation.isPending ? '전송 중...' : '승인'}
              </button>
              <button className="ghost-chip" type="button">
                무시
              </button>
            </div>
          </div>
        </article>
      </section>

      <section className="metric-row metric-row--compact">
        {page.metrics.map((card) => (
          <article className={`metric-card metric-card--${card.tone}`} key={card.label}>
            <span className="metric-label">{card.label}</span>
            <p className="metric-value">{card.value}</p>
            <p className="metric-meta">{card.meta}</p>
          </article>
        ))}
      </section>

      <section className="content-grid content-grid--environment">
        <article className="panel">
          <div className="section-head">
            <div>
              <span className="section-eyebrow">장치 제어</span>
              <h3 className="section-title">기기 제어</h3>
              <p className="section-description">
                `iot/devices`, `actuations/recommendations`, `actuations/*` 동선을 기준으로
                장치 카드 구조를 정리했습니다.
              </p>
            </div>
          </div>

          <div className="device-grid">
            {page.devices.map((device) => (
              <article className="device-card" key={device.name}>
                <div className="split-row">
                  <div className={`device-icon device-icon--${device.accent}`}>
                    <AppIcon name={device.icon} />
                  </div>
                  {device.action === 'toggle' ? (
                    <span className="device-toggle is-active" />
                  ) : null}
                  {device.action === 'slider' ? (
                    <span className="table-tag table-tag--healthy">
                      {normalizePercent(device.value)}
                    </span>
                  ) : null}
                  {device.action === 'button' ? (
                    <span className="table-tag table-tag--warning">대기</span>
                  ) : null}
                </div>
                <div className="device-copy">
                  <h4 className="list-title">{device.name}</h4>
                  <p className="list-meta">{device.detail}</p>
                </div>
                {device.action === 'slider' ? (
                  <div className="slider-track">
                    <span
                      className="slider-fill"
                      style={{ width: normalizePercent(device.value) }}
                    />
                  </div>
                ) : null}
                {device.action === 'fan' ? (
                  <div className="segmented-row">
                    <button className="segment-button" type="button">
                      약
                    </button>
                    <button className="segment-button is-active" type="button">
                      중
                    </button>
                    <button className="segment-button" type="button">
                      강
                    </button>
                  </div>
                ) : null}
                {device.action === 'button' ? (
                  <button
                    className="action-button action-button--warning"
                    disabled={nutrientMutation.isPending}
                    onClick={() => {
                      nutrientMutation.mutate()
                    }}
                    type="button"
                  >
                    {nutrientMutation.isPending ? '투입 중...' : '영양제 투입'}
                  </button>
                ) : null}
              </article>
            ))}
          </div>
          {feedbackMessage ? <p className="muted">{feedbackMessage}</p> : null}

          <div className="panel-divider" />

          <div className="section-head">
            <div>
              <span className="section-eyebrow">승인 큐</span>
              <h3 className="section-title">제어 추천 대기열</h3>
              <p className="section-description">
                자동 제어 권고를 운영자가 검토하고 승인할 수 있도록 별도 큐로 분리했습니다.
              </p>
            </div>
          </div>

          <div className="recommendation-list">
            {page.recommendations.map((item) => (
              <article className="queue-card" key={item.id}>
                <div className="split-row">
                  <span
                    className={`table-tag table-tag--${
                      item.priority.includes('높') ? 'danger' : 'warning'
                    }`}
                  >
                    {item.priority}
                  </span>
                  <span className="list-meta">{item.status}</span>
                </div>
                <h4 className="list-title">{item.title}</h4>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="section-head">
            <div>
              <span className="section-eyebrow">시스템 상태</span>
              <h3 className="section-title">시스템 상태</h3>
              <p className="section-description">
                MQTT bridge와 센서 상태를 운영자에게 짧은 막대 그래프로 보여줍니다.
              </p>
            </div>
          </div>

          <div className="stacked-list">
            {page.healthBars.map((bar) => (
              <article className="health-row" key={bar.label}>
                <AppIcon
                  className={`health-row-icon health-row-icon--${bar.tone}`}
                  name={bar.icon}
                />
                <div className="health-track">
                  <span
                    className={`health-fill health-fill--${bar.tone}`}
                    style={{ width: `${bar.value}%` }}
                  />
                </div>
                <strong>{bar.value}%</strong>
              </article>
            ))}
          </div>

          <div className="panel-divider" />

          <div className="section-head">
            <div>
              <span className="section-eyebrow">제어 이력</span>
              <h3 className="section-title">최근 실행 기록</h3>
              <p className="section-description">
                `actuations/history` 기준으로 어떤 장치에 어떤 명령이 갔는지 빠르게 확인합니다.
              </p>
            </div>
          </div>

          <div className="history-list">
            {page.history.map((item) => (
              <article className={`history-item history-item--${item.tone}`} key={item.id}>
                <div className="split-row">
                  <div>
                    <h4 className="list-title">{item.device}</h4>
                    <p className="list-meta">{item.time}</p>
                  </div>
                  <span
                    className={`table-tag table-tag--${
                      item.tone === 'critical' ? 'danger' : item.tone
                    }`}
                  >
                    {item.result}
                  </span>
                </div>
                <p>{item.action}</p>
              </article>
            ))}
          </div>
        </article>
      </section>
    </div>
  )
}
