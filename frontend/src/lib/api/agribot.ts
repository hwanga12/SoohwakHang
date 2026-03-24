import { isAxiosError } from 'axios'
import { apiClient } from '@/lib/api/client'

export type CardTone = 'accent' | 'warning' | 'danger'
export type DataSource = 'live' | 'fallback'
export type HealthTone = 'healthy' | 'warning' | 'critical'

type UnknownRecord = Record<string, unknown>

export type MetricCardData = {
  label: string
  value: string
  meta: string
  tone: CardTone
}

export type LogEvent = {
  tone: CardTone
  title: string
  detail: string
  time: string
}

export type QueueItem = {
  tone: HealthTone
  label: string
  title: string
  detail: string
}

export type ZoneStatusCard = {
  id: string
  name: string
  summary: string
  tone: HealthTone
}

export type DashboardPageData = {
  source: DataSource
  heroStatus: string
  location: string
  activeTask: string
  battery: string
  batteryMeta: string
  robotLabel: string
  environmentStats: Array<{ label: string; value: string; delta: string }>
  metrics: MetricCardData[]
  events: LogEvent[]
  queue: QueueItem[]
  zones: ZoneStatusCard[]
}

export type RobotZonePreset = {
  id: string
  name: string
  detail: string
}

export type RobotPageData = {
  source: DataSource
  waypoint: string
  zoneLabel: string
  poseLabel: string
  targetLabel: string
  metrics: MetricCardData[]
  progressPct: number
  eta: string
  missionState: string
  battery: string
  speed: string
  logs: string[]
  zonePresets: RobotZonePreset[]
}

export type PlantAlertCard = {
  id: string
  severity: '심각' | '주의'
  title: string
  location: string
  action: string
}

export type PlantRow = {
  name: string
  id: string
  targetId: string
  zoneLabel: string
  positionLabel: string
  lastObserved: string
  recommendedAction: string
  health: number
  tone: HealthTone
  status: string
}

export type PlantsPageData = {
  source: DataSource
  healthSummary: string
  criticalCount: string
  activeScans: string
  growthIndex: string
  alerts: PlantAlertCard[]
  plants: PlantRow[]
}

export type DeviceCard = {
  id: string
  icon: string
  name: string
  detail: string
  accent: 'primary' | 'secondary' | 'warning' | 'neutral'
  action: 'toggle' | 'slider' | 'fan' | 'button'
  value?: string
}

export type RecommendationItem = {
  id: string
  title: string
  detail: string
  priority: string
  status: string
}

export type ActuationHistoryItem = {
  id: string
  device: string
  action: string
  result: string
  time: string
  tone: HealthTone
}

export type EnvironmentPageData = {
  source: DataSource
  recommendation: string
  metrics: MetricCardData[]
  devices: DeviceCard[]
  healthBars: Array<{ icon: string; label: string; value: number; tone: HealthTone }>
  recommendations: RecommendationItem[]
  history: ActuationHistoryItem[]
}

export type HarvestBatch = {
  route: string
  summary: string
  state: string
}

export type HarvestPageData = {
  source: DataSource
  basketState: string
  nextSwap: string
  metrics: MetricCardData[]
  batches: HarvestBatch[]
  qualityStats: Array<{ label: string; value: string }>
}

export type AlertTimelineItem = {
  id: string
  tone: CardTone
  title: string
  detail: string
  meta: string
  location: string
  acknowledged: boolean
}

export type AlertsPageData = {
  source: DataSource
  summary: string
  unreadCount: string
  criticalCount: string
  items: AlertTimelineItem[]
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function unwrapPayload<T = unknown>(payload: unknown): T | unknown {
  if (isRecord(payload) && 'data' in payload) {
    return payload.data
  }

  return payload
}

function asArray(payload: unknown): unknown[] {
  const unwrapped = unwrapPayload(payload)

  if (Array.isArray(unwrapped)) {
    return unwrapped
  }

  if (isRecord(unwrapped)) {
    for (const key of ['items', 'results', 'alerts', 'plants', 'devices', 'rows']) {
      const candidate = unwrapped[key]
      if (Array.isArray(candidate)) {
        return candidate
      }
    }
  }

  return []
}

function readString(value: unknown, fallback = ''): string {
  if (typeof value === 'string' && value.trim()) {
    return value.trim()
  }

  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }

  return fallback
}

function readNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string') {
    const parsed = Number(value.replace(/[^\d.-]/g, ''))
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }

  return fallback
}

function readBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') {
    return value
  }

  if (typeof value === 'string') {
    if (value === 'true') {
      return true
    }
    if (value === 'false') {
      return false
    }
  }

  return fallback
}

function readRecord(payload: unknown): UnknownRecord | null {
  const unwrapped = unwrapPayload(payload)
  return isRecord(unwrapped) ? unwrapped : null
}

function hasStructuredData(payload: unknown): boolean {
  const unwrapped = unwrapPayload(payload)

  if (Array.isArray(unwrapped)) {
    return unwrapped.length > 0
  }

  if (!isRecord(unwrapped)) {
    return false
  }

  const keys = Object.keys(unwrapped).filter((key) => key !== 'message')
  return keys.length > 0
}

function normalizeToneFromSeverity(value: string): HealthTone {
  const normalized = value.toLowerCase()

  if (normalized.includes('critical') || normalized.includes('심각') || normalized.includes('위험')) {
    return 'critical'
  }

  if (normalized.includes('warning') || normalized.includes('주의')) {
    return 'warning'
  }

  return 'healthy'
}

