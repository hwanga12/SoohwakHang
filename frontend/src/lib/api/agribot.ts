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
}

export type RobotPageData = {
  source: DataSource
  waypoint: string
  zoneLabel: string
  metrics: MetricCardData[]
  progressPct: number
  eta: string
  missionState: string
  battery: string
  speed: string
  logs: string[]
}

export type PlantAlertCard = {
  severity: '심각' | '주의'
  title: string
  location: string
  action: string
}

export type PlantRow = {
  name: string
  id: string
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
  icon: string
  name: string
  detail: string
  accent: 'primary' | 'secondary' | 'warning' | 'neutral'
  action: 'toggle' | 'slider' | 'fan' | 'button'
  value?: string
}

export type EnvironmentPageData = {
  source: DataSource
  recommendation: string
  metrics: MetricCardData[]
  devices: DeviceCard[]
  healthBars: Array<{ icon: string; label: string; value: number; tone: HealthTone }>
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
  heroStatus: '1구역 순찰 중',
  location: 'farm_01 / B-12',
  activeTask: '잎 분석 + 수분 모니터링',
  battery: '85%',
  batteryMeta: '충전 없이 2시간 10분 예상',
  robotLabel: 'AGR-02 · 자율 순찰 루프',
  environmentStats: [
    { label: '기온', value: '24.5°C', delta: '+1.2°' },
    { label: '습도', value: '65%', delta: '-4%' },
  ],
  metrics: [
    { label: '로봇 가동률', value: '98.2%', meta: 'patrol mission 안정적 유지', tone: 'accent' },
    { label: '오늘 수확량', value: '142 kg', meta: '목표 대비 12% 초과', tone: 'accent' },
    { label: '주의 알림', value: '3건', meta: '1건은 즉시 확인 필요', tone: 'warning' },
    { label: '점검 장치', value: '2대', meta: 'fan, nutrient pump 확인', tone: 'danger' },
  ],
  events: [
    {
      tone: 'danger',
      title: '2구역 잎 질병 감지',
      detail: '확률 94.2%로 녹병이 의심되어 수동 검수 대기열에 올랐습니다.',
      time: '09:42',
    },
    {
      tone: 'accent',
      title: '순찰 경로 B-12 재계산 성공',
      detail: '로봇이 장애 구간을 우회하고 정상 패트롤 루프를 이어갑니다.',
      time: '09:35',
    },
    {
      tone: 'warning',
      title: '토양 수분 하한 접근',
      detail: '1구역 급수 추천이 승인 대기 상태로 유지되고 있습니다.',
      time: '09:28',
    },
  ],
  queue: [
    {
      tone: 'healthy',
      label: 'B Zone',
      title: '광량 보정 필요',
      detail: '차광막 10% 닫힘과 환기량 상향을 함께 추천합니다.',
    },
    {
      tone: 'warning',
      label: 'C Zone',
      title: '수확 대기 개체 18주',
      detail: '오전 배치가 끝나면 basket-B 교체 후 수확 미션을 붙일 수 있습니다.',
    },
    {
      tone: 'critical',
      label: 'A-03',
      title: '병해 수동 검토 대기',
      detail: '비전 판독 이미지를 인력 검수 큐로 넘겨 최종 확정이 필요합니다.',
    },
  ],
}

export const robotFallback: RobotPageData = {
  source: 'fallback',
  waypoint: 'WP-04',
  zoneLabel: '구역 B-12',
  metrics: [
    { label: '현재 모드', value: 'Patrol', meta: 'farm_01 lane loop', tone: 'accent' },
    { label: '배터리', value: '82%', meta: '충전 없이 2시간 10분 예상', tone: 'warning' },
    { label: '다음 목표', value: 'WP-04', meta: '병해 확인 포인트 접근', tone: 'accent' },
  ],
  progressPct: 75,
  eta: '예상 완료 12분 45초',
  missionState: '이동 중',
  battery: '82%',
  speed: '1.2m/s',
  logs: [
    '구역 B-12 자율 경로 재계산 성공',
    '센서 진단: 토양 수분 프로브 초기화 완료',
    '일일 정기 점검 프로세스 시작됨',
  ],
}

