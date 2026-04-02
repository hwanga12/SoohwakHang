/*
 * 이 컴포넌트는 관제 대시보드의 수확 현황 페이지를 구성한다.
 */
import { useQuery } from '@tanstack/react-query'
import { createGetSignal } from '@/app/dev-inspector'
import { DevSurface } from '@/components/dev-surface'
import { MetricCard } from '@/components/metric-card'
import {
  getHarvestPageData,
  harvestFallback,
  type HarvestBatch,
  type HarvestPageData,
} from '@/lib/api/agribot'

function normalizeHarvestPhase(phase: string) {
  return phase.trim().toUpperCase()
}

function formatHarvestPhase(phase: string) {
  switch (normalizeHarvestPhase(phase)) {
    case 'APPROACHING':
      return '접근'
    case 'ALIGNING':
      return '자세 보정'
    case 'PICKING':
      return '집기'
    case 'STOWING':
      return '등 바구니 적재'
    case 'RETURN_HOME':
      return '복귀'
    case 'RESUME':
      return '다음 작업 복귀'
    default:
      return phase.trim() || '대기'
  }
}

function getBatchTone(batch: HarvestBatch) {
  if (batch.success === true || batch.state.includes('완료')) {
    return 'healthy'
  }

  if (batch.state.includes('진행') || normalizeHarvestPhase(batch.currentPhase)) {
    return 'warning'
  }

  if (batch.success === false || batch.state.includes('실패')) {
    return 'danger'
  }

  return 'warning'
}

function buildHarvestHeroTitle(page: HarvestPageData) {
  if (page.missionStatus === 'running') {
    return `${formatHarvestPhase(page.currentPhase)} 단계와 바구니 적재 현황을 실제 상태 기준으로 보여줍니다.`
  }

  if (page.lastHarvestedFruitId) {
    return '가장 최근에 딴 토마토와 현재 바구니 적재량을 같은 흐름으로 확인할 수 있습니다.'
  }

  return '수확 미션, 적재, 검수 큐를 운영자가 같은 흐름으로 보도록 정리했습니다.'
}

function buildHarvestHeroCopy(page: HarvestPageData) {
  if (page.missionStatus === 'running' || page.missionStatus === 'pending') {
    return page.detailMessage || '`harvests`, `missions/harvest`, `harvest action server` 상태를 묶어 현재 수확 단계를 보여줍니다.'
  }

  if (page.lastHarvestedFruitId) {
    return `${page.lastHarvestedFruitId} 수확 결과와 바구니 적재량을 실제 이벤트 기준으로 정리했습니다.`
  }

  return '`harvests`, `missions/harvest`, `harvest action server` 방향을 기준으로 배치와 바구니 운영 화면을 구성했습니다.'
}

function buildHarvestSequence(page: HarvestPageData) {
  const steps = [
    { key: 'APPROACHING', label: '접근', detail: '수확 대상 식물 앞으로 이동합니다.' },
    { key: 'ALIGNING', label: '자세 보정', detail: '로봇팔이 집기 자세를 맞춥니다.' },
    { key: 'PICKING', label: '집기', detail: '줄기에서 토마토를 분리합니다.' },
    { key: 'STOWING', label: '적재', detail: '수확물을 등 바구니에 옮겨 담습니다.' },
  ] as const

  const currentPhase = normalizeHarvestPhase(page.currentPhase)
  const currentIndex = steps.findIndex((step) => step.key === currentPhase)
  const missionFinished =
    page.missionStatus === 'succeeded'
    || (
      page.missionStatus !== 'running'
      && page.missionStatus !== 'pending'
      && page.lastHarvestedFruitId !== ''
    )

  return steps.map((step, index) => {
    const isCurrent = currentIndex === index && page.missionStatus === 'running'
    const isDone = missionFinished ? true : currentIndex > index

    return {
      ...step,
      stateLabel: isCurrent ? '진행 중' : isDone ? '완료' : '대기',
      tone: isCurrent ? 'warning' : isDone ? 'healthy' : 'warning',
    }
  })
}