function buildPositionLabel(position: unknown, fallback = '좌표 정보 준비 중') {
  if (!isRecord(position)) {
    return fallback
  }

  const x = readNumber(position.x, Number.NaN)
  const y = readNumber(position.y, Number.NaN)

  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return fallback
  }

  return `x ${x.toFixed(1)} / y ${y.toFixed(1)}`
}

async function safeGet(path: string) {
  try {
    const response = await apiClient.get(path)
    return response.data
  } catch {
    return null
  }
}

async function postWithFallback(
  attempts: Array<{ path: string; body: unknown }>,
  successFallback: string,
) {
  for (const attempt of attempts) {
    try {
      const response = await apiClient.post(attempt.path, attempt.body)
      const payload = unwrapPayload(response.data)

      if (isRecord(payload)) {
        return (
          readString(payload.message)
          || readString(payload.status)
          || readString(payload.command_type)
          || successFallback
        )
      }

      if (typeof payload === 'string' && payload.trim()) {
        return payload
      }

      return successFallback
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 404) {
        continue
      }
    }
  }

  throw new Error('연결 가능한 API 엔드포인트를 찾지 못했습니다.')
}

export const dashboardFallback: DashboardPageData = {
  source: 'fallback',
  heroStatus: '서측 2열 순찰과 환경 점검이 함께 진행 중입니다.',
  location: 'farm_01 · 서측 2열',
  activeTask: '수확 후보 토마토 검수와 급수 권고 확인',
  battery: '82%',
  batteryMeta: '현재 적재 기준으로 2시간 10분 연속 운행 예상',
  robotLabel: 'AGR-02 · 오전 자율 순찰 루프',
  environmentStats: [
    { label: '기온', value: '24.2°C', delta: '0.4° 상승' },
    { label: '습도', value: '62%', delta: '2% 감소' },
  ],
  metrics: [
    { label: '로봇 가동률', value: '98.2%', meta: '순찰과 복귀 흐름이 안정적으로 유지됩니다.', tone: 'accent' },
    { label: '오늘 수확량', value: '142kg', meta: '오전 목표 대비 12% 앞서 있습니다.', tone: 'accent' },
    { label: '주의 알림', value: '3건', meta: '작물 이상과 설비 경고가 함께 남아 있습니다.', tone: 'warning' },
    { label: '승인 대기', value: '2건', meta: '급수와 양액 관련 권고가 대기 중입니다.', tone: 'danger' },
  ],
  events: [
    {
      tone: 'danger',
      title: 'farm01_plant_06_tomato_01 병해 의심',
      detail: '수동 검토 후 관찰 유지 또는 수확 제외 여부를 결정해야 합니다.',
      time: '09:42',
    },
    {
      tone: 'accent',
      title: 'B-12 순찰 경로 재계산 완료',
      detail: '장애물 우회 후 inspection waypoint 시퀀스로 복귀했습니다.',
      time: '09:35',
    },
    {
      tone: 'warning',
      title: '1구역 급수 승인 대기',
      detail: '토양 수분 하한선 접근으로 급수 권고가 자동 생성되었습니다.',
      time: '09:28',
    },
  ],
  queue: [
    {
      tone: 'healthy',
      label: '작물',
      title: 'farm01_plant_03_tomato_01',
      detail: 'canonical fruit ID가 준비되어 있어 수확 미션 요청으로 바로 넘길 수 있습니다.',
    },
    {
      tone: 'warning',
      label: '설비',
      title: '중앙 라인 급수 승인 검토',
      detail: '토양 수분이 하한선 아래로 내려가 수동 승인 여부를 확인해야 합니다.',
    },
    {
      tone: 'critical',
      label: '알림',
      title: '서측 3열 병해 검토 큐',
      detail: '질병 의심 개체가 수동 확인 대기열에 남아 있습니다.',
    },
  ],
  zones: [
    {
      id: 'farm_01_west',
      name: '서측 재배 라인',
      summary: '수확 후보 2건이 이 라인에 몰려 있습니다.',
      tone: 'healthy',
    },
    {
      id: 'farm_01_center',
      name: '중앙 재배 라인',
      summary: '급수 승인과 센서 동기화 확인이 필요합니다.',
      tone: 'warning',
    },
    {
      id: 'farm_01_east',
      name: '동측 재배 라인',
      summary: '수확 배치 대기 중이며 현재는 안정 상태입니다.',
      tone: 'healthy',
    },
  ],
}

export const robotFallback: RobotPageData = {
  source: 'fallback',
  waypoint: 'inspection_b12',
  zoneLabel: 'farm_01 · 서측 2열',
  poseLabel: 'map 기준 x 2.0 / y -5.9',
  targetLabel: '다음 목표 farm01_plant_06_tomato_01',
  metrics: [
    { label: '현재 모드', value: '자율 순찰', meta: 'patrol/status 기준으로 동작 중입니다.', tone: 'accent' },
    { label: '배터리', value: '82%', meta: '충전 없이 2시간 10분 운행 예상', tone: 'warning' },
    { label: '다음 목표', value: 'farm01_plant_06_tomato_01', meta: '수확 후보 토마토 근접 경로를 준비 중입니다.', tone: 'accent' },
  ],
  progressPct: 76,
  eta: '예상 완료 12분 30초',
  missionState: '이동 중',
  battery: '82%',
  speed: '1.1m/s',
  logs: [
    'B-12 점검 경유지 진입 완료',
    '서측 2열에서 fruit ID 기반 대상 큐 갱신',
    '순찰 중지 후 수확 미션으로 전환 가능',
  ],
  zonePresets: [
    { id: 'farm_01_west', name: '서측 라인', detail: '수확 후보와 병해 검토가 집중된 구역' },
    { id: 'farm_01_center', name: '중앙 라인', detail: '급수 승인과 센서 점검이 필요한 구역' },
    { id: 'farm_01_east', name: '동측 라인', detail: '다음 수확 배치가 대기 중인 구역' },
  ],
}

