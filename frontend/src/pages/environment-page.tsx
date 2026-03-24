import { MetricCard } from '@/components/metric-card'
import { SectionCard } from '@/components/section-card'

const environmentCards = [
  { label: '온실 평균 온도', value: '24.6°C', meta: '목표 범위 안쪽', tone: 'accent' },
  { label: '평균 습도', value: '67%', meta: '오전 대비 4% 상승', tone: 'warning' },
  { label: '토양 수분', value: '41%', meta: 'C Zone은 추가 급수 권장', tone: 'accent' },
  { label: '광량', value: '38 klux', meta: 'B Zone 보정 필요', tone: 'warning' },
] as const

const sensors = [
  {
    label: '온도',
    value: '24.6°C',
    detail: '세트포인트 24°C',
    fill: 72,
    tone: 'accent',
  },
  {
    label: '습도',
    value: '67%',
    detail: '환기량 소폭 증가 권장',
    fill: 61,
    tone: 'warning',
  },
  {
    label: '토양수분',
    value: '41%',
    detail: 'C-04와 C-05가 하한선 근접',
    fill: 43,
    tone: 'warning',
  },
  {
    label: 'CO2',
    value: '542 ppm',
    detail: '양호한 범위 유지',
    fill: 58,
    tone: 'accent',
  },
] as const

const recommendations = [
  '환기팬 2번을 15분간 20% 상향',
  'C Zone 점적 관수 6분 실행',
  'B Zone 차광막 10% 닫힘 권장',
] as const

export function EnvironmentPage() {
  return (
    <div className="page-grid">
      <section className="metrics-grid">
        {environmentCards.map((metric) => (
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
          description="실시간 센서 값과 목표 범위를 나란히 놓을 수 있도록 카드 구조를 준비했습니다."
          eyebrow="Sensors"
          title="환경 상태"
        >
          <div className="sensor-list">
            {sensors.map((sensor) => (
              <article className="sensor-card" key={sensor.label}>
                <div className="split-row">
                  <strong>{sensor.label}</strong>
                  <span className="numeric-emphasis">{sensor.value}</span>
                </div>
                <p className="muted">{sensor.detail}</p>
                <div className="progress-track">
                  <span
                    className={`progress-fill${sensor.tone === 'warning' ? ' progress-fill--warning' : ''}`}
                    style={{ width: `${sensor.fill}%` }}
                  />
                </div>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          description="추천 로직을 backend에서 계산하더라도 이 영역에 그대로 연결할 수 있습니다."
          eyebrow="Automation"
          title="자동 제어 추천"
        >
          <div className="schedule-list">
            {recommendations.map((item) => (
              <article className="schedule-item" key={item}>
                <span className="badge badge--accent">recommendation</span>
                <p className="schedule-copy">{item}</p>
              </article>
            ))}
          </div>
        </SectionCard>
      </section>
    </div>
  )
}