/**
 * 수확 페이지 화면 조각을 렌더링하는 컴포넌트다.
 */
export function HarvestPage() {
  const harvestQuery = useQuery({
    queryKey: ['page', 'harvest'],
    queryFn: getHarvestPageData,
    initialData: harvestFallback,
    refetchInterval: 20_000,
  })
  const page = harvestQuery.data
  const querySource = (path: string) => page.debug.querySources[path] ?? 'fallback'

  return (
    <div className="screen">
      <section className="hero-grid hero-grid--harvest">
        <DevSurface
          as="article"
          className="hero-panel hero-panel--warning"
          contract={{
            title: '수확 운영 요약',
            queries: [
              createGetSignal('수확 통계', querySource('/harvests/stats'), '/harvests/stats'),
              createGetSignal('수확 배치', querySource('/harvests'), '/harvests'),
            ],
          }}
        >
          <div className="hero-topline">
            <span className="panel-kicker">수확 운영</span>
            <span className="live-pill live-pill--soft">
              {page.source === 'live' ? '실시간 수확 통계' : '발표용 수확 통계'}
            </span>
          </div>
          <h3 className="hero-title">{buildHarvestHeroTitle(page)}</h3>
          <p className="hero-copy">
            {buildHarvestHeroCopy(page)}
          </p>
          <div className="hero-stat-row">
            <div className="hero-stat">
              <span className="hero-stat-label">현재 단계</span>
              <strong>{formatHarvestPhase(page.currentPhase)}</strong>
            </div>
            <div className="hero-stat">
              <span className="hero-stat-label">현재 바구니</span>
              <strong>{page.basketState}</strong>
            </div>
            <div className="hero-stat">
              <span className="hero-stat-label">마지막 수확</span>
              <strong>{page.lastHarvestedFruitId || '아직 없음'}</strong>
            </div>
          </div>
          <div className="chip-row" style={{ marginTop: '16px' }}>
            <span className="chip">적재 {page.basketCount}개</span>
            <span className="chip">대기 수확 {page.remainingReadyCount}개</span>
            <span className="chip">{page.nextSwap}</span>
            {page.activeMissionId ? <span className="chip">{page.activeMissionId}</span> : null}
          </div>
          <div className="stacked-list" style={{ marginTop: '16px' }}>
            {buildHarvestSequence(page).map((step) => (
              <article className="queue-card" key={step.key}>
                <div className="split-row">
                  <h4 className="list-title">{step.label}</h4>
                  <span className={`table-tag table-tag--${step.tone}`}>{step.stateLabel}</span>
                </div>
                <p>{step.detail}</p>
              </article>
            ))}
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
          contract={{
            title: '수확 일정 큐',
            queries: [
              createGetSignal('수확 배치', querySource('/harvests'), '/harvests'),
            ],
          }}
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
                  <span className={`table-tag table-tag--${getBatchTone(batch)}`}>
                    {batch.state}
                  </span>
                </div>
                <p>{batch.summary}</p>
                <div className="chip-row">
                  {batch.currentPhase ? <span className="chip">{formatHarvestPhase(batch.currentPhase)}</span> : null}
                  {batch.fruitId ? <span className="chip">{batch.fruitId}</span> : null}
                  {batch.basketCount !== null ? <span className="chip">적재 {batch.basketCount}개</span> : null}
                  {batch.updatedAt ? <span className="chip">{batch.updatedAt}</span> : null}
                </div>
              </article>
            ))}
          </div>
        </DevSurface>

        <DevSurface
          as="article"
          className="panel"
          contract={{
            title: '수확 품질 지표',
            queries: [
              createGetSignal('수확 통계', querySource('/harvests/stats'), '/harvests/stats'),
            ],
          }}
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
