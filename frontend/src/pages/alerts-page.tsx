import { SectionCard } from '@/components/section-card'

const alerts = [
  {
    tone: 'danger',
    title: 'A-03 구역 병해 의심 알림',
    detail: '잎 가장자리 갈변과 흰가루 패턴이 동시에 검출되었습니다.',
    meta: '2분 전 · camera/front-left',
  },
  {
    tone: 'warning',
    title: '환경 센서 패킷 유실',
    detail: 'B Zone 조도 센서가 3회 연속 업데이트를 놓쳤습니다.',
    meta: '14분 전 · sensor/light-b',
  },
  {
    tone: 'accent',
    title: '급수 실행 완료',
    detail: 'A Zone 급수 시퀀스가 권장량 기준으로 정상 종료되었습니다.',
    meta: '26분 전 · actuator/water-a',
  },
  {
    tone: 'warning',
    title: '도징펌프 점검 필요',
    detail: '실행 전류 피크가 직전 평균보다 18% 높게 측정되었습니다.',
    meta: '41분 전 · actuator/nutrient-1',
  },
] as const

export function AlertsPage() {
  return (
    <div className="page-grid">
      <SectionCard
        description="알림 심각도, 발생 시각, 장치 출처를 기준으로 정렬한 기본 타임라인입니다."
        eyebrow="Timeline"
        title="알림 센터"
      >
        <div className="timeline">
          {alerts.map((alert) => (
            <article className="timeline-item" key={alert.title}>
              <div className="split-row">
                <span className={`badge badge--${alert.tone}`}>{alert.meta}</span>
                <span className="muted">읽음 처리 전</span>
              </div>
              <h4 className="timeline-title">{alert.title}</h4>
              <p className="timeline-copy">{alert.detail}</p>
            </article>
          ))}
        </div>
      </SectionCard>
    </div>
  )
}