export const plantsFallback: PlantsPageData = {
  source: 'fallback',
  healthSummary: '95%',
  criticalCount: '03',
  activeScans: '1.2천 건',
  growthIndex: '+4.2%',
  alerts: [
    {
      id: 'alert-disease-001',
      severity: '심각',
      title: '조기 병해 의심',
      location: 'farm01_plant_06 · farm01_plant_06_tomato_01',
      action: '수동 검토 후 관찰 또는 수확 미션 전환',
    },
    {
      id: 'alert-target-001',
      severity: '주의',
      title: '수확 후보 토마토 재확인',
      location: 'farm01_plant_03 · farm01_plant_03_tomato_01',
      action: 'canonical ID 기준으로 대상 큐에 유지',
    },
  ],
  plants: [
    {
      name: '토마토 03',
      id: 'farm01_plant_03',
      targetId: 'farm01_plant_03_tomato_01',
      zoneLabel: 'farm_01 · 서측 2열',
      positionLabel: 'x 2.0 / y -6.0',
      lastObserved: '09:38',
      recommendedAction: '수확 요청 가능',
      health: 96,
      tone: 'healthy',
      status: '수확 후보',
    },
    {
      name: '토마토 06',
      id: 'farm01_plant_06',
      targetId: 'farm01_plant_06_tomato_01',
      zoneLabel: 'farm_01 · 서측 3열',
      positionLabel: 'x -2.0 / y -4.0',
      lastObserved: '09:42',
      recommendedAction: '병해 수동 검토',
      health: 71,
      tone: 'warning',
      status: '재확인 필요',
    },
    {
      name: '토마토 10',
      id: 'farm01_plant_10',
      targetId: 'farm01_plant_10_tomato_01',
      zoneLabel: 'farm_01 · 중앙 3열',
      positionLabel: 'x -2.0 / y -2.0',
      lastObserved: '09:29',
      recommendedAction: '질병 촬영 재시도',
      health: 44,
      tone: 'warning',
      status: '병해 점검',
    },
    {
      name: '토마토 15',
      id: 'farm01_plant_15',
      targetId: 'farm01_plant_15_tomato_01',
      zoneLabel: 'farm_01 · 동측 2열',
      positionLabel: 'x 2.0 / y 2.0',
      lastObserved: '09:18',
      recommendedAction: '순찰 관찰 유지',
      health: 89,
      tone: 'healthy',
      status: '순찰 관찰',
    },
  ],
}

export const environmentFallback: EnvironmentPageData = {
  source: 'fallback',
  recommendation: '1구역 토양 수분이 낮아 급수 승인을 검토하는 것이 좋습니다.',
  metrics: [
    { label: '기온', value: '24.2°C', meta: '권장 범위 상단', tone: 'accent' },
    { label: '습도', value: '62%', meta: '야간 대비 2% 감소', tone: 'warning' },
    { label: '토양 수분', value: '18.5%', meta: '급수 권고 기준선 도달', tone: 'danger' },
  ],
  devices: [
    {
      id: 'farm_01_watering',
      icon: 'water_drop',
      name: '급수 펌프',
      detail: '자동 대기 · 수동 승인 가능',
      accent: 'primary',
      action: 'toggle',
    },
    {
      id: 'farm_01_curtain',
      icon: 'curtains',
      name: '차광 커튼',
      detail: '현재 80% 개방',
      accent: 'secondary',
      action: 'slider',
      value: '80%',
    },
    {
      id: 'farm_01_fan',
      icon: 'air',
      name: '환기 팬',
      detail: '중간 세기로 동작 중',
      accent: 'neutral',
      action: 'fan',
    },
    {
      id: 'farm_01_nutrient',
      icon: 'science',
      name: '양액 주입기',
      detail: '수동 실행 대기',
      accent: 'warning',
      action: 'button',
    },
  ],
  healthBars: [
    { icon: 'router', label: '네트워크', value: 98, tone: 'healthy' },
    { icon: 'sensors', label: '센서 동기화', value: 64, tone: 'warning' },
  ],
  recommendations: [
    {
      id: 'reco-water-001',
      title: '중앙 라인 급수 승인 필요',
      detail: '토양 수분이 기준선 아래로 내려가 400ml 급수가 추천되었습니다.',
      priority: '높음',
      status: '승인 대기',
    },
    {
      id: 'reco-curtain-001',
      title: '차광 커튼 10% 추가 폐쇄 검토',
      detail: '조도와 온도 상승 폭이 동시에 커지는 구간입니다.',
      priority: '보통',
      status: '자동 적용 대기',
    },
  ],
  history: [
    {
      id: 'history-water-001',
      device: '급수 펌프',
      action: '400ml 급수 실행',
      result: '정상 완료',
      time: '09:16',
      tone: 'healthy',
    },
    {
      id: 'history-fan-001',
      device: '환기 팬',
      action: '중속 유지',
      result: '모니터링 필요',
      time: '09:12',
      tone: 'warning',
    },
    {
      id: 'history-nutrient-001',
      device: '양액 주입기',
      action: '칼슘 부스터 보류',
      result: '사용자 승인 대기',
      time: '09:04',
      tone: 'warning',
    },
  ],
}

