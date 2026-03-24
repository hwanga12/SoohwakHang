import { useQuery } from '@tanstack/react-query'
import { MetricCard } from '@/components/metric-card'
import {
  getHarvestPageData,
  harvestFallback,
} from '@/lib/api/agribot'

function getBatchTone(state: string) {
  if (state.includes('진행')) {
    return 'healthy'
  }

  if (state.includes('예정')) {
    return 'warning'
  }

  return 'danger'
}

export function HarvestPage() {
  const harvestQuery = useQuery({
    queryKey: ['page', 'harvest'],
    queryFn: getHarvestPageData,
    initialData: harvestFallback,
    refetchInterval: 20_000,
  })
  const page = harvestQuery.data

  return (
    <div className="screen">
      <section className="hero-grid hero-grid--harvest">
        <article className="hero-panel hero-panel--warning">
          <div className="hero-topline">
            <span className="panel-kicker">Harvest Mission</span>
            <span className="live-pill live-pill--soft">
              {page.source === 'live' ? '실시간 수확 통계' : 'fallback 수확 통계'}
            </span>
          </div>
          <h3 className="hero-title">수확 미션, 적재, 검수 큐를 운영자가 같은 흐름으로 보도록 정리했습니다.</h3>
          <p className="hero-copy">
            `harvests`, `missions/harvest`, `harvest action server` 방향을 기준으로
            배치와 바구니 운영 화면을 구성했습니다.
          </p>
          <div className="hero-stat-row">
            <div className="hero-stat">
              <span className="hero-stat-label">현재 바구니</span>
              <strong>{page.basketState}</strong>
            </div>
            <div className="hero-stat">
              <span className="hero-stat-label">다음 교체</span>
              <strong>{page.nextSwap}</strong>
            </div>
          </div>
        </article>
      </section>

      <section className="metric-row">
        {page.metrics.map((metric) => (
          <MetricCard
            key={metric.label}
            label={metric.label}
            meta={metric.meta}
            tone={metric.tone}
            value={metric.value}
          />
        ))}
      </section>

      <section className="content-grid content-grid--harvest">
        <article className="panel">
          <div className="section-head">
            <div>
              <span className="section-eyebrow">Batch Queue</span>
              <h3 className="section-title">수확 일정</h3>
              <p className="section-description">
                lane 단위 수확 루트와 적재 작업을 같은 큐에서 관리하도록 구성했습니다.
              </p>
            </div>
          </div>

          <div className="stacked-list">
            {page.batches.map((batch) => (
              <article className="queue-card" key={batch.route}>
                <div className="split-row">
                  <h4 className="list-title">{batch.route}</h4>
                  <span className={`table-tag table-tag--${getBatchTone(batch.state)}`}>
                    {batch.state}
                  </span>
                </div>
                <p>{batch.summary}</p>
              </article>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="section-head">
            <div>
              <span className="section-eyebrow">Quality KPI</span>
              <h3 className="section-title">수확 품질 지표</h3>
              <p className="section-description">
                메인 대시보드에도 재사용 가능한 작은 KPI 카드들입니다.
              </p>
            </div>
          </div>

          <div className="mini-card-grid">
            {page.qualityStats.map((stat) => (
              <article className="mini-metric-card" key={stat.label}>
                <span className="mini-metric-label">{stat.label}</span>
                <strong className="mini-metric-value">{stat.value}</strong>
              </article>
            ))}
          </div>
        </article>
      </section>
    </div>
  )
}