export const plantsFallback: PlantsPageData = {
  source: 'fallback',
  healthSummary: '95%',
  criticalCount: '05',
  activeScans: '1.2k',
  growthIndex: '+4.2%',
  alerts: [
    {
      severity: '심각',
      title: '조기 겹무늬병 의심',
      location: '2구역 · 3열 · CR-0982',
      action: '격리 및 수동 검수 요청',
    },
    {
      severity: '주의',
      title: '흰가루병 패턴 감지',
      location: '4구역 · 12열 · CR-1044',
      action: '추가 촬영 후 비교 판독',
    },
  ],
  plants: [
    { name: '에어룸 토마토', id: 'CR-0982', health: 98, tone: 'healthy', status: '결실기' },
    { name: '피망', id: 'CR-1044', health: 65, tone: 'warning', status: '성장기' },
    { name: '오이', id: 'CR-0855', health: 24, tone: 'critical', status: '육묘기' },
    { name: '방울토마토', id: 'CR-1128', health: 91, tone: 'healthy', status: '수확 대기' },
  ],
}

export const environmentFallback: EnvironmentPageData = {
  source: 'fallback',
  recommendation: '1구역 토양 수분 부족. 급수 시작?',
  metrics: [
    { label: '기온', value: '24.2°C', meta: '↑0.4°', tone: 'accent' },
    { label: '습도', value: '62%', meta: '↓2%', tone: 'warning' },
    { label: '토양 수분', value: '18.5%', meta: '위험 수준', tone: 'danger' },
  ],
  devices: [
    {
      icon: 'water_drop',
      name: '워터 펌프',
      detail: '자동 순환 중',
      accent: 'primary',
      action: 'toggle',
    },
    {
      icon: 'curtains',
      name: '천장 커튼',
      detail: '80% 개방',
      accent: 'secondary',
      action: 'slider',
      value: '80%',
    },
    {
      icon: 'air',
      name: '환풍기',
      detail: '중속 운전',
      accent: 'neutral',
      action: 'fan',
    },
    {
      icon: 'science',
      name: '영양제',
      detail: '대기',
      accent: 'warning',
      action: 'button',
    },
  ],
  healthBars: [
    { icon: 'router', label: '네트워크', value: 98, tone: 'healthy' },
    { icon: 'sensors', label: '센서 동기화', value: 42, tone: 'warning' },
  ],
}

export const harvestFallback: HarvestPageData = {
  source: 'fallback',
  basketState: 'basket-A · 68%',
  nextSwap: '35분 후',
  metrics: [
    { label: '오늘 수확', value: '142 kg', meta: '전일 대비 18% 증가', tone: 'accent' },
    { label: '적재율', value: '68%', meta: 'basket-B 교체 예상 35분 후', tone: 'warning' },
    { label: '성공률', value: '94.8%', meta: '접근 재시도 포함', tone: 'accent' },
    { label: '실패 건수', value: '7건', meta: '미성숙 개체 접근 4건', tone: 'danger' },
  ],
  batches: [
    {
      route: 'farm_01_harvest_lane_01',
      summary: '남측 라인 완숙 과실 우선 수확',
      state: '진행 중',
    },
    {
      route: 'farm_01_harvest_lane_03',
      summary: '우측 3열 대칭 라인 준비 완료',
      state: '예정',
    },
    {
      route: 'basket relabel',
      summary: '출하 대기 바구니 QR 라벨 갱신',
      state: '대기',
    },
  ],
  qualityStats: [
    { label: '완숙 비율', value: '81%' },
    { label: '평균 수확 시간', value: '42초/개' },
    { label: '적재 중량 오차', value: '1.8%' },
  ],
}