export const harvestFallback: HarvestPageData = {
  source: 'fallback',
  basketState: '바구니 A · 68%',
  nextSwap: '35분 후 교체 예정',
  metrics: [
    { label: '오늘 수확', value: '142kg', meta: '전일 대비 18% 증가', tone: 'accent' },
    { label: '적재율', value: '68%', meta: '바구니 B 교체 예상 35분 후', tone: 'warning' },
    { label: '성공률', value: '94.8%', meta: '접근 재시도 포함', tone: 'accent' },
    { label: '실패 건수', value: '7건', meta: '미성숙 개체 접근 4건 포함', tone: 'danger' },
  ],
  batches: [
    {
      route: '남측 1열 수확 배치',
      summary: '완숙 토마토 우선 수확과 적재를 함께 진행합니다.',
      state: '진행 중',
    },
    {
      route: '동측 3열 대기 배치',
      summary: '다음 바구니 교체 이후 바로 시작할 예정입니다.',
      state: '예정',
    },
    {
      route: '출하 바구니 라벨 교체',
      summary: '출하 큐와 적재 ID 정합성을 맞추기 위한 작업입니다.',
      state: '대기',
    },
  ],
  qualityStats: [
    { label: '완숙 비율', value: '81%' },
    { label: '평균 수확 시간', value: '42초/개' },
    { label: '적재 중량 오차', value: '1.8%' },
  ],
}

export const alertsFallback: AlertsPageData = {
  source: 'fallback',
  summary: '병해, 센서, 장치 경고를 같은 기준으로 검토할 수 있는 알림 센터입니다.',
  unreadCount: '3건',
  criticalCount: '1건',
  items: [
    {
      id: 'alert-disease-001',
      tone: 'danger',
      title: 'farm01_plant_06_tomato_01 병해 의심',
      detail: '잎 가장자리 갈변과 흰가루 패턴이 동시에 검출되었습니다.',
      meta: '2분 전 · 전면 좌측 카메라',
      location: 'farm_01 · 서측 3열',
      acknowledged: false,
    },
    {
      id: 'alert-sensor-001',
      tone: 'warning',
      title: '조도 센서 패킷 유실',
      detail: '중앙 라인 조도 센서가 3회 연속 업데이트를 놓쳤습니다.',
      meta: '14분 전 · 조도 센서 B',
      location: 'farm_01 · 중앙 라인',
      acknowledged: false,
    },
    {
      id: 'alert-water-001',
      tone: 'accent',
      title: '급수 시퀀스 정상 종료',
      detail: '1구역 급수 실행이 권장량 기준으로 정상 완료됐습니다.',
      meta: '26분 전 · 급수 장치 A',
      location: 'farm_01 · 중앙 라인',
      acknowledged: true,
    },
  ],
}

export async function getDashboardPageData(): Promise<DashboardPageData> {
  const [summaryPayload, robotPayload, envPayload, alertsPayload, harvestPayload, zonesPayload] =
    await Promise.all([
      safeGet('/dashboard/summary'),
      safeGet('/robot/status'),
      safeGet('/environment/latest'),
      safeGet('/alerts'),
      safeGet('/harvests/stats'),
      safeGet('/zones'),
    ])

  const live =
    hasStructuredData(summaryPayload)
    || hasStructuredData(robotPayload)
    || hasStructuredData(envPayload)
    || hasStructuredData(alertsPayload)
    || hasStructuredData(harvestPayload)
    || hasStructuredData(zonesPayload)

  const robot = readRecord(robotPayload)
  const env = readRecord(envPayload)
  const summary = readRecord(summaryPayload)
  const alerts = asArray(alertsPayload)
  const harvest = readRecord(harvestPayload)
  const zones = asArray(zonesPayload)

  const metrics = [...dashboardFallback.metrics]
  metrics[0] = {
    ...metrics[0],
    value:
      readString(summary?.robot_uptime_pct)
      || readString(robot?.uptime_pct)
      || readString(robot?.operating_rate)
      || metrics[0].value,
  }
  metrics[1] = {
    ...metrics[1],
    value:
      readString(harvest?.today_weight_kg)
      || readString(harvest?.today_harvest_kg)
      || readString(harvest?.total_weight_kg)
      || metrics[1].value,
  }
  metrics[2] = {
    ...metrics[2],
    value: alerts.length > 0 ? `${alerts.length}건` : metrics[2].value,
  }

  const events =
    alerts
      .slice(0, 3)
      .map((item, index): LogEvent | null => {
        if (!isRecord(item)) {
          return null
        }

        const severity = readString(item.severity) || readString(item.level)
        const tone: CardTone =
          normalizeToneFromSeverity(severity) === 'critical'
            ? 'danger'
            : normalizeToneFromSeverity(severity) === 'warning'
              ? 'warning'
              : 'accent'

        return {
          tone,
          title: readString(item.title) || `알림 ${index + 1}`,
          detail:
            readString(item.detail)
            || readString(item.description)
            || readString(item.message)
            || '상세 내용이 아직 정의되지 않았습니다.',
          time:
            readString(item.time)
            || readString(item.detected_at)
            || readString(item.created_at)
            || '방금 전',
        }
      })
      .filter((item): item is LogEvent => item !== null)

  const zoneCards =
    zones
      .slice(0, 3)
      .map((item, index): ZoneStatusCard | null => {
        if (!isRecord(item)) {
          return null
        }

        const name = readString(item.name) || `구역 ${index + 1}`
        return {
          id: readString(item.id) || `zone-${index + 1}`,
          name,
          summary:
            readString(item.description)
            || `${name} 상태를 점검할 수 있습니다.`,
          tone: index === 1 ? 'warning' : 'healthy',
        }
      })
      .filter((item): item is ZoneStatusCard => item !== null)

  return {
    ...dashboardFallback,
    source: live ? 'live' : 'fallback',
    heroStatus:
      readString(robot?.status)
      || readString(robot?.current_mode)
      || dashboardFallback.heroStatus,
    location:
      readString(robot?.zone_label)
      || readString(robot?.current_zone_id)
      || readString(robot?.current_zone)
      || dashboardFallback.location,
    activeTask:
      readString(robot?.active_task)
      || readString(summary?.active_task)
      || dashboardFallback.activeTask,
    battery:
      readString(robot?.battery)
      || readString(robot?.battery_level)
      || dashboardFallback.battery,
    batteryMeta:
      readString(robot?.battery_eta)
      || readString(robot?.battery_message)
      || dashboardFallback.batteryMeta,
    robotLabel:
      readString(robot?.robot_id)
      || readString(robot?.label)
      || dashboardFallback.robotLabel,
    environmentStats: [
      {
        label: '기온',
        value: readString(env?.temperature) || dashboardFallback.environmentStats[0].value,
        delta: readString(env?.temperature_delta) || dashboardFallback.environmentStats[0].delta,
      },
      {
        label: '습도',
        value: readString(env?.humidity) || dashboardFallback.environmentStats[1].value,
        delta: readString(env?.humidity_delta) || dashboardFallback.environmentStats[1].delta,
      },
    ],
    metrics,
    events: events.length > 0 ? events : dashboardFallback.events,
    zones: zoneCards.length > 0 ? zoneCards : dashboardFallback.zones,
  }
}

