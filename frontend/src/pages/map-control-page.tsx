import { MetricCard } from '@/components/metric-card'
import { SectionCard } from '@/components/section-card'

const robotMetrics = [
  { label: '현재 모드', value: 'Patrol', meta: 'B 루트 순찰 중', tone: 'accent' },
  { label: '배터리', value: '74%', meta: '충전 없이 2시간 10분 예상', tone: 'warning' },
  { label: '다음 목표', value: 'B-04', meta: '병해 확인 포인트 접근', tone: 'accent' },
] as const

const controlActions = [
  {
    title: '순찰 시작',
    detail: '오늘 배정된 waypoint 세트를 기준으로 주행을 시작합니다.',
  },
  {
    title: '순찰 중지',
    detail: '현재 구역 작업 완료 후 안전 정지 상태로 전환합니다.',
  },
  {
    title: '홈 복귀',
    detail: '충전 스테이션으로 복귀 명령을 전송합니다.',
  },
  {
    title: '긴급 정지',
    detail: '즉시 모터를 정지하고 운영자 확인을 기다립니다.',
  },
] as const

const zones = [
  { name: 'A Zone', copy: '병해 감시 우선 구역', state: '주의' },
  { name: 'B Zone', copy: '현재 순찰 동선 진행 중', state: '진행 중' },
  { name: 'C Zone', copy: '수확 예정 개체 밀집', state: '대기' },
  { name: 'Dock', copy: '충전 및 바구니 적재 지점', state: '정상' },
] as const

export function MapControlPage() {
  return (
    <div className="page-grid">
      <section className="metrics-grid">
        {robotMetrics.map((metric) => (
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
          description="실제 지도 이미지 또는 SVG overlay를 붙일 자리를 미리 잡아둔 상태입니다."
          eyebrow="Map"
          title="비닐하우스 맵"
        >
          <div className="map-stage">
            <div className="map-grid">
              {zones.map((zone) => (
                <article className="map-zone" key={zone.name}>
                  <strong>{zone.name}</strong>
                  <span className="muted">{zone.copy}</span>
                  <span className="badge badge--accent">{zone.state}</span>
                </article>
              ))}
            </div>
            <div className="robot-marker">AGR-02</div>
          </div>
        </SectionCard>

        <SectionCard
          description="버튼 이벤트에 backend 명령 호출만 연결하면 제어 화면으로 바로 확장할 수 있습니다."
          eyebrow="Commands"
          title="로봇 제어"
        >
          <div className="control-grid">
            {controlActions.map((action) => (
              <button className="control-button" key={action.title} type="button">
                <strong>{action.title}</strong>
                <span className="muted">{action.detail}</span>
              </button>
            ))}
          </div>
        </SectionCard>
      </section>
    </div>
  )
}
