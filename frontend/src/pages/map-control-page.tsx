import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AppIcon } from '@/components/app-icon'
import { DevSurface } from '@/components/dev-surface'
import { MetricCard } from '@/components/metric-card'
import { MockupImage } from '@/components/mockup-image'
import {
  getRobotPageData,
  robotFallback,
  sendRobotControlAction,
  sendRobotZoneMove,
} from '@/lib/api/agribot'

const controlActions = [
  { id: 'pause', title: '정지', icon: 'pause_circle', tone: 'soft' },
  { id: 'resume', title: '재개', icon: 'play_circle', tone: 'soft' },
  { id: 'home', title: '복귀', icon: 'home', tone: 'soft' },
  { id: 'emergency', title: '비상 정지', icon: 'emergency_home', tone: 'danger' },
] as const

export function MapControlPage() {
  const queryClient = useQueryClient()
  const robotQuery = useQuery({
    queryKey: ['page', 'robot'],
    queryFn: getRobotPageData,
    initialData: robotFallback,
    refetchInterval: 10_000,
  })
  const controlMutation = useMutation({
    mutationFn: sendRobotControlAction,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
    },
  })
  const zoneMoveMutation = useMutation({
    mutationFn: sendRobotZoneMove,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
    },
  })
  const page = robotQuery.data
  const actionPending = controlMutation.isPending || zoneMoveMutation.isPending
  const feedbackMessage = zoneMoveMutation.isSuccess
    ? zoneMoveMutation.data
    : zoneMoveMutation.isError
      ? zoneMoveMutation.error.message
      : controlMutation.isSuccess
        ? controlMutation.data
        : controlMutation.isError
          ? controlMutation.error.message
          : null

  return (
    <div className="screen">
      <section className="metric-row metric-row--compact">
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

      <section className="map-layout">
        <DevSurface
          as="article"
          className="map-board panel"
          detail="현재 지도, 경로선, 카메라 뷰는 실제 SLAM/카메라 스트림 대신 발표용 샘플 자산으로 렌더링됩니다."
          status="sample"
          title="지도와 카메라 보드"
        >
          <div className="map-floating-card">
            <span className="panel-kicker">현재 경유지</span>
            <strong>{page.waypoint}</strong>
            <p>{page.targetLabel}</p>
          </div>

          <div className="camera-peek">
            <span className="camera-live-pill">
              <span className="live-dot" />
              시뮬레이션 프리뷰
            </span>
            <div className="camera-frame">
              <MockupImage
                alt="로봇 카메라 프리뷰 시뮬레이션"
                className="camera-frame-media"
                height="100%"
                src="/mock-images/robot-camera-preview.png"
              />
            </div>
          </div>

          <svg
            aria-hidden="true"
            className="map-overlay"
            preserveAspectRatio="xMidYMid slice"
            viewBox="0 0 800 600"
          >
            <path d="M110 110 L300 110 L300 400 L610 400 L610 220" />
            <circle cx="110" cy="110" r="7" />
            <circle cx="300" cy="110" r="7" />
            <circle cx="300" cy="400" r="7" />
            <circle className="map-pulse" cx="610" cy="400" r="12" />
            <circle cx="610" cy="400" r="8" />
          </svg>

          <div className="robot-marker">
            <div className="robot-marker-box">
              <AppIcon filled name="navigation" />
            </div>
          </div>

          <div className="map-controls">
            <button className="icon-button" type="button">
              <AppIcon name="add" />
            </button>
            <button className="icon-button" type="button">
              <AppIcon name="remove" />
            </button>
            <button className="icon-button icon-button--active" type="button">
              <AppIcon filled name="my_location" />
            </button>
          </div>
        </DevSurface>

        <aside className="map-sidebar">
          <DevSurface
            as="article"
            className="panel"
            detail="mission 진행률과 ETA는 아직 단일 runtime 체인이 없어 route/harvest 시나리오 기준 샘플 값으로 표시합니다."
            status="sample"
            title="미션 진행률"
          >
            <div className="section-head">
              <div>
                <span className="section-eyebrow">미션 진행</span>
                <h3 className="section-title">{page.progressPct}%</h3>
                <p className="section-description">{page.eta}</p>
              </div>
              <span className="table-tag table-tag--healthy">{page.missionState}</span>
            </div>
            <div className="progress-track">
              <span className="progress-fill" style={{ width: `${page.progressPct}%` }} />
            </div>
            <div className="detail-grid">
              <article className="detail-card">
                <span className="detail-label">현재 구역</span>
                <strong className="detail-value">{page.zoneLabel}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">현재 위치</span>
                <strong className="detail-value">{page.poseLabel}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">다음 목표</span>
                <strong className="detail-value">{page.targetLabel}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">주행 상태</span>
                <strong className="detail-value">{page.speed} · 배터리 {page.battery}</strong>
              </article>
            </div>
          </DevSurface>

          <DevSurface
            as="article"
            className="panel"
            detail="제어 API는 요청을 받아들이지만, 실제 ROS 명령 수행 결과와 상태 피드백은 아직 고정 응답 단계입니다."
            status="stub"
            title="로봇 제어 센터"
          >
            <div className="section-head">
              <div>
                <span className="section-eyebrow">로봇 제어</span>
                <h3 className="section-title">제어 센터</h3>
                <p className="section-description">
                  `robot/commands`, `missions/patrol/*`, `missions/return-home` 흐름을 같은 패널에 모았습니다.
                </p>
              </div>
              <span className="table-tag table-tag--warning">
                {page.source === 'live' ? '실 API' : '준비 데이터'}
              </span>
            </div>
            <div className="control-tile-grid">
              {controlActions.map((action) => (
                <button
                  className={`control-tile${action.tone === 'danger' ? ' control-tile--danger' : ''}`}
                  disabled={actionPending}
                  key={action.title}
                  onClick={() => {
                    controlMutation.mutate(action.id)
                  }}
                  type="button"
                >
                  <AppIcon
                    className="control-tile-icon"
                    filled={action.tone === 'danger'}
                    name={action.icon}
                  />
                  <span>{action.title}</span>
                </button>
              ))}
            </div>
            {feedbackMessage ? <p className="muted">{feedbackMessage}</p> : null}
          </DevSurface>

          <DevSurface
            as="article"
            className="panel"
            detail="구역 이동 요청 포맷은 잡혀 있지만 zone preset과 실제 waypoint/mission 연결은 아직 백엔드 브리지 구현이 남아 있습니다."
            status="stub"
            title="빠른 구역 이동"
          >
            <div className="section-head">
              <div>
                <span className="section-eyebrow">구역 이동</span>
                <h3 className="section-title">빠른 구역 이동</h3>
                <p className="section-description">
                  `robot/commands`의 `move_to_zone` 계약을 기준으로 운영자가 구역 단위 이동을 요청합니다.
                </p>
              </div>
            </div>
            <div className="preset-grid">
              {page.zonePresets.map((preset) => (
                <button
                  className="preset-button"
                  disabled={actionPending}
                  key={preset.id}
                  onClick={() => {
                    zoneMoveMutation.mutate(preset.id)
                  }}
                  type="button"
                >
                  <div className="split-row">
                    <div>
                      <span className="panel-kicker">{preset.id}</span>
                      <h4 className="list-title">{preset.name}</h4>
                    </div>
                    <AppIcon className="control-tile-icon" name="route" />
                  </div>
                  <p>{preset.detail}</p>
                </button>
              ))}
            </div>
          </DevSurface>

          <DevSurface
            as="article"
            className="panel"
            detail="이벤트 로그는 실제 mission event stream이 아니라 발표용 운행 로그를 시간순으로 정리한 샘플입니다."
            status="sample"
            title="이벤트 로그"
          >
            <div className="section-head">
              <div>
                <span className="section-eyebrow">이벤트 로그</span>
                <h3 className="section-title">이벤트 로그</h3>
              </div>
            </div>
            <div className="stacked-list">
              {page.logs.map((log) => (
                <article className="log-item" key={log}>
                  <span className="log-dot log-dot--accent" />
                  <div className="log-copy">
                    <p>{log}</p>
                  </div>
                </article>
              ))}
            </div>
          </DevSurface>
        </aside>
      </section>
    </div>
  )
}