export async function getRobotPageData(): Promise<RobotPageData> {
  const [statusPayload, posePayload, zonesPayload] = await Promise.all([
    safeGet('/robot/status'),
    safeGet('/robot/pose'),
    safeGet('/zones'),
  ])

  const live =
    hasStructuredData(statusPayload)
    || hasStructuredData(posePayload)
    || hasStructuredData(zonesPayload)
  const status = readRecord(statusPayload)
  const pose = readRecord(posePayload)
  const poseRecord = readRecord(pose?.pose)
  const zones = asArray(zonesPayload)
  const metrics = [...robotFallback.metrics]

  metrics[0] = {
    ...metrics[0],
    value: readString(status?.mode) || readString(status?.status) || metrics[0].value,
  }
  metrics[1] = {
    ...metrics[1],
    value:
      readString(status?.battery)
      || readString(status?.battery_level)
      || metrics[1].value,
    meta: readString(status?.battery_eta) || metrics[1].meta,
  }
  metrics[2] = {
    ...metrics[2],
    value:
      readString(status?.next_target_crop_id)
      || readString(status?.next_waypoint)
      || readString(status?.waypoint_id)
      || metrics[2].value,
    meta:
      readString(status?.next_goal)
      || readString(status?.mission_name)
      || metrics[2].meta,
  }

  const zonePresets =
    zones
      .map((item, index): RobotZonePreset | null => {
        if (!isRecord(item)) {
          return null
        }

        const name = readString(item.name) || `구역 ${index + 1}`
        return {
          id: readString(item.id) || `zone-${index + 1}`,
          name,
          detail: readString(item.description) || `${name} 빠른 이동 요청`,
        }
      })
      .filter((item): item is RobotZonePreset => item !== null)

  return {
    ...robotFallback,
    source: live ? 'live' : 'fallback',
    waypoint:
      readString(status?.waypoint_id)
      || readString(status?.next_waypoint)
      || robotFallback.waypoint,
    zoneLabel:
      readString(status?.zone_label)
      || readString(status?.current_zone_id)
      || readString(status?.current_zone)
      || readString(pose?.current_zone_id)
      || robotFallback.zoneLabel,
    poseLabel:
      poseRecord !== null
        ? buildPositionLabel(poseRecord, robotFallback.poseLabel)
        : robotFallback.poseLabel,
    targetLabel:
      readString(status?.next_target_crop_id)
      || readString(status?.target_crop_id)
      || robotFallback.targetLabel,
    metrics,
    progressPct: readNumber(status?.mission_progress_pct, robotFallback.progressPct),
    eta:
      readString(status?.eta)
      || readString(status?.estimated_completion)
      || robotFallback.eta,
    missionState:
      readString(status?.mission_state)
      || readString(status?.status)
      || robotFallback.missionState,
    battery:
      readString(status?.battery)
      || readString(status?.battery_level)
      || robotFallback.battery,
    speed: readString(status?.speed_mps) || readString(status?.speed) || robotFallback.speed,
    zonePresets: zonePresets.length > 0 ? zonePresets : robotFallback.zonePresets,
  }
}

