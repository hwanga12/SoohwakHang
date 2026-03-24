import { useQuery } from '@tanstack/react-query'
import { AppIcon } from '@/components/app-icon'
import {
  getPlantsPageData,
  plantsFallback,
} from '@/lib/api/agribot'

export function PlantsPage() {
  const plantsQuery = useQuery({
    queryKey: ['page', 'plants'],
    queryFn: getPlantsPageData,
    initialData: plantsFallback,
    refetchInterval: 20_000,
  })
  const page = plantsQuery.data

  return (
    <div className="screen">
      <section className="hero-grid hero-grid--plants">
        <article className="hero-panel hero-panel--accent">
          <div className="hero-topline">
            <span className="panel-kicker">Plant Intelligence</span>
            <span className="live-pill live-pill--soft">
              {page.source === 'live' ? 'AI 비전 + API 연결' : '시안 fallback 데이터'}
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
        </article>

        <article className="hero-panel hero-panel--danger hero-panel--compact">
          <div className="alert-count-icon">
            <AppIcon className="alert-count-symbol" filled name="warning" />
          </div>
          <span className="panel-kicker">Critical Cases</span>
          <strong className="feature-number">{page.criticalCount}</strong>
          <p className="feature-copy">즉시 판독 또는 처치가 필요한 개체 수</p>
          <button className="action-button action-button--danger" type="button">
            치료 요청
          </button>
        </article>
      </section>

      <section className="panel">
        <div className="section-head">
          <div>
            <span className="section-eyebrow">Alert Rail</span>
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
      </section>

      <section className="panel">
        <div className="section-head">
          <div>
            <span className="section-eyebrow">Crop Ledger</span>
            <h3 className="section-title">작물 현황</h3>
            <p className="section-description">
              필터 칩, 건강도, 상태 태그만으로 현장 검수 우선순위를 빠르게 고를 수 있게
              구성했습니다.
            </p>
          </div>
          <div className="chip-row">
            <span className="chip chip--active">전체</span>
            <span className="chip">수확 가능</span>
            <span className="chip">질병 의심</span>
          </div>
        </div>

        <div className="table-card">
          <div className="table-head">
            <span>작물 종류</span>
            <span>건강도</span>
            <span>상태</span>
          </div>
          {page.plants.map((plant) => (
            <article className="table-row" key={plant.id}>
              <div className="table-row-main">
                <AppIcon
                  className={`plant-row-icon plant-row-icon--${plant.tone}`}
                  name="potted_plant"
                />
                <div>
                  <h4>{plant.name}</h4>
                  <p>{plant.id}</p>
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
                <span className={`table-tag table-tag--${plant.tone}`}>
                  {plant.status}
                </span>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
