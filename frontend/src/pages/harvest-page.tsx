import { MetricCard } from '@/components/metric-card'
import { SectionCard } from '@/components/section-card'

const harvestMetrics = [
  { label: '오늘 수확', value: '142 kg', meta: '전일 대비 18% 증가', tone: 'accent' },
  { label: '바구니 적재율', value: '68%', meta: '다음 교체 예상 35분 후', tone: 'warning' },
  { label: '성공률', value: '94.8%', meta: '접근 재시도 포함', tone: 'accent' },
  { label: '실패 건수', value: '7건', meta: '미성숙 개체 접근 4건', tone: 'danger' },
] as const

const schedules = [
  {
    title: '오전 수확 배치',
    detail: 'C Zone 성숙 과실 우선 수확, 바구니 2개 사용',
    status: '진행 중',
  },
  {
    title: '오후 품질 검수',
    detail: 'A Zone 의심 병해 개체 제외 후 재집계',
    status: '예정',
  },
  {
    title: '적재 라벨 정리',
    detail: '출하 대기 바구니 QR 라벨 일괄 갱신',
    status: '대기',
  },
] as const

const stats = [
  { label: '완숙 비율', value: '81%' },
  { label: '평균 수확 시간', value: '42초/개' },
  { label: '적재 중량 오차', value: '1.8%' },
] as const

export function HarvestPage() {
  return (
    <div className="page-grid">
      <section className="metrics-grid">
        {harvestMetrics.map((metric) => (
          <MetricCard
            key={metric.label}
            label={metric.label}
            meta={metric.meta}
            tone={metric.tone}
            value={metric.value}
          />
        ))}
      </section>

      <section className="layout-two-col">
        <SectionCard
          description="수확 이력, 진행 중 배치, 작업 예정 목록을 분리해서 확장하기 쉬운 형태입니다."
          eyebrow="Plan"
          title="수확 일정"
        >
          <div className="schedule-list">
            {schedules.map((schedule) => (
              <article className="schedule-item" key={schedule.title}>
                <div className="split-row">
                  <h4 className="schedule-title">{schedule.title}</h4>
                  <span className="badge badge--accent">{schedule.status}</span>
                </div>
                <p className="schedule-copy">{schedule.detail}</p>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          description="핵심 KPI를 작은 카드로 분리해 메인 대시보드에도 재사용하기 쉽게 구성했습니다."
          eyebrow="KPI"
          title="수확 품질 지표"
        >
          <div className="helper-grid">
            {stats.map((stat) => (
              <article className="sensor-card" key={stat.label}>
                <span className="metric-label">{stat.label}</span>
                <strong className="numeric-emphasis">{stat.value}</strong>
              </article>
            ))}
          </div>
        </SectionCard>
      </section>
    </div>
  )
}