export async function getPlantsPageData(): Promise<PlantsPageData> {
  const [plantsPayload, alertsPayload] = await Promise.all([
    safeGet('/plants'),
    safeGet('/alerts'),
  ])

  const live = hasStructuredData(plantsPayload) || hasStructuredData(alertsPayload)
  const alerts = asArray(alertsPayload)
  const plants = asArray(plantsPayload)

  const parsedAlerts =
    alerts
      .slice(0, 3)
      .map((item, index): PlantAlertCard | null => {
        if (!isRecord(item)) {
          return null
        }

        const tone = normalizeToneFromSeverity(readString(item.severity) || readString(item.level))

        return {
          id: readString(item.id) || `alert-${index + 1}`,
          severity: tone === 'critical' ? '심각' : '주의',
          title: readString(item.title) || `질병 감지 ${index + 1}`,
          location:
            readString(item.location)
            || readString(item.target_crop_id)
            || readString(item.zone_id)
            || '위치 정보 없음',
          action:
            readString(item.action)
            || readString(item.detail)
            || readString(item.message)
            || '추가 검수가 필요합니다.',
        }
      })
      .filter((item): item is PlantAlertCard => item !== null)

  const parsedPlants =
    plants
      .slice(0, 6)
      .map((item, index): PlantRow | null => {
        if (!isRecord(item)) {
          return null
        }

        const health = readNumber(item.health_score, 0) || readNumber(item.health, 0) || 70
        const tone: HealthTone =
          health < 35
            ? 'critical'
            : health < 75 || readBoolean(item.needs_water)
              ? 'warning'
              : 'healthy'

        return {
          name: readString(item.name) || readString(item.crop_name) || `작물 ${index + 1}`,
          id: readString(item.id) || readString(item.plant_id) || `plant-${index + 1}`,
          targetId:
            readString(item.target_fruit_id)
            || readString(item.fruit_id)
            || readString(item.tomato_id)
            || readString(item.id)
            || `target-${index + 1}`,
          zoneLabel:
            readString(item.zone_label)
            || readString(item.zone_id)
            || plantsFallback.plants[Math.min(index, plantsFallback.plants.length - 1)]?.zoneLabel
            || '구역 정보 준비 중',
          positionLabel:
            buildPositionLabel(
              item.position,
              plantsFallback.plants[Math.min(index, plantsFallback.plants.length - 1)]?.positionLabel
              || '좌표 정보 준비 중',
            ),
          lastObserved:
            readString(item.last_observed_at)
            || readString(item.last_observed)
            || plantsFallback.plants[Math.min(index, plantsFallback.plants.length - 1)]?.lastObserved
            || '-',
          recommendedAction:
            readBoolean(item.ready_to_harvest)
              ? '수확 요청 가능'
              : readBoolean(item.needs_water)
                ? '급수 우선 확인'
                : plantsFallback.plants[Math.min(index, plantsFallback.plants.length - 1)]?.recommendedAction
                  || '추가 관찰 유지',
          health,
          tone,
          status:
            readString(item.status)
            || readString(item.stage)
            || readString(item.growth_stage)
            || (readBoolean(item.ready_to_harvest) ? '수확 후보' : '관측 중'),
        }
      })
      .filter((item): item is PlantRow => item !== null)

  return {
    ...plantsFallback,
    source: live ? 'live' : 'fallback',
    criticalCount:
      parsedAlerts.length > 0
        ? String(parsedAlerts.length).padStart(2, '0')
        : plantsFallback.criticalCount,
    alerts: parsedAlerts.length > 0 ? parsedAlerts : plantsFallback.alerts,
    plants: parsedPlants.length > 0 ? parsedPlants : plantsFallback.plants,
  }
}

