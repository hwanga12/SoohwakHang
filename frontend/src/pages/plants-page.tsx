import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { createGetSignal, createPostAction } from '@/app/dev-inspector'
import { AppIcon } from '@/components/app-icon'
import { DevSurface } from '@/components/dev-surface'
import { MockupImage } from '@/components/mockup-image'
import {
  getPlantsPageData,
  plantsFallback,
  requestHarvestMission,
} from '@/lib/api/agribot'

function getAlertPreview(alertId: string) {
  if (alertId.includes('disease')) {
    return '/mock-images/disease-closeup.png'
  }

  return '/mock-images/harvest-closeup.png'
}

export function PlantsPage() {
  const queryClient = useQueryClient()
  const plantsQuery = useQuery({
    queryKey: ['page', 'plants'],
    queryFn: getPlantsPageData,
    initialData: plantsFallback,
    refetchInterval: 20_000,
  })
  const [selectedPlantId, setSelectedPlantId] = useState<string | null>(null)
  const harvestMutation = useMutation({
    mutationFn: requestHarvestMission,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'plants'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'harvest'] })
    },
  })
  const page = plantsQuery.data
  const querySource = (path: string) => page.debug.querySources[path] ?? 'fallback'
  const selectedPlant =
    page.plants.find((plant) => plant.id === selectedPlantId) ?? page.plants[0]
  const feedbackMessage = harvestMutation.isSuccess
    ? harvestMutation.data.message
    : harvestMutation.isError
      ? harvestMutation.error.message
      : null

  useEffect(() => {
    if (!selectedPlantId && page.plants[0]) {
      setSelectedPlantId(page.plants[0].id)
      return
    }

    if (selectedPlantId && !page.plants.some((plant) => plant.id === selectedPlantId)) {
      setSelectedPlantId(page.plants[0]?.id ?? null)
    }
  }, [page.plants, selectedPlantId])

  return (
    <div className="screen">
      <section className="hero-grid hero-grid--plants">
        <DevSurface
          as="article"
          className="hero-panel hero-panel--accent"
          contract={{
            title: '작물 진단 요약',
            queries: [
              createGetSignal('작물 목록', querySource('/plants'), '/plants'),
              createGetSignal('알림 목록', querySource('/alerts'), '/alerts'),
            ],
          }}
        >
          <div className="hero-topline">
            <span className="panel-kicker">작물 인텔리전스</span>
            <span className="live-pill live-pill--soft">
              {page.source === 'live' ? 'AI 비전 + API 연결' : '발표용 샘플 데이터'}
            </span>
          </div>
          <h3 className="hero-title">
            식물 건강도 {page.healthSummary}, 질병 의심 개체 {page.criticalCount}주가 추적 중입니다.
          </h3>
          <p className="hero-copy">
            `plants`, `plants/{'{plant_id}'}/observations`, `alerts` 라우터를 한 화면에서
            다룬다는 전제로 작물 진단과 병해 알림을 묶었습니다.
          </p>
          <div className="hero-stat-row">
            <div className="hero-stat">
              <span className="hero-stat-label">활성 스캔</span>
              <strong>{page.activeScans}</strong>
            </div>
            <div className="hero-stat">
              <span className="hero-stat-label">성장 지수</span>
              <strong>{page.growthIndex}</strong>
            </div>
          </div>
        </DevSurface>

        <DevSurface
          as="article"
          className="hero-panel hero-panel--danger hero-panel--compact"
          contract={{
            title: '우선 검수 카드',
            queries: [
              createGetSignal('알림 목록', querySource('/alerts'), '/alerts'),
            ],
          }}
        >
          <div className="alert-count-icon">
            <AppIcon className="alert-count-symbol" filled name="warning" />
          </div>
          <span className="panel-kicker">중점 검수</span>
          <strong className="feature-number">{page.criticalCount}</strong>
          <p className="feature-copy">즉시 판독 또는 처치가 필요한 개체 수</p>
          <Link className="action-button action-button--danger" to="/alerts">
            알림 센터 열기
          </Link>
        </DevSurface>
      </section>

      <DevSurface
        as="section"
        className="panel"
        contract={{
          title: '우선 알림 카드',
          queries: [
            createGetSignal('알림 목록', querySource('/alerts'), '/alerts'),
          ],
        }}
      >
        <div className="section-head">
          <div>
            <span className="section-eyebrow">우선 알림</span>
            <h3 className="section-title">긴급 알림</h3>
            <p className="section-description">
              병해 분류 모델이 높은 신뢰도로 잡아낸 개체를 우선 카드로 띄웁니다.
            </p>
          </div>
          <button className="ghost-chip" type="button">
            지도 보기
          </button>
        </div>

        <div className="alert-rail">
          {page.alerts.map((alert) => (
            <article className="alert-card" key={alert.title}>
              <div className="alert-card-visual">
                <MockupImage
                  alt={`${alert.title} 시뮬레이션 이미지`}
                  className="alert-card-photo"
                  height="100%"
                  src={getAlertPreview(alert.id)}
                />
                <div
                  className={`severity-pill severity-pill--${
                    alert.severity === '심각' ? 'danger' : 'warning'
                  }`}
                >
                  {alert.severity}
                </div>
              </div>
              <div className="alert-card-body">
                <div>
                  <h4 className="list-title">{alert.title}</h4>
                  <p className="list-meta">{alert.location}</p>
                </div>
                <div className="alert-card-footer">
                  <span className="muted">{alert.action}</span>
                  <button className="icon-button icon-button--soft" type="button">
                    <AppIcon filled name="rocket_launch" />
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      </DevSurface>

      <section className="content-grid content-grid--plants">
        <DevSurface
          as="article"
          className="panel"
          contract={{
            title: '작물 원장',
            queries: [
              createGetSignal('작물 목록', querySource('/plants'), '/plants'),
            ],
          }}
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">작물 원장</span>
              <h3 className="section-title">작물 현황</h3>
              <p className="section-description">
                식물 ID와 토마토 대상 ID를 함께 보면서 수확 후보와 검수 대상을 고릅니다.
              </p>
            </div>
            <div className="chip-row">
              <span className="chip chip--active">전체</span>
              <span className="chip">수확 후보</span>
              <span className="chip">병해 점검</span>
            </div>
          </div>

          <div className="table-card">
            <div className="table-head">
              <span>작물</span>
              <span>건강도</span>
              <span>상태</span>
            </div>
            {page.plants.map((plant) => (
              <button
                className={`table-row is-selectable${selectedPlant?.id === plant.id ? ' is-selected' : ''}`}
                key={plant.id}
                onClick={() => {
                  setSelectedPlantId(plant.id)
                }}
                type="button"
              >
                <div className="table-row-main">
                  <AppIcon
                    className={`plant-row-icon plant-row-icon--${plant.tone}`}
                    name="potted_plant"
                  />
                  <div className="table-row-copy">
                    <h4>{plant.name}</h4>
                    <p>{plant.id}</p>
                    <span className="table-row-meta">{plant.targetId}</span>
                  </div>
                </div>
                <div className="health-cell">
                  <div className="health-track">
                    <span
                      className={`health-fill health-fill--${plant.tone}`}
                      style={{ width: `${plant.health}%` }}
                    />
                  </div>
                  <strong>{plant.health}</strong>
                </div>
                <div className="table-tag-wrap">
                  <span className={`table-tag table-tag--${plant.tone === 'critical' ? 'danger' : plant.tone}`}>
                    {plant.status}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </DevSurface>

        <DevSurface
          as="article"
          className="panel"
          contract={{
            title: '선택 대상 상세와 수확 요청',
            queries: [
              createGetSignal('작물 목록', querySource('/plants'), '/plants'),
            ],
            actions: [
              createPostAction('수확 요청', ['/missions/harvest']),
            ],
          }}
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">선택 상세</span>
              <h3 className="section-title">
                {selectedPlant ? `${selectedPlant.name} 상세` : '작물 상세'}
              </h3>
              <p className="section-description">
                현재 선택한 작물의 대상 ID와 위치를 보고 바로 수확 요청으로 넘길 수 있습니다.
              </p>
            </div>
            {selectedPlant ? (
              <span className={`table-tag table-tag--${selectedPlant.tone === 'critical' ? 'danger' : selectedPlant.tone}`}>
                {selectedPlant.status}
              </span>
            ) : null}
          </div>

          {selectedPlant ? (
            <>
              <div className="detail-grid">
                <article className="detail-card">
                  <span className="detail-label">작물 ID</span>
                  <strong className="detail-value">{selectedPlant.id}</strong>
                </article>
                <article className="detail-card">
                  <span className="detail-label">대상 토마토 ID</span>
                  <strong className="detail-value">{selectedPlant.targetId}</strong>
                </article>
                <article className="detail-card">
                  <span className="detail-label">구역</span>
                  <strong className="detail-value">{selectedPlant.zoneLabel}</strong>
                </article>
                <article className="detail-card">
                  <span className="detail-label">위치</span>
                  <strong className="detail-value">{selectedPlant.positionLabel}</strong>
                </article>
              </div>

              <div className="detail-list">
                <article className="detail-line">
                  <span className="detail-label">최근 관측</span>
                  <strong>{selectedPlant.lastObserved}</strong>
                </article>
                <article className="detail-line">
                  <span className="detail-label">권장 작업</span>
                  <strong>{selectedPlant.recommendedAction}</strong>
                </article>
                <article className="detail-line">
                  <span className="detail-label">건강도</span>
                  <strong>{selectedPlant.health}점</strong>
                </article>
              </div>

              <button
                className="action-button"
                disabled={harvestMutation.isPending}
                onClick={() => {
                  harvestMutation.mutate({
                    plantId: selectedPlant.id,
                    fruitId: selectedPlant.targetId,
                  })
                }}
                type="button"
              >
                {harvestMutation.isPending ? '요청 전송 중...' : '선택 대상 수확 요청'}
              </button>
              {feedbackMessage ? <p className="muted">{feedbackMessage}</p> : null}
            </>
          ) : (
            <p className="muted">표에서 작물을 선택하면 상세 정보가 표시됩니다.</p>
          )}
        </DevSurface>
      </section>
    </div>
  )
}
