/*
 * 이 컴포넌트는 관제 대시보드의 환경 제어 페이지를 구성한다.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createGetSignal, createPostAction } from '@/app/dev-inspector'
import { AppIcon } from '@/components/app-icon'
import { DevSurface } from '@/components/dev-surface'
import {
  approveWateringRecommendation,
  environmentFallback,
  getEnvironmentPageData,
  triggerNutrientInjection,
} from '@/lib/api/agribot'

function recommendationTagTone(priority: string) {
  if (priority.includes('높') || priority.includes('심각')) {
    return 'danger'
  }

  if (priority.includes('보통') || priority.includes('주의')) {
    return 'warning'
  }

  return 'healthy'
}

function historyToneToTag(tone: 'healthy' | 'warning' | 'critical') {
  if (tone === 'critical') {
    return 'danger'
  }

  return tone
}

/**
 * 환경 페이지 화면 조각을 렌더링하는 컴포넌트다.
 */
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
  const querySource = (path: string) => page.debug.querySources[path] ?? 'fallback'
  const feedbackMessage = approveMutation.isSuccess
    ? approveMutation.data
    : nutrientMutation.isSuccess
      ? nutrientMutation.data
      : approveMutation.isError
        ? approveMutation.error.message
        : nutrientMutation.isError
          ? nutrientMutation.error.message
          : null
  const todayNotes = page.recommendations.slice(0, 3)
  const recentHistory = page.history.slice(0, 3)

  return (
    <div className="screen field-screen">
      <section className="hero-grid hero-grid--environment field-hero-grid">
        <DevSurface
          as="article"
          className="hero-panel hero-panel--environment field-hero"
          contract={{
            title: '밭 안내소',
            queries: [
              createGetSignal('밭 상태', querySource('/environment/latest'), '/environment/latest'),
              createGetSignal('작업 메모', querySource('/actuations/recommendations'), '/actuations/recommendations'),
            ],
            actions: [
              createPostAction('물 주기 승인', ['/actuations/recommendations/reco-water-001/approve', '/actuations/watering'], 'any'),
            ],
          }}
        >
          <div className="hero-topline">
            <div>
              <span className="panel-kicker">밭 안내소</span>
              <h3 className="hero-title">{page.recommendation}</h3>
            </div>
            <span className="live-pill">
              {page.source === 'live' ? '실시간 밭 메모' : '포근한 샘플 메모'}
            </span>
          </div>
          <p className="hero-copy">
            차광 커튼과 환기 팬은 빼고, 밭에서 실제로 필요한 물주기와 영양 보충만 남겼습니다.
          </p>

          <div className="field-mini-card-grid">
            {page.metrics.map((card) => (
              <article className={`field-mini-card field-mini-card--${card.tone}`} key={card.label}>
                <span className="metric-label">{card.label}</span>
                <strong className="field-mini-card-value">{card.value}</strong>
                <p className="field-mini-card-meta">{card.meta}</p>
              </article>
            ))}
          </div>

          <div className="recommendation-strip field-recommendation-strip">
            <div className="recommendation-icon">
              <AppIcon filled name="water_drop" />
            </div>
            <div className="recommendation-copy">
              <span className="section-eyebrow">지금 먼저 할 일</span>
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
                {approveMutation.isPending ? '물 주는 중...' : '물 주기 승인'}
              </button>
            </div>
          </div>
        </DevSurface>

        <DevSurface
          as="aside"
          className="panel field-daybook"
          contract={{
            title: '오늘의 밭 메모',
            queries: [
              createGetSignal('작업 메모', querySource('/actuations/recommendations'), '/actuations/recommendations'),
            ],
          }}
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">오늘의 메모</span>
              <h3 className="section-title">차분한 밭 루틴</h3>
              <p className="section-description">
                지금 바로 확인할 일만 안내소 메모처럼 짧게 적어 두었습니다.
              </p>
            </div>
          </div>

          <div className="field-diary-list">
            {todayNotes.map((item) => (
              <article className={`field-diary-item field-diary-item--${recommendationTagTone(item.priority)}`} key={item.id}>
                <div className="split-row">
                  <span className={`table-tag table-tag--${recommendationTagTone(item.priority)}`}>
                    {item.priority}
                  </span>
                  <span className="list-meta">{item.status}</span>
                </div>
                <h4 className="list-title">{item.title}</h4>
                <p>{item.detail}</p>
              </article>
            ))}
          </div>
        </DevSurface>
      </section>

      <section className="content-grid content-grid--environment field-board-grid">
        <DevSurface
          as="article"
          className="panel field-tools"
          contract={{
            title: '작은 도구함',
            queries: [
              createGetSignal('장치 목록', querySource('/iot/devices'), '/iot/devices'),
            ],
            actions: [
              createPostAction('물 주기 승인', ['/actuations/recommendations/reco-water-001/approve', '/actuations/watering'], 'any'),
              createPostAction('영양 보충', ['/actuations/nutrients']),
            ],
          }}
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">작은 도구함</span>
              <h3 className="section-title">두 가지만 챙기기</h3>
              <p className="section-description">
                밭에서는 물주기와 영양 보충만 바로 누를 수 있게 남겼습니다.
              </p>
            </div>
          </div>

          <div className="field-tool-grid">
            {page.devices.map((device) => {
              const isWatering = device.action === 'toggle'
              const pending = isWatering ? approveMutation.isPending : nutrientMutation.isPending

              return (
                <article className={`field-tool-card field-tool-card--${device.accent}`} key={device.id}>
                  <div className="field-tool-top">
                    <div className={`device-icon device-icon--${device.accent}`}>
                      <AppIcon name={device.icon} />
                    </div>
                    <span className={`table-tag table-tag--${isWatering ? 'healthy' : 'warning'}`}>
                      {isWatering ? '자동 대기' : '수동 실행'}
                    </span>
                  </div>
                  <div className="field-tool-copy">
                    <h4 className="list-title">{device.name}</h4>
                    <p>{device.detail}</p>
                  </div>
                  <button
                    className={`action-button${isWatering ? '' : ' action-button--warning'} field-tool-action`}
                    disabled={pending}
                    onClick={() => {
                      if (isWatering) {
                        approveMutation.mutate()
                        return
                      }

                      nutrientMutation.mutate()
                    }}
                    type="button"
                  >
                    {isWatering
                      ? pending
                        ? '물 주는 중...'
                        : '물 주기 승인'
                      : pending
                        ? '보충 중...'
                        : '영양 보충 실행'}
                  </button>
                </article>
              )
            })}
          </div>
          {feedbackMessage ? <p className="muted">{feedbackMessage}</p> : null}
        </DevSurface>

        <DevSurface
          as="article"
          className="panel field-journal"
          contract={{
            title: '산책 기록',
            queries: [
              createGetSignal('실행 이력', querySource('/actuations/history'), '/actuations/history'),
            ],
          }}
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">산책 기록</span>
              <h3 className="section-title">최근 손보기 메모</h3>
              <p className="section-description">
                방금 한 일만 짧게 남겨 두고, 복잡한 시스템 상태 표는 걷어냈습니다.
              </p>
            </div>
          </div>

          <div className="field-journal-list">
            {recentHistory.map((item) => (
              <article className={`field-journal-item field-journal-item--${item.tone}`} key={item.id}>
                <div className="split-row">
                  <div>
                    <h4 className="list-title">{item.device}</h4>
                    <p className="list-meta">{item.time}</p>
                  </div>
                  <span className={`table-tag table-tag--${historyToneToTag(item.tone)}`}>
                    {item.result}
                  </span>
                </div>
                <p>{item.action}</p>
              </article>
            ))}
          </div>
        </DevSurface>
      </section>
    </div>
  )
}