export async function getEnvironmentPageData(): Promise<EnvironmentPageData> {
  const [envPayload, devicePayload, recommendationPayload, historyPayload] = await Promise.all([
    safeGet('/environment/latest'),
    safeGet('/iot/devices'),
    safeGet('/actuations/recommendations'),
    safeGet('/actuations/history'),
  ])

  const live =
    hasStructuredData(envPayload)
    || hasStructuredData(devicePayload)
    || hasStructuredData(recommendationPayload)
    || hasStructuredData(historyPayload)

  const env = readRecord(envPayload)
  const devices = asArray(devicePayload)
  const recommendations = asArray(recommendationPayload)
  const history = asArray(historyPayload)
  const metrics = [...environmentFallback.metrics]

  metrics[0] = {
    ...metrics[0],
    value: readString(env?.temperature) || metrics[0].value,
    meta: readString(env?.temperature_delta) || metrics[0].meta,
  }
  metrics[1] = {
    ...metrics[1],
    value: readString(env?.humidity) || metrics[1].value,
    meta: readString(env?.humidity_delta) || metrics[1].meta,
  }
  metrics[2] = {
    ...metrics[2],
    value:
      readString(env?.soil_moisture)
      || readString(env?.soil_moisture_percent)
      || metrics[2].value,
    meta: readString(env?.soil_status) || metrics[2].meta,
  }

  const parsedDevices =
    devices
      .map((item, index): DeviceCard | null => {
        if (!isRecord(item)) {
          return null
        }

        const deviceType = (readString(item.device_type) || '').toLowerCase()
        const name =
          readString(item.display_name)
          || readString(item.device_name)
          || readString(item.name)
          || readString(item.device_id)

        if (!name) {
          return null
        }

        if (deviceType.includes('water')) {
          return {
            id: readString(item.id) || `device-${index + 1}`,
            icon: 'water_drop',
            name,
            detail: readString(item.current_state) || readString(item.state) || '장치 연결됨',
            accent: 'primary',
            action: 'toggle',
          }
        }

        if (deviceType.includes('curtain')) {
          return {
            id: readString(item.id) || `device-${index + 1}`,
            icon: 'curtains',
            name,
            detail: readString(item.current_state) || readString(item.state) || '커튼 위치 제어',
            accent: 'secondary',
            action: 'slider',
            value:
              readString(item.opening_ratio)
              || readString(item.current_value)
              || readString(item.target_value),
          }
        }

        if (deviceType.includes('fan')) {
          return {
            id: readString(item.id) || `device-${index + 1}`,
            icon: 'air',
            name,
            detail: readString(item.current_state) || readString(item.state) || '환기 제어',
            accent: 'neutral',
            action: 'fan',
          }
        }

        if (deviceType.includes('nutrient')) {
          return {
            id: readString(item.id) || `device-${index + 1}`,
            icon: 'science',
            name,
            detail: readString(item.current_state) || readString(item.state) || '대기',
            accent: 'warning',
            action: 'button',
          }
        }

        return null
      })
      .filter((item): item is DeviceCard => item !== null)

  const parsedRecommendations =
    recommendations
      .slice(0, 3)
      .map((item, index): RecommendationItem | null => {
        if (!isRecord(item)) {
          return null
        }

        return {
          id: readString(item.id) || `recommendation-${index + 1}`,
          title:
            readString(item.title)
            || readString(item.reason_text)
            || `추천 ${index + 1}`,
          detail:
            readString(item.detail)
            || readString(item.message)
            || readString(item.reason_text)
            || '세부 설명이 아직 연결되지 않았습니다.',
          priority:
            readString(item.priority)
            || readString(item.severity)
            || '보통',
          status:
            readString(item.status)
            || '대기',
        }
      })
      .filter((item): item is RecommendationItem => item !== null)

  const parsedHistory =
    history
      .slice(0, 4)
      .map((item, index): ActuationHistoryItem | null => {
        if (!isRecord(item)) {
          return null
        }

        const resultValue =
          readString(item.result)
          || readString(item.command_status)
          || readString(item.status)
          || '기록됨'
        const tone = normalizeToneFromSeverity(resultValue)

        return {
          id: readString(item.command_id) || `history-${index + 1}`,
          device:
            readString(item.device_name)
            || readString(item.device_id)
            || `장치 ${index + 1}`,
          action:
            readString(item.command_type)
            || readString(item.action_type)
            || '제어 명령',
          result: resultValue,
          time:
            readString(item.finished_at)
            || readString(item.started_at)
            || readString(item.executed_at)
            || '-',
          tone,
        }
      })
      .filter((item): item is ActuationHistoryItem => item !== null)

  const recommendationRecord = recommendations[0]
  const recommendationText =
    isRecord(recommendationRecord)
      ? readString(recommendationRecord.title)
        || readString(recommendationRecord.message)
        || readString(recommendationRecord.reason_text)
      : ''

  return {
    ...environmentFallback,
    source: live ? 'live' : 'fallback',
    recommendation:
      recommendationText
      || readString(env?.recommendation)
      || environmentFallback.recommendation,
    metrics,
    devices: parsedDevices.length > 0 ? parsedDevices.slice(0, 4) : environmentFallback.devices,
    recommendations:
      parsedRecommendations.length > 0 ? parsedRecommendations : environmentFallback.recommendations,
    history: parsedHistory.length > 0 ? parsedHistory : environmentFallback.history,
  }
}

export async function getHarvestPageData(): Promise<HarvestPageData> {
  const [statsPayload, harvestsPayload] = await Promise.all([
    safeGet('/harvests/stats'),
    safeGet('/harvests'),
  ])

  const live = hasStructuredData(statsPayload) || hasStructuredData(harvestsPayload)
  const stats = readRecord(statsPayload)
  const rows = asArray(harvestsPayload)
  const metrics = [...harvestFallback.metrics]

  metrics[0] = {
    ...metrics[0],
    value:
      readString(stats?.today_weight_kg)
      || readString(stats?.today_harvest_kg)
      || metrics[0].value,
  }
  metrics[1] = {
    ...metrics[1],
    value: readString(stats?.basket_fill_rate) || metrics[1].value,
  }
  metrics[2] = {
    ...metrics[2],
    value: readString(stats?.success_rate) || metrics[2].value,
  }
  metrics[3] = {
    ...metrics[3],
    value: readString(stats?.failed_count) || metrics[3].value,
  }

  const batches =
    rows
      .slice(0, 3)
      .map((item, index): HarvestBatch | null => {
        if (!isRecord(item)) {
          return null
        }

        return {
          route:
            readString(item.route_id)
            || readString(item.batch_id)
            || readString(item.name)
            || `harvest-batch-${index + 1}`,
          summary:
            readString(item.summary)
            || readString(item.detail)
            || readString(item.message)
            || '수확 배치 정보가 아직 축약 형태로만 제공됩니다.',
          state: readString(item.state) || readString(item.status) || '진행 중',
        }
      })
      .filter((item): item is HarvestBatch => item !== null)

  return {
    ...harvestFallback,
    source: live ? 'live' : 'fallback',
    basketState:
      readString(stats?.basket_state)
      || readString(stats?.basket_fill_rate)
      || harvestFallback.basketState,
    nextSwap: readString(stats?.next_swap_eta) || harvestFallback.nextSwap,
    metrics,
    batches: batches.length > 0 ? batches : harvestFallback.batches,
  }
}