export async function getDashboardPageData(): Promise<DashboardPageData> {
  const [summaryPayload, robotPayload, envPayload, alertsPayload, harvestPayload] =
    await Promise.all([
      safeGet('/dashboard/summary'),
      safeGet('/robot/status'),
      safeGet('/environment/latest'),
      safeGet('/alerts'),
      safeGet('/harvests/stats'),
    ])

  const live =
    hasStructuredData(summaryPayload)
    || hasStructuredData(robotPayload)
    || hasStructuredData(envPayload)
    || hasStructuredData(alertsPayload)
    || hasStructuredData(harvestPayload)

  const robot = readRecord(robotPayload)
  const env = readRecord(envPayload)
  const summary = readRecord(summaryPayload)
  const alerts = asArray(alertsPayload)
  const harvest = readRecord(harvestPayload)

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

        const level = readString(item.severity) || readString(item.level)
        const tone: CardTone =
          level.includes('critical') || level.includes('심각')
            ? 'danger'
            : level.includes('warn') || level.includes('주의')
              ? 'warning'
              : 'accent'

        return {
          tone,
          title:
            readString(item.title)
            || readString(item.name)
            || `알림 ${index + 1}`,
          detail:
            readString(item.detail)
            || readString(item.description)
            || readString(item.message)
            || '상세 내용이 아직 정의되지 않았습니다.',
          time: readString(item.time) || readString(item.created_at) || '방금 전',
        }
      })
      .filter((item): item is LogEvent => item !== null) || []

  return {
    ...dashboardFallback,
    source: live ? 'live' : 'fallback',
    heroStatus:
      readString(robot?.status)
      || readString(robot?.current_mode)
      || dashboardFallback.heroStatus,
    location:
      readString(robot?.zone_label)
      || readString(robot?.current_zone)
      || dashboardFallback.location,
    activeTask:
      readString(robot?.active_task)
      || readString(summary?.active_task)
      || dashboardFallback.activeTask,
    battery: readString(robot?.battery) || dashboardFallback.battery,
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
  }
}

