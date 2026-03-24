import { useQuery } from '@tanstack/react-query'
import { DevSurface } from '@/components/dev-surface'
import { MetricCard } from '@/components/metric-card'
import { MockupImage } from '@/components/mockup-image'
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
        <DevSurface
          as="article"
          className="hero-panel hero-panel--warning"
          detail="수확 배치, 적재율, 품질 지표는 실제 harvest runtime 대신 발표용 운영 시나리오에 맞춘 샘플 데이터입니다."
          status="sample"
          title="수확 운영 요약"
        >
          <div className="hero-topline">
            <span className="panel-kicker">수확 운영</span>
            <span className="live-pill live-pill--soft">
              {page.source === 'live' ? '실시간 수확 통계' : '발표용 수확 통계'}
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
          <div style={{ marginTop: '16px' }}>
            <MockupImage
              alt="수확 대상 토마토 시뮬레이션"
              className="hero-photo"
              height={156}
              objectPosition="center 58%"
              src="/mock-images/harvest-closeup.png"
            />
          </div>
        </DevSurface>
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
        <DevSurface
          as="article"
          className="panel"
          detail="수확 배치 큐는 harvest 미션 서버가 아직 완전 연결되지 않아 발표용 루트 시퀀스로 재현합니다."
          status="sample"
          title="수확 일정 큐"
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">배치 큐</span>
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
        </DevSurface>

        <DevSurface
          as="article"
          className="panel"
          detail="품질 지표는 실제 출하/검수 DB가 아니라 발표용 KPI 조합으로, 메인 대시보드 재사용을 염두에 두고 구성했습니다."
          status="sample"
          title="수확 품질 지표"
        >
          <div className="section-head">
            <div>
              <span className="section-eyebrow">품질 KPI</span>
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
        </DevSurface>
      </section>
    </div>
  )
}