export async function getAlertsPageData(): Promise<AlertsPageData> {
  const alertsPayload = await safeGet('/alerts')
  const live = hasStructuredData(alertsPayload)
  const alerts = asArray(alertsPayload)

  const items =
    alerts
      .slice(0, 8)
      .map((item, index): AlertTimelineItem | null => {
        if (!isRecord(item)) {
          return null
        }

        const severity = readString(item.severity) || readString(item.level)
        const healthTone = normalizeToneFromSeverity(severity)
        const tone: CardTone =
          healthTone === 'critical' ? 'danger' : healthTone === 'warning' ? 'warning' : 'accent'

        return {
          id: readString(item.id) || `alert-${index + 1}`,
          tone,
          title: readString(item.title) || `알림 ${index + 1}`,
          detail:
            readString(item.detail)
            || readString(item.message)
            || readString(item.description)
            || '세부 설명이 아직 연결되지 않았습니다.',
          meta:
            readString(item.detected_at)
            || readString(item.created_at)
            || readString(item.time)
            || '방금 전',
          location:
            readString(item.location)
            || readString(item.target_crop_id)
            || readString(item.zone_id)
            || '위치 정보 없음',
          acknowledged:
            readBoolean(item.is_acked)
            || readBoolean(item.acknowledged)
            || Boolean(readString(item.acknowledged_at)),
        }
      })
      .filter((item): item is AlertTimelineItem => item !== null)

  const unreadCount = items.filter((item) => !item.acknowledged).length
  const criticalCount = items.filter((item) => item.tone === 'danger').length

  return {
    ...alertsFallback,
    source: live ? 'live' : 'fallback',
    unreadCount: items.length > 0 ? `${unreadCount}건` : alertsFallback.unreadCount,
    criticalCount: items.length > 0 ? `${criticalCount}건` : alertsFallback.criticalCount,
    items: items.length > 0 ? items : alertsFallback.items,
  }
}

export async function sendRobotControlAction(
  action: 'pause' | 'resume' | 'home' | 'emergency',
) {
  const robotId = 'AGR-02'

  if (action === 'pause') {
    return postWithFallback(
      [
        {
          path: '/missions/patrol/stop',
          body: {
            robot_id: robotId,
            requested_by: 'frontend-operator',
            reason: 'ui_pause',
          },
        },
        {
          path: '/robot/commands',
          body: {
            robot_id: robotId,
            requested_by: 'frontend-operator',
            command_type: 'pause_patrol',
          },
        },
      ],
      '순찰 중지 요청을 보냈습니다.',
    )
  }

  if (action === 'resume') {
    return postWithFallback(
      [
        {
          path: '/robot/commands',
          body: {
            robot_id: robotId,
            requested_by: 'frontend-operator',
            command_type: 'resume_patrol',
          },
        },
      ],
      '순찰 재개 요청을 보냈습니다.',
    )
  }

  if (action === 'home') {
    return postWithFallback(
      [
        {
          path: '/missions/return-home',
          body: {
            robot_id: robotId,
            requested_by: 'frontend-operator',
          },
        },
        {
          path: '/robot/commands',
          body: {
            robot_id: robotId,
            requested_by: 'frontend-operator',
            command_type: 'return_home',
          },
        },
      ],
      '홈 복귀 요청을 보냈습니다.',
    )
  }

  return postWithFallback(
    [
      {
        path: '/robot/commands',
        body: {
          robot_id: robotId,
          requested_by: 'frontend-operator',
          command_type: 'emergency_stop',
        },
      },
    ],
    '비상 정지 요청을 보냈습니다.',
  )
}

export async function sendRobotZoneMove(zoneId: string) {
  return postWithFallback(
    [
      {
        path: '/robot/commands',
        body: {
          robot_id: 'AGR-02',
          requested_by: 'frontend-operator',
          command_type: 'move_to_zone',
          target_zone_id: zoneId,
        },
      },
    ],
    `${zoneId} 이동 요청을 보냈습니다.`,
  )
}

export async function requestHarvestMission({
  plantId,
  fruitId,
}: {
  plantId: string
  fruitId: string
}) {
  return postWithFallback(
    [
      {
        path: '/missions/harvest',
        body: {
          robot_id: 'AGR-02',
          plant_id: plantId,
          fruit_id: fruitId,
          requested_by: 'frontend-operator',
        },
      },
    ],
    `${fruitId} 수확 요청을 보냈습니다.`,
  )
}

export async function acknowledgeAlert(alertId: string) {
  return postWithFallback(
    [
      {
        path: `/alerts/${alertId}/ack`,
        body: {
          acknowledged_by: 'frontend-operator',
        },
      },
    ],
    `${alertId} 알림을 읽음 처리했습니다.`,
  )
}

export async function approveWateringRecommendation() {
  return postWithFallback(
    [
      {
        path: '/actuations/recommendations/reco-water-001/approve',
        body: {
          reviewed_by: 'frontend-operator',
          auto_execute: true,
        },
      },
      {
        path: '/actuations/watering',
        body: {
          zone_id: 'farm_01',
          device_id: 'farm_01_watering',
          target_value: 400,
          requested_by: 'frontend-operator',
          request_source: 'environment_page',
          recommendation_id: 'reco-water-001',
        },
      },
    ],
    '급수 승인 요청을 보냈습니다.',
  )
}

export async function triggerNutrientInjection() {
  return postWithFallback(
    [
      {
        path: '/actuations/nutrients',
        body: {
          zone_id: 'farm_01',
          device_id: 'farm_01_nutrient',
          target_value: 120,
          requested_by: 'frontend-operator',
          request_source: 'environment_page',
          recommendation_id: 'manual-nutrient-001',
        },
      },
    ],
    '영양제 투입 요청을 보냈습니다.',
  )
}