export async function getRobotPageData(): Promise<RobotPageData> {
  const [statusPayload, posePayload] = await Promise.all([
    safeGet('/robot/status'),
    safeGet('/robot/pose'),
  ])

  const live = hasStructuredData(statusPayload) || hasStructuredData(posePayload)
  const status = readRecord(statusPayload)
  const pose = readRecord(posePayload)
  const metrics = [...robotFallback.metrics]

  metrics[0] = {
    ...metrics[0],
    value: readString(status?.mode) || readString(status?.status) || metrics[0].value,
  }
  metrics[1] = {
    ...metrics[1],
    value: readString(status?.battery) || metrics[1].value,
    meta: readString(status?.battery_eta) || metrics[1].meta,
  }
  metrics[2] = {
    ...metrics[2],
    value:
      readString(status?.next_waypoint)
      || readString(status?.waypoint_id)
      || metrics[2].value,
    meta:
      readString(status?.next_goal)
      || readString(status?.mission_name)
      || metrics[2].meta,
  }

  return {
    ...robotFallback,
    source: live ? 'live' : 'fallback',
    waypoint:
      readString(status?.waypoint_id)
      || readString(status?.next_waypoint)
      || robotFallback.waypoint,
    zoneLabel:
      readString(status?.zone_label)
      || readString(status?.current_zone)
      || readString(pose?.zone_label)
      || robotFallback.zoneLabel,
    metrics,
    progressPct: readNumber(status?.mission_progress_pct, robotFallback.progressPct),
    eta: readString(status?.eta) || readString(status?.estimated_completion) || robotFallback.eta,
    missionState: readString(status?.mission_state) || readString(status?.status) || robotFallback.missionState,
    battery: readString(status?.battery) || robotFallback.battery,
    speed: readString(status?.speed_mps) || readString(status?.speed) || robotFallback.speed,
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
      .slice(0, 2)
      .map((item, index): PlantAlertCard | null => {
        if (!isRecord(item)) {
          return null
        }

        const severity =
          readString(item.severity).includes('심각')
          || readString(item.level).includes('critical')
            ? '심각'
            : '주의'

        return {
          severity,
          title: readString(item.title) || `질병 감지 ${index + 1}`,
          location:
            readString(item.location)
            || readString(item.zone_name)
            || readString(item.zone_id)
            || '위치 정보 없음',
          action:
            readString(item.action)
            || readString(item.detail)
            || readString(item.message)
            || '추가 검수가 필요합니다.',
        }
      })
      .filter((item): item is PlantAlertCard => item !== null) || []

  const parsedPlants =
    plants
      .slice(0, 6)
      .map((item, index): PlantRow | null => {
        if (!isRecord(item)) {
          return null
        }

        const health = readNumber(item.health_score, 0) || readNumber(item.health, 0) || 70
        const tone: HealthTone =
          health < 35 ? 'critical' : health < 70 ? 'warning' : 'healthy'

        return {
          name: readString(item.name) || readString(item.crop_name) || `작물 ${index + 1}`,
          id: readString(item.id) || readString(item.plant_id) || `PLANT-${index + 1}`,
          health,
          tone,
          status:
            readString(item.status)
            || readString(item.stage)
            || readString(item.growth_stage)
            || '관측 중',
        }
      })
      .filter((item): item is PlantRow => item !== null) || []

  return {
    ...plantsFallback,
    source: live ? 'live' : 'fallback',
    criticalCount: parsedAlerts.length > 0 ? String(parsedAlerts.length).padStart(2, '0') : plantsFallback.criticalCount,
    alerts: parsedAlerts.length > 0 ? parsedAlerts : plantsFallback.alerts,
    plants: parsedPlants.length > 0 ? parsedPlants : plantsFallback.plants,
  }
}

export async function getEnvironmentPageData(): Promise<EnvironmentPageData> {
  const [envPayload, devicePayload, recommendationPayload] = await Promise.all([
    safeGet('/environment/latest'),
    safeGet('/iot/devices'),
    safeGet('/actuations/recommendations'),
  ])

  const live =
    hasStructuredData(envPayload)
    || hasStructuredData(devicePayload)
    || hasStructuredData(recommendationPayload)

  const env = readRecord(envPayload)
  const devices = asArray(devicePayload)
  const recommendations = asArray(recommendationPayload)
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
      .map((item): DeviceCard | null => {
        if (!isRecord(item)) {
          return null
        }

        const deviceType = readString(item.device_type)
        const name =
          readString(item.device_name)
          || readString(item.name)
          || readString(item.device_id)

        if (!name) {
          return null
        }

        if (deviceType.includes('water')) {
          return {
            icon: 'water_drop',
            name,
            detail: readString(item.state) || '장치 연결됨',
            accent: 'primary',
            action: 'toggle',
          }
        }

        if (deviceType.includes('curtain')) {
          return {
            icon: 'curtains',
            name,
            detail: readString(item.state) || '커튼 위치 제어',
            accent: 'secondary',
            action: 'slider',
            value: readString(item.opening_ratio) || readString(item.current_value),
          }
        }

        if (deviceType.includes('fan')) {
          return {
            icon: 'air',
            name,
            detail: readString(item.state) || '환기 제어',
            accent: 'neutral',
            action: 'fan',
          }
        }

        if (deviceType.includes('nutrient')) {
          return {
            icon: 'science',
            name,
            detail: readString(item.state) || '대기',
            accent: 'warning',
            action: 'button',
          }
        }

        return null
      })
      .filter((item): item is DeviceCard => item !== null) || []

  const recommendationRecord = recommendations[0]
  const recommendationText =
    isRecord(recommendationRecord)
      ? readString(recommendationRecord.title)
        || readString(recommendationRecord.message)
        || readString(recommendationRecord.description)
      : ''

  return {
    ...environmentFallback,
    source: live ? 'live' : 'fallback',
    recommendation: recommendationText || environmentFallback.recommendation,
    metrics,
    devices: parsedDevices.length > 0 ? parsedDevices.slice(0, 4) : environmentFallback.devices,
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
      .filter((item): item is HarvestBatch => item !== null) || []

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
