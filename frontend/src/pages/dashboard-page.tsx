import { MetricCard } from '@/components/metric-card'
import { SectionCard } from '@/components/section-card'
import { env } from '@/config/env'
import { apiClient } from '@/lib/api/client'

const summaryCards = [
  { label: '로봇 가동률', value: '98.2%', meta: '순찰 모드 안정적 유지', tone: 'accent' },
  { label: '오늘 수확량', value: '142 kg', meta: '목표 대비 12% 초과', tone: 'accent' },
  { label: '주의 알림', value: '3건', meta: '1건은 즉시 확인 필요', tone: 'warning' },
  { label: '점검 장치', value: '2대', meta: '환기팬과 도징펌프 확인', tone: 'danger' },
] as const

const recentAlerts = [
  {
    level: 'critical',
    title: 'A-03 구역 잎마름 의심 감지',
    detail: '최근 10분 내 이미지 4건에서 동일 패턴이 반복 감지되었습니다.',
    time: '09:18',
    tone: 'danger',
  },
  {
    level: 'warning',
    title: '환기팬 2번 응답 지연',
    detail: '상태 업데이트 지연이 8초 이상 발생했습니다.',
    time: '09:12',
    tone: 'warning',
  },
  {
    level: 'normal',
    title: '순찰 루트 B 완료',
    detail: '현재 로봇은 충전 스테이션으로 복귀 중입니다.',
    time: '09:05',
    tone: 'accent',
  },
] as const

const zones = [
  { name: 'A Zone', summary: '온도 24.3°C · 토양수분 안정', status: '정상' },
  { name: 'B Zone', summary: '광량 보정 필요 · 환기 증가 권장', status: '관찰' },
  { name: 'C Zone', summary: '수확 대기 개체 18주', status: '수확 예정' },
] as const

const tasks = [
  { title: '수확 준비', detail: 'C-02, C-04 구역 적재 바구니 교체', owner: '농장 운영팀' },
  { title: '센서 보정', detail: 'B Zone 조도 센서 drift 점검', owner: 'IoT 담당' },
  { title: '병해 검수', detail: 'A-03 의심 이미지 수동 검토', owner: '작물 분석팀' },
] as const

export function DashboardPage() {
  return (
    <div className="page-grid">
      <section className="metrics-grid">
        {summaryCards.map((card) => (
          <MetricCard
            key={card.label}
            label={card.label}
            meta={card.meta}
            tone={card.tone}
            value={card.value}
          />
        ))}
      </section>

      <section className="layout-two-col">
        <SectionCard
          description="병해, 장애, 순찰 완료 이벤트를 우선순위 순으로 배치할 수 있는 기본 형태입니다."
          eyebrow="Live Feed"
          title="최근 알림"
        >
          <div className="timeline">
            {recentAlerts.map((alert) => (
              <article className="timeline-item" key={alert.title}>
                <div className="split-row">
                  <span className={`badge badge--${alert.tone}`}>
                    {alert.level}
                  </span>
                  <span className="muted">{alert.time}</span>
                </div>
                <h4 className="timeline-title">{alert.title}</h4>
                <p className="timeline-copy">{alert.detail}</p>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          description="`.env.local`만 교체하면 backend와 WebSocket 엔드포인트를 바로 연결할 수 있습니다."
          eyebrow="Connection"
          title="연결 기준값"
        >
          <dl className="connection-list">
            <div>
              <dt>App Name</dt>
              <dd>{env.appName}</dd>
            </div>
            <div>
              <dt>REST API</dt>
              <dd className="code-chip">{apiClient.defaults.baseURL}</dd>
            </div>
            <div>
              <dt>WebSocket</dt>
              <dd className="code-chip">{env.wsUrl}</dd>
            </div>
            <div>
              <dt>Mode</dt>
              <dd>{env.mode}</dd>
            </div>
          </dl>
        </SectionCard>
      </section>

      <section className="layout-two-col">
        <SectionCard
          description="실제 API 연동 전에도 구역별 운영 지표를 어떤 밀도로 보여줄지 빠르게 검토할 수 있습니다."
          eyebrow="Zones"
          title="구역 상태"
        >
          <div className="zone-list">
            {zones.map((zone) => (
              <article className="zone-item" key={zone.name}>
                <div className="split-row">
                  <h4 className="zone-title">{zone.name}</h4>
                  <span className="badge badge--accent">{zone.status}</span>
                </div>
                <p className="zone-copy">{zone.summary}</p>
              </article>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          description="운영, IoT, 분석 담당자가 동시에 확인해야 하는 액션 아이템을 고정 영역으로 분리했습니다."
          eyebrow="Ops Queue"
          title="오늘의 할 일"
        >
          <div className="schedule-list">
            {tasks.map((task) => (
              <article className="schedule-item" key={task.title}>
                <div className="split-row">
                  <h4 className="schedule-title">{task.title}</h4>
                  <span className="badge badge--warning">{task.owner}</span>
                </div>
                <p className="schedule-copy">{task.detail}</p>
              </article>
            ))}
          </div>
        </SectionCard>
      </section>
    </div>
  )
}
