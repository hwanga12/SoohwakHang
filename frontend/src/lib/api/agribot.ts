import { isAxiosError } from 'axios'
import { markRouteFailed, markRouteVerified } from '@/app/dev-runtime'
import { env } from '@/config/env'
import { apiClient } from '@/lib/api/client'
import {
  farmSemanticScene,
  type SemanticAsset,
  type SemanticGuideLine,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'

export type CardTone = 'accent' | 'warning' | 'danger'
export type DataSource = 'live' | 'fallback'
export type HealthTone = 'healthy' | 'warning' | 'critical'
export type QuerySourceMap = Partial<Record<string, DataSource>>

type UnknownRecord = Record<string, unknown>

type PageDebugMeta = {
  querySources: QuerySourceMap
}

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
  debug: PageDebugMeta
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
  representativePose: RobotTargetPose
}

export type RobotTargetPose = {
  x: number
  y: number
  z: number
  yaw: number
  frameId: string
}

export type RobotMapData = {
  source: DataSource
  mapId: string
  imageUrl: string
  resolution: number
  origin: RobotTargetPose
  width: number
  height: number
  bounds: {
    minX: number
    maxX: number
    minY: number
    maxY: number
  }
}

export type RobotCommandStatus = {
  source: DataSource
  available: boolean
  commandId: string | null
  requestedCommandType: string
  commandType: string
  preemptCurrentNavigation: boolean
  targetPose: RobotTargetPose | null
  status: 'idle' | 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled'
  message: string
  error: string
  result: string
  updatedAt: string
  targetZoneId: string | null
  receivedAt: string
  startedAt: string
  completedAt: string
  controlState: RobotControlState | null
}

export type RobotCommandDispatch = {
  commandId: string
  message: string
  requestedCommandType: string
  commandType: string
  preemptCurrentNavigation: boolean
  targetPose: RobotTargetPose | null
  targetZoneId: string | null
}

export type DemoDiagnosisResult = {
  observationId: string
  finalLabel: string
  displayLabel: string
  finalConfidence: number
  imagePath: string
  imageUrl: string
  reviewedAt: string
  decisionSource: string
  detail: string
  healthPercent: number
  recommendedAction: string
  diagnosisNeeded: boolean
}

export type MissionDispatch = {
  missionId: string
  commandId: string
  requestType: string
  requestedType: string
  statusEndpoint: string
  message: string
  operatorMessage: string
  robotId: string
  requestedBy: string
  zoneIds: string[]
  loopCount: number | null
  patrolMode: string
  plantId: string | null
  fruitId: string | null
  tomatoId: string | null
}

export type MissionStatus = {
  source: DataSource
  available: boolean
  missionId: string | null
  commandId: string | null
  missionType: string
  requestType: string
  requestedType: string
  status: 'idle' | 'pending' | 'running' | 'succeeded' | 'failed' | 'canceled'
  state: string
  currentPhase: string
  progressPct: number | null
  retryCount: number | null
  message: string
  operatorMessage: string
  detailMessage: string
  error: string
  result: string
  updatedAt: string
  zoneIds: string[]
  loopCount: number | null
  patrolMode: string
  plantId: string | null
  fruitId: string | null
  tomatoId: string | null
  zoneId: string | null
  targetId: string | null
  receivedAt: string
  startedAt: string
  completedAt: string
}

export type RobotPoseSnapshot = {
  x: number
  y: number
  yawDeg: number
  linearSpeedMps: number
  updatedAt: string
}

export type RobotControlState = {
  mode: 'normal' | 'paused' | 'emergency_stop'
  activeActivity: 'idle' | 'manual_navigation' | 'patrol'
  blockingReason: string
  message: string
  resumeAvailable: boolean
  resumeContextType: '' | 'manual_navigation' | 'patrol'
  updatedAt: string
}

export type RobotPageData = {
  source: DataSource
  debug: PageDebugMeta
  waypoint: string
  zoneLabel: string
  poseLabel: string
  pose: RobotPoseSnapshot
  targetLabel: string
  metrics: MetricCardData[]
  progressPct: number
  eta: string
  missionState: string
  battery: string
  speed: string
  logs: string[]
  zonePresets: RobotZonePreset[]
  map: RobotMapData
  scene: SemanticScene
  robotPose: RobotTargetPose
  latestCommandStatus: RobotCommandStatus
}

export type PlantAlertCard = {
  id: string
  severity: '심각' | '주의'
  title: string
  location: string
  action: string
  detail: string
  diagnosisLabel: string
  detectedAt: string
  imageUrl: string
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
  latestLabel: string
  latestDisplayLabel: string
  latestImageUrl: string
}

export type PlantsPageData = {
  source: DataSource
  debug: PageDebugMeta
  healthSummary: string
  criticalCount: string
  activeScans: string
  growthIndex: string
  alerts: PlantAlertCard[]
  plants: PlantRow[]
}

export type PlantObservationEntry = {
  id: string
  label: string
  displayLabel: string
  reviewedAt: string
  imageUrl: string
  decisionSource: string
  healthPercent: number
  detail: string
}

export type PlantObservationFeed = {
  source: DataSource
  plantId: string
  plantName: string
  items: PlantObservationEntry[]
}

export type DeviceCard = {
  id: string
  icon: string
  name: string
  detail: string
  accent: 'primary' | 'secondary' | 'warning' | 'neutral'
  action: 'toggle' | 'button'
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
  debug: PageDebugMeta
  recommendation: string
  metrics: MetricCardData[]
  devices: DeviceCard[]
  recommendations: RecommendationItem[]
  history: ActuationHistoryItem[]
}

export type HarvestBatch = {
  route: string
  summary: string
  state: string
  missionId: string
  plantId: string | null
  fruitId: string | null
  currentPhase: string
  updatedAt: string
  basketCount: number | null
  success: boolean | null
}

export type HarvestPageData = {
  source: DataSource
  debug: PageDebugMeta
  basketState: string
  nextSwap: string
  basketCount: number
  remainingReadyCount: number
  lastHarvestedFruitId: string
  missionStatus: MissionStatus['status']
  currentPhase: string
  activeMissionId: string
  activeTargetId: string
  detailMessage: string
  loadedFruitIds: string[]
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
  debug: PageDebugMeta
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

function readOptionalNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string') {
    const parsed = Number(value.replace(/[^\d.-]/g, ''))
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }

  return null
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value
    .map((item) => readString(item))
    .filter(Boolean)
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

function toQuerySource(payload: unknown): DataSource {
  return hasStructuredData(payload) ? 'live' : 'fallback'
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

function toCardTone(value: HealthTone): CardTone {
  if (value === 'critical') {
    return 'danger'
  }

  if (value === 'warning') {
    return 'warning'
  }

  return 'accent'
}

function normalizeSearchText(...values: unknown[]) {
  return values
    .map((value) => readString(value).toLowerCase())
    .filter(Boolean)
    .join(' ')
}

function includesAnyKeyword(source: string, keywords: string[]) {
  return keywords.some((keyword) => source.includes(keyword))
}

const PLANT_DIAGNOSIS_KEYWORDS = [
  '진단 필요',
  'disease',
  'mildew',
  'powdery',
  'gray_mold',
  'gray mold',
  'blossom_end_rot',
  'blossom end rot',
  'rot',
  'blight',
  'wilt',
  'spot',
  'deficiency',
  '결핍',
  '병',
  '이상',
]

const PLANT_NON_DIAGNOSIS_KEYWORDS = [
  'healthy_leaf',
  'healthy',
  'normal',
  '정상 잎',
  '정상',
  'ripe_tomato',
  '수확 가능 토마토',
]

function extractPlantId(value: unknown) {
  const normalized = readString(value)
  if (!normalized) {
    return ''
  }

  const match = normalized.match(/farm\d+_plant_\d{2}/)
  return match?.[0] ?? ''
}

export function plantNeedsDiagnosis(plant?: {
  status?: string
  recommendedAction?: string
  latestLabel?: string
  latestDisplayLabel?: string
} | null) {
  if (!plant) {
    return false
  }

  const latestState = normalizeSearchText(
    plant.latestLabel,
    plant.latestDisplayLabel,
    plant.status,
  )

  if (latestState && includesAnyKeyword(latestState, PLANT_NON_DIAGNOSIS_KEYWORDS)) {
    return false
  }

  const normalized = normalizeSearchText(
    plant.latestLabel,
    plant.latestDisplayLabel,
    plant.status,
    plant.recommendedAction,
  )

  if (!normalized) {
    return false
  }

  return includesAnyKeyword(normalized, PLANT_DIAGNOSIS_KEYWORDS)
}

function displayLabelForDiagnosis(label: string) {
  const normalized = label.trim().toLowerCase()

  if (!normalized) {
    return '진단 결과'
  }

  if (normalized.includes('healthy')) {
    return '정상 잎'
  }

  if (normalized.includes('ripe')) {
    return '수확 가능 토마토'
  }

  if (normalized.includes('powder')) {
    return '토마토 흰가루병'
  }

  if (normalized.includes('gray_mold') || normalized.includes('gray mold')) {
    return '토마토 잿빛곰팡이병'
  }

  if (normalized.includes('blossom') || normalized.includes('rot')) {
    return '배꼽썩음병'
  }

  if (normalized.includes('blight')) {
    return '토마토 역병'
  }

  if (normalized.includes('wilt')) {
    return '토마토 시듦병'
  }

  if (normalized.includes('spot')) {
    return '토마토 반점병'
  }

  return label
}

function healthPercentForDiagnosis(label: string) {
  const normalized = label.trim().toLowerCase()

  if (!normalized) {
    return 55
  }

  if (normalized.includes('healthy')) {
    return 96
  }

  if (normalized.includes('ripe')) {
    return 92
  }

  if (normalized.includes('gray_mold') || normalized.includes('gray mold')) {
    return 34
  }

  if (normalized.includes('powder')) {
    return 38
  }

  if (normalized.includes('blossom') || normalized.includes('rot')) {
    return 41
  }

  if (normalized.includes('blight')) {
    return 35
  }

  if (normalized.includes('wilt') || normalized.includes('spot')) {
    return 44
  }

  return 52
}

function recommendedActionForDiagnosis(label: string, displayLabel: string) {
  const normalized = label.trim().toLowerCase()

  if (!normalized) {
    return '추가 관찰 유지'
  }

  if (normalized.includes('healthy')) {
    return '추가 관찰 유지'
  }

  if (normalized.includes('ripe')) {
    return '수확 요청 가능'
  }

  return `${displayLabel} 수동 검토`
}

function detailForDiagnosis(label: string, displayLabel: string, treatmentReason: string) {
  if (treatmentReason) {
    return treatmentReason
  }

  const normalized = label.trim().toLowerCase()

  if (normalized.includes('healthy')) {
    return '정상 생육 패턴이 확인되었습니다.'
  }

  if (normalized.includes('ripe')) {
    return '수확 가능한 성숙 상태가 확인되었습니다.'
  }

  return `${displayLabel} 징후가 확인되었습니다.`
}

function isFieldRelevantText(...values: unknown[]) {
  const normalized = normalizeSearchText(...values)

  if (!normalized) {
    return false
  }

  return !includesAnyKeyword(normalized, [
    'curtain',
    '차광',
    '커튼',
    'fan',
    'vent',
    '환기',
    'temperature',
    '온도',
    'humidity',
    '습도',
    'greenhouse',
    '온실',
  ])
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

function resolveApiMediaUrl(value: string) {
  if (!value) {
    return ''
  }

  if (/^(?:https?:)?\/\//i.test(value) || value.startsWith('data:')) {
    return value
  }

  if (value.startsWith('/mock-images/')) {
    return value
  }

  try {
    const apiBase = new URL(env.apiBaseUrl)
    return new URL(value, `${apiBase.origin}/`).toString()
  } catch {
    return value
  }
}

function normalizeHeadingDegrees(value: unknown, fallback = 0) {
  const raw = readNumber(value, Number.NaN)

  if (!Number.isFinite(raw)) {
    return fallback
  }

  const asDegrees = Math.abs(raw) <= Math.PI * 2 + 0.001 ? (raw * 180) / Math.PI : raw
  const normalized = ((asDegrees % 360) + 360) % 360
  return Number.isFinite(normalized) ? normalized : fallback
}

function readPoseSnapshot(payload: unknown, fallback: RobotPoseSnapshot): RobotPoseSnapshot {
  const record = readRecord(payload)
  const pose = readRecord(record?.pose)

  if (!pose) {
    return fallback
  }

  const x = readNumber(pose.x, Number.NaN)
  const y = readNumber(pose.y, Number.NaN)

  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return fallback
  }

  return {
    x,
    y,
    yawDeg: normalizeHeadingDegrees(pose.yaw, fallback.yawDeg),
    linearSpeedMps: readNumber(record?.linear_speed_mps, fallback.linearSpeedMps),
    updatedAt: readString(record?.updated_at) || fallback.updatedAt,
  }
}

function readSemanticGuide(payload: unknown): SemanticGuideLine | null {
  if (!isRecord(payload)) {
    return null
  }

  const axis = readString(payload.axis)
  if (axis !== 'x' && axis !== 'y') {
    return null
  }

  return {
    id: readString(payload.id) || `guide-${axis}-${readNumber(payload.value)}`,
    axis,
    value: readNumber(payload.value),
    label: readString(payload.label) || '가이드',
  }
}

function readSemanticAsset(payload: unknown): SemanticAsset | null {
  if (!isRecord(payload)) {
    return null
  }

  const kind = readString(payload.kind)
  if (kind !== 'plant' && kind !== 'sprinkler') {
    return null
  }

  const position = readRecord(payload.position)
  if (!position) {
    return null
  }

  const status = readString(payload.status)

  return {
    id: readString(payload.id) || `${kind}-${readNumber(position.x)}-${readNumber(position.y)}`,
    linkedId: readString(payload.linked_id),
    kind,
    label: readString(payload.label) || readString(payload.id) || '이름 없는 자산',
    shortLabel: readString(payload.short_label) || readString(payload.label, '자산'),
    zoneId: readString(payload.zone_id) || 'farm_01',
    description: readString(payload.description) || '운영 자산',
    position: {
      x: readNumber(position.x),
      y: readNumber(position.y),
    },
    navigationPose: payload.navigation_pose
      ? readRobotTargetPose(payload.navigation_pose, {
          x: readNumber(position.x),
          y: readNumber(position.y),
          z: 0,
          yaw: 0,
          frameId: 'map',
        })
      : undefined,
    approachPose: payload.approach_pose
      ? readRobotTargetPose(payload.approach_pose, {
          x: readNumber(position.x),
          y: readNumber(position.y),
          z: 0,
          yaw: 0,
          frameId: 'map',
        })
      : undefined,
    inspectWaypointId: readString(payload.inspect_waypoint_id),
    inspectWaypointName: readString(payload.inspect_waypoint_name),
    status:
      status === 'attention' || status === 'target' || status === 'handled'
        ? status
        : 'normal',
  }
}

function readRobotTargetPose(payload: unknown, fallback: RobotTargetPose): RobotTargetPose {
  if (!isRecord(payload)) {
    return fallback
  }

  return {
    x: readNumber(payload.x, fallback.x),
    y: readNumber(payload.y, fallback.y),
    z: readNumber(payload.z, fallback.z),
    yaw: readNumber(payload.yaw, fallback.yaw),
    frameId: readString(payload.frame_id) || readString(payload.frameId) || fallback.frameId,
  }
}

function readRobotMapData(payload: unknown): RobotMapData | null {
  const record = readRecord(payload)
  if (!record) {
    return null
  }

  const originRecord = readRecord(record.origin)

  return {
    source: toQuerySource(payload),
    mapId: readString(record.map_id) || 'farm_map',
    imageUrl: readString(record.image_url),
    resolution: readNumber(record.resolution, 0.05),
    origin: readRobotTargetPose(originRecord, {
      x: 0,
      y: 0,
      z: 0,
      yaw: 0,
      frameId: 'map',
    }),
    width: readNumber(record.width, 400),
    height: readNumber(record.height, 400),
    bounds: {
      minX: readNumber(readRecord(record.bounds)?.min_x, farmSemanticScene.bounds.minX),
      maxX: readNumber(readRecord(record.bounds)?.max_x, farmSemanticScene.bounds.maxX),
      minY: readNumber(readRecord(record.bounds)?.min_y, farmSemanticScene.bounds.minY),
      maxY: readNumber(readRecord(record.bounds)?.max_y, farmSemanticScene.bounds.maxY),
    },
  }
}

function readSemanticScene(payload: unknown): SemanticScene | null {
  const record = readRecord(payload)
  if (!record) {
    return null
  }

  const bounds = readRecord(record.bounds)
  const rowGuides = asArray(record.row_guides)
    .map((item) => readSemanticGuide(item))
    .filter((item): item is SemanticGuideLine => item !== null)
  const laneGuides = asArray(record.lane_guides)
    .map((item) => readSemanticGuide(item))
    .filter((item): item is SemanticGuideLine => item !== null)
  const assets = asArray(record.assets)
    .map((item) => readSemanticAsset(item))
    .filter((item): item is SemanticAsset => item !== null)

  if (assets.length === 0) {
    return null
  }

  return {
    bounds: {
      minX: readNumber(bounds?.min_x, farmSemanticScene.bounds.minX),
      maxX: readNumber(bounds?.max_x, farmSemanticScene.bounds.maxX),
      minY: readNumber(bounds?.min_y, farmSemanticScene.bounds.minY),
      maxY: readNumber(bounds?.max_y, farmSemanticScene.bounds.maxY),
    },
    rowGuides,
    laneGuides,
    assets,
  }
}

function readRobotControlState(payload: unknown): RobotControlState | null {
  const record = readRecord(payload)
  if (!record) {
    return null
  }

  const rawMode = readString(record.mode).toLowerCase()
  const rawActivity = readString(record.active_activity).toLowerCase()
  const resumeContext = readRecord(record.resume_context)
  const rawResumeContextType = readString(resumeContext?.context_type).toLowerCase()

  const mode =
    rawMode === 'paused' || rawMode === 'emergency_stop'
      ? rawMode
      : 'normal'
  const activeActivity =
    rawActivity === 'manual_navigation' || rawActivity === 'patrol'
      ? rawActivity
      : 'idle'
  const resumeContextType =
    rawResumeContextType === 'manual_navigation' || rawResumeContextType === 'patrol'
      ? rawResumeContextType
      : ''

  return {
    mode,
    activeActivity,
    blockingReason: readString(record.blocking_reason),
    message: readString(record.message),
    resumeAvailable: readBoolean(record.resume_available, false),
    resumeContextType,
    updatedAt: readString(record.updated_at),
  }
}

function readRobotCommandStatus(payload: unknown): RobotCommandStatus | null {
  const record = readRecord(payload)
  if (!record) {
    return null
  }

  const normalizedStatus = normalizeTaskStatus(record.status)

  return {
    source: toQuerySource(payload),
    available: readBoolean(record.available, true),
    commandId: readString(record.command_id) || null,
    requestedCommandType: readString(record.requested_command_type),
    commandType: readString(record.command_type),
    preemptCurrentNavigation: readBoolean(record.preempt_current_navigation, false),
    targetPose: record.target_pose
      ? readRobotTargetPose(record.target_pose, robotFallbackPose)
      : null,
    status: normalizedStatus,
    message: readString(record.message) || readString(record.note) || '명령 상태 정보가 준비되지 않았습니다.',
    error: readString(record.error),
    result: readString(record.result),
    updatedAt: readString(record.updated_at),
    targetZoneId: readString(record.target_zone_id) || null,
    receivedAt: readString(record.received_at),
    startedAt: readString(record.started_at),
    completedAt: readString(record.completed_at),
    controlState: readRobotControlState(record.control_state),
  }
}

function normalizeTaskStatus(value: unknown): RobotCommandStatus['status'] {
  const status = readString(value) as RobotCommandStatus['status']
  return (
    status === 'pending'
    || status === 'running'
    || status === 'succeeded'
    || status === 'failed'
    || status === 'canceled'
    || status === 'idle'
  )
    ? status
    : 'idle'
}

function readMissionStatus(payload: unknown): MissionStatus | null {
  const record = readRecord(payload)
  if (!record) {
    return null
  }

  return {
    source: toQuerySource(payload),
    available: readBoolean(record.available, true),
    missionId: readString(record.mission_id) || null,
    commandId: readString(record.command_id) || null,
    missionType: readString(record.mission_type),
    requestType: readString(record.request_type),
    requestedType: readString(record.requested_type) || readString(record.request_type),
    status: normalizeTaskStatus(record.status),
    state: readString(record.state),
    currentPhase: readString(record.current_phase),
    progressPct: readOptionalNumber(record.progress_pct),
    retryCount: readOptionalNumber(record.retry_count),
    message: readString(record.message) || '미션 상태 정보가 준비되지 않았습니다.',
    operatorMessage:
      readString(record.operator_message)
      || readString(record.message)
      || '미션 상태 정보가 준비되지 않았습니다.',
    detailMessage:
      readString(record.detail_message)
      || readString(record.message)
      || readString(record.operator_message),
    error: readString(record.error),
    result: readString(record.result),
    updatedAt: readString(record.updated_at),
    zoneIds: readStringArray(record.zone_ids),
    loopCount:
      typeof record.loop_count === 'number' && Number.isFinite(record.loop_count)
        ? record.loop_count
        : null,
    patrolMode: readString(record.patrol_mode),
    plantId: readString(record.plant_id) || null,
    fruitId: readString(record.fruit_id) || null,
    tomatoId: readString(record.tomato_id) || null,
    zoneId: readString(record.zone_id) || null,
    targetId: readString(record.target_id) || null,
    receivedAt: readString(record.received_at),
    startedAt: readString(record.started_at),
    completedAt: readString(record.completed_at),
  }
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
  let lastNon404Error: unknown = null

  for (const attempt of attempts) {
    try {
      const response = await apiClient.post(attempt.path, attempt.body)
      markRouteVerified('POST', attempt.path)
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
        markRouteFailed('POST', attempt.path)
        continue
      }

      markRouteFailed('POST', attempt.path)
      lastNon404Error = error
    }
  }

  if (lastNon404Error) {
    throw new Error(readApiErrorMessage(lastNon404Error, successFallback))
  }

  throw new Error('연결 가능한 API 엔드포인트를 찾지 못했습니다.')
}

function readApiErrorMessage(error: unknown, fallback: string) {
  if (!isAxiosError(error)) {
    return fallback
  }

  const payload = error.response?.data
  const record = readRecord(payload)
  const detail = record?.detail

  if (typeof detail === 'string' && detail.trim()) {
    return detail.trim()
  }

  if (isRecord(detail)) {
    return readString(detail.message) || readString(detail.error) || fallback
  }

  return readString(record?.message) || fallback
}

function parseCommandDispatch(payload: unknown, fallbackMessage: string): RobotCommandDispatch {
  const record = readRecord(payload)
  if (!record) {
    throw new Error(fallbackMessage)
  }

  return {
    commandId: readString(record.command_id),
    message:
      readString(record.message)
      || readString(record.status)
      || fallbackMessage,
    requestedCommandType: readString(record.requested_command_type),
    commandType: readString(record.command_type),
    preemptCurrentNavigation: readBoolean(record.preempt_current_navigation, false),
    targetPose: record.target_pose
      ? readRobotTargetPose(record.target_pose, robotFallbackPose)
      : null,
    targetZoneId:
      readString(readRecord(record.target_zone)?.id)
      || readString(record.target_zone_id)
      || null,
  }
}

function parseMissionDispatch(payload: unknown, fallbackMessage: string): MissionDispatch {
  const record = readRecord(payload)
  if (!record) {
    throw new Error(fallbackMessage)
  }

  const missionId = readString(record.mission_id) || readString(record.command_id)
  const requestType = readString(record.request_type) || readString(record.requested_type)
  const statusEndpoint = readString(record.status_endpoint)

  if (!missionId) {
    throw new Error('미션 접수 응답에 mission_id가 없어 상태 추적을 시작할 수 없습니다.')
  }
  if (!requestType) {
    throw new Error('미션 접수 응답에 request_type이 없어 상태 추적을 시작할 수 없습니다.')
  }
  if (!statusEndpoint) {
    throw new Error('미션 접수 응답에 status_endpoint가 없어 authoritative polling을 시작할 수 없습니다.')
  }

  return {
    missionId,
    commandId: readString(record.command_id) || missionId,
    requestType,
    requestedType: readString(record.requested_type) || requestType,
    statusEndpoint,
    message:
      readString(record.message)
      || readString(record.operator_message)
      || fallbackMessage,
    operatorMessage:
      readString(record.operator_message)
      || readString(record.message)
      || fallbackMessage,
    robotId: readString(record.robot_id),
    requestedBy: readString(record.requested_by),
    zoneIds: readStringArray(record.zone_ids),
    loopCount:
      typeof record.loop_count === 'number' && Number.isFinite(record.loop_count)
        ? record.loop_count
        : null,
    patrolMode: readString(record.patrol_mode),
    plantId: readString(record.plant_id) || null,
    fruitId: readString(record.fruit_id) || null,
    tomatoId: readString(record.tomato_id) || null,
  }
}

function buildUnavailableMissionStatus(
  missionId: string,
  message: string,
): MissionStatus {
  return {
    source: 'fallback',
    available: false,
    missionId,
    commandId: missionId,
    missionType: '',
    requestType: '',
    requestedType: '',
    status: 'idle',
    state: '',
    currentPhase: '',
    progressPct: null,
    retryCount: null,
    message,
    operatorMessage: message,
    detailMessage: message,
    error: '',
    result: '',
    updatedAt: '',
    zoneIds: [],
    loopCount: null,
    patrolMode: '',
    plantId: null,
    fruitId: null,
    tomatoId: null,
    zoneId: null,
    targetId: null,
    receivedAt: '',
    startedAt: '',
    completedAt: '',
  }
}

export const dashboardFallback: DashboardPageData = {
  source: 'fallback',
  debug: {
    querySources: {
      '/dashboard/summary': 'fallback',
      '/robot/status': 'fallback',
      '/environment/latest': 'fallback',
      '/alerts': 'fallback',
      '/harvests/stats': 'fallback',
      '/zones': 'fallback',
    },
  },
  heroStatus: 'farm_01 전체 순찰과 환경 점검이 함께 진행 중입니다.',
  location: 'Farm 01',
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
      id: 'farm_01',
      name: 'Farm 01',
      summary: '온실 전체를 하나의 운영 구역으로 사용합니다.',
      tone: 'healthy',
    },
  ],
}

const robotFallbackPose: RobotTargetPose = {
  x: 0,
  y: 0,
  z: 0,
  yaw: Math.PI / 2,
  frameId: 'map',
}

const robotFallbackMap: RobotMapData = {
  source: 'fallback',
  mapId: 'farm_map',
  imageUrl: '',
  resolution: 0.05,
  origin: {
    x: -10,
    y: -10,
    z: 0,
    yaw: 0,
    frameId: 'map',
  },
  width: 400,
  height: 400,
  bounds: {
    minX: farmSemanticScene.bounds.minX,
    maxX: farmSemanticScene.bounds.maxX,
    minY: farmSemanticScene.bounds.minY,
    maxY: farmSemanticScene.bounds.maxY,
  },
}

const robotFallbackCommandStatus: RobotCommandStatus = {
  source: 'fallback',
  available: false,
  commandId: null,
  requestedCommandType: '',
  commandType: '',
  preemptCurrentNavigation: false,
  targetPose: null,
  status: 'idle',
  message: '이동 명령 상태를 아직 받지 못했습니다.',
  error: '',
  result: '',
  updatedAt: '',
  targetZoneId: null,
  receivedAt: '',
  startedAt: '',
  completedAt: '',
  controlState: null,
}

export const robotFallback: RobotPageData = {
  source: 'fallback',
  debug: {
    querySources: {
      '/robot/status': 'fallback',
      '/robot/pose': 'fallback',
      '/robot/map': 'fallback',
      '/robot/map/layers': 'fallback',
      '/robot/commands/latest': 'fallback',
      '/zones': 'fallback',
    },
  },
  waypoint: 'inspection_b12',
  zoneLabel: 'Farm 01',
  poseLabel: 'map 기준 x 0.0 / y 0.0',
  pose: {
    x: 0.0,
    y: 0.0,
    yawDeg: 90,
    linearSpeedMps: 1.1,
    updatedAt: '',
  },
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
    {
      id: 'farm_01',
      name: 'Farm 01',
      detail: '온실 전체를 하나의 운영 구역으로 사용합니다.',
      representativePose: { x: 0, y: 0, z: 0, yaw: 0, frameId: 'map' },
    },
  ],
  map: robotFallbackMap,
  scene: farmSemanticScene,
  robotPose: robotFallbackPose,
  latestCommandStatus: robotFallbackCommandStatus,
}

export const plantsFallback: PlantsPageData = {
  source: 'fallback',
  debug: {
    querySources: {
      '/plants': 'fallback',
      '/alerts': 'fallback',
    },
  },
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
      detail: '상태가 좋지 않은 잎을 진단했고, 흰가루병 의심 결과가 저장되었습니다.',
      diagnosisLabel: '토마토 흰가루병',
      detectedAt: '09:42',
      imageUrl: '/mock-images/disease-closeup.png',
    },
    {
      id: 'alert-target-001',
      severity: '주의',
      title: '수확 후보 토마토 재확인',
      location: 'farm01_plant_03 · farm01_plant_03_tomato_01',
      action: 'canonical ID 기준으로 대상 큐에 유지',
      detail: '수확 후보를 다시 확인하는 발표용 샘플 카드입니다.',
      diagnosisLabel: '수확 후보 재확인',
      detectedAt: '09:38',
      imageUrl: '/mock-images/healthy-default.jpg',
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
      latestLabel: '',
      latestDisplayLabel: '',
      latestImageUrl: '/mock-images/healthy-default.jpg',
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
      latestLabel: 'tomato_powdery_mildew_disease',
      latestDisplayLabel: '토마토 흰가루병',
      latestImageUrl: '/mock-images/disease-closeup.png',
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
      latestLabel: 'tomato_gray_mold_disease',
      latestDisplayLabel: '토마토 잿빛곰팡이병',
      latestImageUrl: '/mock-images/disease-closeup.png',
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
      latestLabel: '',
      latestDisplayLabel: '',
      latestImageUrl: '/mock-images/healthy-default.jpg',
    },
  ],
}

export const emptyPlantObservationFeed: PlantObservationFeed = {
  source: 'fallback',
  plantId: '',
  plantName: '',
  items: [],
}

export const environmentFallback: EnvironmentPageData = {
  source: 'fallback',
  debug: {
    querySources: {
      '/environment/latest': 'fallback',
      '/iot/devices': 'fallback',
      '/actuations/recommendations': 'fallback',
      '/actuations/history': 'fallback',
    },
  },
  recommendation: '북쪽 밭 흙이 살짝 말라서 오후 햇살 전에 물을 한 번 더 주세요.',
  metrics: [
    { label: '토양 촉촉함', value: '18.5%', meta: '북쪽 밭이 조금 메말랐어요.', tone: 'danger' },
    { label: '오늘 물주기', value: '1건', meta: '오후 햇살 전에 먼저 챙기면 됩니다.', tone: 'warning' },
    { label: '손볼 메모', value: '2개', meta: '영양 보충과 최근 작업 기록만 남겨 두었습니다.', tone: 'accent' },
  ],
  devices: [
    {
      id: 'farm_01_watering',
      icon: 'water_drop',
      name: '물주기 펌프',
      detail: '자동 대기 · 오늘 1건만 승인하면 됩니다.',
      accent: 'primary',
      action: 'toggle',
    },
    {
      id: 'farm_01_nutrient',
      icon: 'science',
      name: '영양 보충기',
      detail: '가볍게 한 번만 보충하면 되는 상태예요.',
      accent: 'warning',
      action: 'button',
    },
  ],
  recommendations: [
    {
      id: 'reco-water-001',
      title: '북쪽 밭 물주기 메모',
      detail: '토양 수분이 기준선 아래로 내려가 350ml 정도만 가볍게 보충하면 됩니다.',
      priority: '높음',
      status: '승인 대기',
    },
    {
      id: 'reco-nutrient-001',
      title: '수확 전 영양 보충 살피기',
      detail: '오후 점검 때 칼슘 계열 보충을 한 번만 보면 충분합니다.',
      priority: '보통',
      status: '메모',
    },
  ],
  history: [
    {
      id: 'history-water-001',
      device: '물주기 펌프',
      action: '아침 물주기 350ml 실행',
      result: '정상 완료',
      time: '06:40',
      tone: 'healthy',
    },
    {
      id: 'history-nutrient-001',
      device: '영양 보충기',
      action: '칼슘 보충은 오후 점검 뒤로 미룸',
      result: '메모 남김',
      time: '07:10',
      tone: 'warning',
    },
  ],
}

export const harvestFallback: HarvestPageData = {
  source: 'fallback',
  debug: {
    querySources: {
      '/harvests/stats': 'fallback',
      '/harvests': 'fallback',
    },
  },
  basketState: '바구니 A · 68%',
  nextSwap: '35분 후 교체 예정',
  basketCount: 4,
  remainingReadyCount: 8,
  lastHarvestedFruitId: 'farm01_plant_03_tomato_01',
  missionStatus: 'running',
  currentPhase: 'STOWING',
  activeMissionId: 'mission-harvest-demo',
  activeTargetId: 'farm01_plant_03_tomato_01',
  detailMessage: '수확한 토마토를 등 바구니에 적재하는 중입니다.',
  loadedFruitIds: [
    'farm01_plant_01_tomato_01',
    'farm01_plant_02_tomato_01',
    'farm01_plant_03_tomato_01',
    'farm01_plant_04_tomato_01',
  ],
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
      missionId: 'mission-harvest-demo',
      plantId: 'farm01_plant_03',
      fruitId: 'farm01_plant_03_tomato_01',
      currentPhase: 'STOWING',
      updatedAt: '방금 전',
      basketCount: 4,
      success: null,
    },
    {
      route: '동측 3열 대기 배치',
      summary: '다음 바구니 교체 이후 바로 시작할 예정입니다.',
      state: '예정',
      missionId: 'mission-harvest-queue-01',
      plantId: 'farm01_plant_09',
      fruitId: 'farm01_plant_09_tomato_01',
      currentPhase: '',
      updatedAt: '10분 전',
      basketCount: null,
      success: null,
    },
    {
      route: '출하 바구니 라벨 교체',
      summary: '출하 큐와 적재 ID 정합성을 맞추기 위한 작업입니다.',
      state: '대기',
      missionId: 'mission-harvest-queue-02',
      plantId: null,
      fruitId: null,
      currentPhase: '',
      updatedAt: '20분 전',
      basketCount: null,
      success: null,
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
  debug: {
    querySources: {
      '/alerts': 'fallback',
    },
  },
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

  const querySources: QuerySourceMap = {
    '/dashboard/summary': toQuerySource(summaryPayload),
    '/robot/status': toQuerySource(robotPayload),
    '/environment/latest': toQuerySource(envPayload),
    '/alerts': toQuerySource(alertsPayload),
    '/harvests/stats': toQuerySource(harvestPayload),
    '/zones': toQuerySource(zonesPayload),
  }
  const live = Object.values(querySources).some((source) => source === 'live')

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
    debug: {
      querySources,
    },
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
  const [statusPayload, posePayload, zonesPayload, mapPayload, layersPayload, commandStatusPayload] =
    await Promise.all([
      safeGet('/robot/status'),
      safeGet('/robot/pose'),
      safeGet('/zones'),
      safeGet('/robot/map'),
      safeGet('/robot/map/layers'),
      safeGet('/robot/commands/latest'),
    ])

  const querySources: QuerySourceMap = {
    '/robot/status': toQuerySource(statusPayload),
    '/robot/pose': toQuerySource(posePayload),
    '/robot/map': toQuerySource(mapPayload),
    '/robot/map/layers': toQuerySource(layersPayload),
    '/robot/commands/latest': toQuerySource(commandStatusPayload),
    '/zones': toQuerySource(zonesPayload),
  }
  const live = Object.values(querySources).some((source) => source === 'live')
  const status = readRecord(statusPayload)
  const pose = readRecord(posePayload)
  const poseRecord = readRecord(pose?.pose)
  const poseSnapshot = readPoseSnapshot(posePayload, robotFallback.pose)
  const robotPose = readRobotTargetPose(poseRecord, robotFallbackPose)
  const mapData = readRobotMapData(mapPayload) ?? robotFallbackMap
  const scene = readSemanticScene(layersPayload) ?? robotFallback.scene
  const commandStatus = readRobotCommandStatus(commandStatusPayload) ?? robotFallback.latestCommandStatus
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
        const representativePose = readRobotTargetPose(
          readRecord(item.representative_pose),
          robotFallback.zonePresets[Math.min(index, robotFallback.zonePresets.length - 1)]
            ?.representativePose ?? robotFallbackPose,
        )
        return {
          id: readString(item.id) || `zone-${index + 1}`,
          name,
          detail:
            readString(item.description)
            || `${name} 대표 좌표 x ${representativePose.x.toFixed(1)} / y ${representativePose.y.toFixed(1)}`,
          representativePose,
        }
      })
      .filter((item): item is RobotZonePreset => item !== null)

  return {
    ...robotFallback,
    source: live ? 'live' : 'fallback',
    debug: {
      querySources,
    },
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
    poseLabel: buildPositionLabel(poseRecord ?? poseSnapshot, robotFallback.poseLabel),
    pose: poseSnapshot,
    targetLabel:
      readString(status?.next_target_crop_id)
      || readString(status?.target_crop_id)
      || readString(commandStatus.targetZoneId)
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
    speed:
      readString(status?.speed_mps)
      || readString(status?.speed)
      || `${poseSnapshot.linearSpeedMps.toFixed(1)}m/s`,
    zonePresets: zonePresets.length > 0 ? zonePresets : robotFallback.zonePresets,
    map: mapData,
    scene,
    robotPose,
    latestCommandStatus: commandStatus,
  }
}

export async function getPlantsPageData(): Promise<PlantsPageData> {
  const [plantsPayload, alertsPayload] = await Promise.all([
    safeGet('/plants'),
    safeGet('/alerts'),
  ])

  const querySources: QuerySourceMap = {
    '/plants': toQuerySource(plantsPayload),
    '/alerts': toQuerySource(alertsPayload),
  }
  const live = Object.values(querySources).some((source) => source === 'live')
  const alerts = asArray(alertsPayload)
  const plants = asArray(plantsPayload)
  const alertRecords = alerts.filter((item): item is UnknownRecord => isRecord(item))
  const alertSeverityByPlantId = new Map<string, string>()

  for (const item of alertRecords) {
    const plantId =
      extractPlantId(item.plant_id)
      || extractPlantId(item.target_crop_id)
      || extractPlantId(item.location)
      || extractPlantId(item.detail)

    if (!plantId) {
      continue
    }

    alertSeverityByPlantId.set(
      plantId,
      readString(item.severity)
      || readString(item.level)
      || readString(item.priority),
    )
  }

  const parsedAlerts =
    alertRecords
      .slice(0, 3)
      .map((item, index): PlantAlertCard | null => {
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
          detail:
            readString(item.detail)
            || readString(item.message)
            || '상태가 좋지 않은 잎을 진단한 결과가 도착하면 이 카드에 표시됩니다.',
          diagnosisLabel:
            readString(item.display_label)
            || readString(item.label)
            || readString(item.title)
            || '진단 결과 대기',
          detectedAt:
            readString(item.detected_at)
            || readString(item.created_at)
            || readString(item.time)
            || '',
          imageUrl: resolveApiMediaUrl(readString(item.image_url)),
        }
      })
      .filter((item): item is PlantAlertCard => item !== null)

  const parsedPlants =
    plants
      .map((item, index): PlantRow | null => {
        if (!isRecord(item)) {
          return null
        }

        const id = readString(item.id) || readString(item.plant_id) || `plant-${index + 1}`
        const latestLabel =
          readString(item.latest_label)
          || readString(item.label)
          || ''
        const latestDisplayLabel =
          readString(item.latest_display_label)
          || readString(item.display_label)
          || readString(item.status)
          || ''
        const baseStatus =
          readString(item.status)
          || readString(item.stage)
          || readString(item.growth_stage)
          || (readBoolean(item.ready_to_harvest) ? '수확 후보' : '관측 중')
        const baseRecommendedAction =
          readString(item.recommended_action)
          || readString(item.action)
          || latestDisplayLabel
          || latestLabel
          || plantsFallback.plants[Math.min(index, plantsFallback.plants.length - 1)]?.recommendedAction
          || '추가 관찰 유지'
        const diagnosisNeeded =
          alertSeverityByPlantId.has(id)
          || plantNeedsDiagnosis({
            status: baseStatus,
            recommendedAction: baseRecommendedAction,
            latestLabel,
            latestDisplayLabel,
          })
        const health = readNumber(item.health_score, 0) || readNumber(item.health, 0) || 70
        const baseTone: HealthTone =
          health < 35
            ? 'critical'
            : health < 75 || readBoolean(item.needs_water)
              ? 'warning'
              : 'healthy'
        const alertTone = normalizeToneFromSeverity(alertSeverityByPlantId.get(id) || 'warning')
        const tone: HealthTone =
          diagnosisNeeded
            ? baseTone === 'critical' || alertTone === 'critical'
              ? 'critical'
              : 'warning'
            : baseTone

        return {
          name: readString(item.name) || readString(item.crop_name) || `작물 ${index + 1}`,
          id,
          targetId:
            readString(item.target_fruit_id)
            || readString(item.fruit_id)
            || readString(item.tomato_id)
            || id
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
            diagnosisNeeded
              ? baseRecommendedAction
              : readBoolean(item.ready_to_harvest)
              ? '수확 요청 가능'
              : readBoolean(item.needs_water)
                ? '급수 우선 확인'
                : baseRecommendedAction,
          health,
          tone,
          status: diagnosisNeeded ? '조치 필요' : baseStatus,
          latestLabel,
          latestDisplayLabel,
          latestImageUrl: resolveApiMediaUrl(
            readString(item.latest_image_url)
            || readString(item.image_url)
            || '',
          ),
        }
      })
      .filter((item): item is PlantRow => item !== null)
  const diagnosisNeededCount = parsedPlants.filter((plant) => plantNeedsDiagnosis(plant)).length
  const averageHealth =
    parsedPlants.length > 0
      ? Math.round(parsedPlants.reduce((total, plant) => total + plant.health, 0) / parsedPlants.length)
      : null

  return {
    ...plantsFallback,
    source: live ? 'live' : 'fallback',
    debug: {
      querySources,
    },
    healthSummary: averageHealth !== null ? `${averageHealth}%` : plantsFallback.healthSummary,
    criticalCount:
      diagnosisNeededCount > 0
        ? String(diagnosisNeededCount).padStart(2, '0')
        : plantsFallback.criticalCount,
    alerts: parsedAlerts.length > 0 ? parsedAlerts : plantsFallback.alerts,
    plants: parsedPlants.length > 0 ? parsedPlants : plantsFallback.plants,
  }
}

export async function getPlantObservations(plantId: string): Promise<PlantObservationFeed> {
  if (!plantId) {
    return emptyPlantObservationFeed
  }

  const path = `/plants/${plantId}/observations`
  const payload = await safeGet(path)
  const record = readRecord(payload)
  const items = asArray(payload)

  const parsedItems =
    items
      .map((item, index): PlantObservationEntry | null => {
        if (!isRecord(item)) {
          return null
        }

        const treatmentPlan = readRecord(item.treatment_plan)
        const displayLabel =
          readString(item.display_label)
          || readString(item.label)
          || readString(item.class_name)
          || `진단 ${index + 1}`

        return {
          id: readString(item.id) || `observation-${index + 1}`,
          label: readString(item.class_name) || readString(item.label) || '',
          displayLabel,
          reviewedAt:
            readString(item.reviewed_at)
            || readString(item.detected_at)
            || readString(item.created_at)
            || '',
          imageUrl: resolveApiMediaUrl(readString(item.image_url)),
          decisionSource: readString(item.decision_source) || '',
          healthPercent: readNumber(item.health_percent, 0),
          detail:
            readString(treatmentPlan?.reason)
            || `${displayLabel} 결과가 저장되어 있습니다.`,
        }
      })
      .filter((item): item is PlantObservationEntry => item !== null)

  return {
    source: toQuerySource(payload),
    plantId: readString(record?.plant_id) || plantId,
    plantName: readString(record?.plant_name) || '',
    items: parsedItems,
  }
}

export async function getEnvironmentPageData(): Promise<EnvironmentPageData> {
  const [envPayload, devicePayload, recommendationPayload, historyPayload] = await Promise.all([
    safeGet('/environment/latest'),
    safeGet('/iot/devices'),
    safeGet('/actuations/recommendations'),
    safeGet('/actuations/history'),
  ])

  const querySources: QuerySourceMap = {
    '/environment/latest': toQuerySource(envPayload),
    '/iot/devices': toQuerySource(devicePayload),
    '/actuations/recommendations': toQuerySource(recommendationPayload),
    '/actuations/history': toQuerySource(historyPayload),
  }
  const live = Object.values(querySources).some((source) => source === 'live')

  const env = readRecord(envPayload)
  const devices = asArray(devicePayload)
  const recommendations = asArray(recommendationPayload)
  const history = asArray(historyPayload)

  const parsedDevices =
    devices
      .map((item, index): DeviceCard | null => {
        if (!isRecord(item)) {
          return null
        }

        const name =
          readString(item.display_name)
          || readString(item.device_name)
          || readString(item.name)
          || readString(item.device_id)
        const signature = normalizeSearchText(
          item.device_type,
          item.display_name,
          item.device_name,
          item.name,
          item.device_id,
        )

        if (!name || !signature || !isFieldRelevantText(signature)) {
          return null
        }

        if (includesAnyKeyword(signature, ['water', 'watering', 'irrigation', 'pump', 'drip', '급수', '관수'])) {
          return {
            id: readString(item.id) || `device-${index + 1}`,
            icon: 'water_drop',
            name,
            detail: readString(item.current_state) || readString(item.state) || '장치 연결됨',
            accent: 'primary',
            action: 'toggle',
          }
        }

        if (includesAnyKeyword(signature, ['nutrient', 'fert', 'fertilizer', '양액', '영양', '비료'])) {
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
      .filter((item): item is UnknownRecord => {
        if (!isRecord(item)) {
          return false
        }

        return isFieldRelevantText(
          item.title,
          item.detail,
          item.message,
          item.reason_text,
          item.device_name,
          item.device_type,
        )
      })
      .slice(0, 3)
      .map((item, index): RecommendationItem | null => {
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
      .filter((item): item is UnknownRecord => {
        if (!isRecord(item)) {
          return false
        }

        return isFieldRelevantText(
          item.device_name,
          item.device_id,
          item.command_type,
          item.action_type,
          item.result,
          item.status,
        )
      })
      .slice(0, 3)
      .map((item, index): ActuationHistoryItem | null => {
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

  const metrics = environmentFallback.metrics.map((item) => ({ ...item }))
  const soilValue =
    readString(env?.soil_moisture)
    || readString(env?.soil_moisture_percent)
    || metrics[0].value
  const soilPercent = readNumber(soilValue, Number.NaN)
  const latestFieldMemo = parsedHistory[0]

  metrics[0] = {
    ...metrics[0],
    value: soilValue,
    meta: readString(env?.soil_status) || metrics[0].meta,
    tone:
      Number.isFinite(soilPercent)
        ? soilPercent <= 20
          ? 'danger'
          : soilPercent <= 30
            ? 'warning'
            : 'accent'
        : metrics[0].tone,
  }
  metrics[1] = {
    ...metrics[1],
    value: `${parsedRecommendations.length > 0 ? parsedRecommendations.length : environmentFallback.recommendations.length}건`,
    meta: parsedRecommendations[0]?.title || metrics[1].meta,
    tone:
      parsedRecommendations.some((item) => item.priority.includes('높') || item.priority.includes('심각'))
        ? 'warning'
        : 'accent',
  }
  metrics[2] = {
    ...metrics[2],
    value: `${parsedHistory.length > 0 ? parsedHistory.length : environmentFallback.history.length}개`,
    meta:
      latestFieldMemo
        ? `${latestFieldMemo.device} · ${latestFieldMemo.action}`
        : metrics[2].meta,
    tone: latestFieldMemo ? toCardTone(latestFieldMemo.tone) : metrics[2].tone,
  }

  const recommendationRecord = parsedRecommendations[0]
  const recommendationText =
    recommendationRecord?.detail
    || recommendationRecord?.title
    || (isFieldRelevantText(env?.recommendation) ? readString(env?.recommendation) : '')

  return {
    ...environmentFallback,
    source: live ? 'live' : 'fallback',
    debug: {
      querySources,
    },
    recommendation:
      recommendationText
      || environmentFallback.recommendation,
    metrics,
    devices: parsedDevices.length > 0 ? parsedDevices.slice(0, 2) : environmentFallback.devices,
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

  const querySources: QuerySourceMap = {
    '/harvests/stats': toQuerySource(statsPayload),
    '/harvests': toQuerySource(harvestsPayload),
  }
  const live = Object.values(querySources).some((source) => source === 'live')
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
      .slice(0, 4)
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
          missionId:
            readString(item.mission_id)
            || readString(item.route_id)
            || readString(item.batch_id)
            || `harvest-mission-${index + 1}`,
          plantId: readString(item.plant_id) || null,
          fruitId: readString(item.fruit_id) || null,
          currentPhase: readString(item.current_phase),
          updatedAt:
            readString(item.updated_at)
            || readString(item.harvested_at)
            || readString(item.occurred_at)
            || '',
          basketCount: readOptionalNumber(item.basket_count),
          success:
            typeof item.success === 'boolean'
              ? item.success
              : readString(item.status) === 'succeeded'
                ? true
                : readString(item.status) === 'failed'
                  ? false
                  : null,
        }
      })
      .filter((item): item is HarvestBatch => item !== null)

  return {
    ...harvestFallback,
    source: live ? 'live' : 'fallback',
    debug: {
      querySources,
    },
    basketState:
      readString(stats?.basket_state)
      || readString(stats?.basket_fill_rate)
      || harvestFallback.basketState,
    nextSwap: readString(stats?.next_swap_eta) || harvestFallback.nextSwap,
    basketCount: readNumber(stats?.basket_count, harvestFallback.basketCount),
    remainingReadyCount: readNumber(stats?.remaining_ready_count, harvestFallback.remainingReadyCount),
    lastHarvestedFruitId:
      readString(stats?.last_harvested_fruit_id)
      || harvestFallback.lastHarvestedFruitId,
    missionStatus: normalizeTaskStatus(stats?.mission_status),
    currentPhase: readString(stats?.current_phase) || harvestFallback.currentPhase,
    activeMissionId: readString(stats?.active_mission_id) || harvestFallback.activeMissionId,
    activeTargetId: readString(stats?.active_target_id) || harvestFallback.activeTargetId,
    detailMessage: readString(stats?.detail_message) || harvestFallback.detailMessage,
    loadedFruitIds:
      readStringArray(stats?.loaded_fruit_ids).length > 0
        ? readStringArray(stats?.loaded_fruit_ids)
        : harvestFallback.loadedFruitIds,
    metrics,
    batches: batches.length > 0 ? batches : harvestFallback.batches,
  }
}

export async function getAlertsPageData(): Promise<AlertsPageData> {
  const alertsPayload = await safeGet('/alerts')
  const querySources: QuerySourceMap = {
    '/alerts': toQuerySource(alertsPayload),
  }
  const live = Object.values(querySources).some((source) => source === 'live')
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
    debug: {
      querySources,
    },
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
          path: '/robot/control/pause',
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
            command_type: 'pause_motion',
          },
        },
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
      '일시정지 명령을 접수했습니다. 실제 정지 상태를 확인하는 중입니다.',
    )
  }

  if (action === 'resume') {
    return postWithFallback(
      [
        {
          path: '/robot/control/resume',
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
            command_type: 'resume_motion',
          },
        },
        {
          path: '/robot/commands',
          body: {
            robot_id: robotId,
            requested_by: 'frontend-operator',
            command_type: 'resume_patrol',
          },
        },
      ],
      '재개 명령을 접수했습니다. 실제 재개 여부를 확인하는 중입니다.',
    )
  }

  if (action === 'home') {
    return postWithFallback(
      [
        {
          path: '/robot/commands',
          body: {
            robot_id: robotId,
            requested_by: 'frontend-operator',
            command_type: 'navigate_to_pose',
            target_pose: {
              x: 0,
              y: 0,
              z: 0,
              yaw: 0,
              frame_id: 'map',
            },
          },
        },
      ],
      '가운데 복귀 명령을 접수했습니다. 상태 카드에서 진행 상황을 확인하세요.',
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
    '비상 정지 명령을 접수했습니다. 실제 정지 상태를 확인하는 중입니다.',
  )
}

export async function pauseRobotMotion() {
  return postWithFallback(
    [
      {
        path: '/robot/control/pause',
        body: {
          robot_id: 'AGR-02',
          requested_by: 'frontend-operator',
        },
      },
      {
        path: '/robot/commands',
        body: {
          robot_id: 'AGR-02',
          requested_by: 'frontend-operator',
          command_type: 'pause_motion',
        },
      },
    ],
    '주행 중단 요청을 접수했습니다. 실제 정지 상태를 확인하는 중입니다.',
  )
}

export async function stopPatrolMission() {
  return postWithFallback(
    [
      {
        path: '/missions/patrol/stop',
        body: {
          robot_id: 'AGR-02',
          requested_by: 'frontend-operator',
          reason: 'ui_stop',
        },
      },
      {
        path: '/robot/commands',
        body: {
          robot_id: 'AGR-02',
          requested_by: 'frontend-operator',
          command_type: 'pause_patrol',
        },
      },
    ],
    '패트롤 중단 요청을 접수했습니다. 실제 정지 상태를 확인하는 중입니다.',
  )
}

export async function getLatestRobotCommandStatus(): Promise<RobotCommandStatus> {
  const payload = await safeGet('/robot/commands/latest')
  return readRobotCommandStatus(payload) ?? robotFallback.latestCommandStatus
}

export async function getMissionStatus(missionId: string): Promise<MissionStatus> {
  try {
    const response = await apiClient.get(`/missions/${missionId}`)
    const status = readMissionStatus(response.data)

    if (!status || !status.missionId) {
      throw new Error('미션 상태 응답에 mission_id가 없어 authoritative polling을 이어갈 수 없습니다.')
    }

    return status
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 404) {
      return buildUnavailableMissionStatus(
        missionId,
        'mission status 파일이 아직 생성되지 않았습니다. bridge 반영을 기다리는 중입니다.',
      )
    }

    throw new Error(readApiErrorMessage(error, '미션 상태를 조회하지 못했습니다.'))
  }
}

export async function sendRobotNavigateCommand(
  targetPose: RobotTargetPose,
  options?: {
    inspectWaypointId?: string | null
  },
) {
  try {
    const response = await apiClient.post('/robot/commands', {
      robot_id: 'AGR-02',
      requested_by: 'frontend-operator',
      command_type: 'navigate_to_pose',
      target_pose: {
        x: targetPose.x,
        y: targetPose.y,
        z: targetPose.z,
        yaw: targetPose.yaw,
        frame_id: targetPose.frameId,
      },
      payload: options?.inspectWaypointId
        ? {
            inspect_waypoint_id: options.inspectWaypointId,
          }
        : undefined,
    })
    markRouteVerified('POST', '/robot/commands')
    return parseCommandDispatch(response.data, '클릭한 좌표로 이동 요청을 보냈습니다.')
  } catch (error) {
    markRouteFailed('POST', '/robot/commands')
    throw new Error(readApiErrorMessage(error, '클릭 이동 요청을 처리하지 못했습니다.'))
  }
}

export async function runDemoDiagnosis({
  plantId,
  fruitId,
  targetPose,
}: {
  plantId: string
  fruitId: string
  targetPose: RobotTargetPose
}) {
  try {
    const response = await apiClient.post('/inference/demo/confirm', {
      plant_id: plantId,
      fruit_id: fruitId,
      robot_id: 'AGR-02',
      zone_id: 'farm_01',
      requested_by: 'frontend-demo',
      auto_execute_treatment: true,
      target_position: {
        x: targetPose.x,
        y: targetPose.y,
        z: targetPose.z,
      },
    })
    const payload = readRecord(response.data)
    if (!payload) {
      throw new Error('시연용 진단 응답이 비어 있습니다.')
    }

    markRouteVerified('POST', '/inference/demo/confirm')
    const treatmentPlan = readRecord(payload.treatment_plan)
    const observationId = readString(payload.observation_id)
    const finalLabel = readString(payload.final_label)
    const displayLabel = displayLabelForDiagnosis(finalLabel)
    const treatmentReason = readString(treatmentPlan?.reason)
    const recommendedAction = recommendedActionForDiagnosis(finalLabel, displayLabel)
    const diagnosisNeeded = plantNeedsDiagnosis({
      status: displayLabel,
      recommendedAction,
      latestLabel: finalLabel,
      latestDisplayLabel: displayLabel,
    })
    return {
      observationId,
      finalLabel,
      displayLabel,
      finalConfidence: readNumber(payload.final_confidence),
      imagePath: readString(payload.image_path),
      imageUrl: resolveApiMediaUrl(observationId ? `/api/v1/media/${observationId}` : ''),
      reviewedAt: readString(payload.reviewed_at),
      decisionSource: readString(payload.decision_source),
      detail: detailForDiagnosis(finalLabel, displayLabel, treatmentReason),
      healthPercent: healthPercentForDiagnosis(finalLabel),
      recommendedAction,
      diagnosisNeeded,
    } satisfies DemoDiagnosisResult
  } catch (error) {
    markRouteFailed('POST', '/inference/demo/confirm')
    throw new Error(readApiErrorMessage(error, '시연용 AI 진단을 처리하지 못했습니다.'))
  }
}

export async function sendRobotZoneMove(zoneId: string) {
  try {
    const response = await apiClient.post('/robot/commands', {
      robot_id: 'AGR-02',
      requested_by: 'frontend-operator',
      command_type: 'move_to_zone',
      target_zone_id: zoneId,
    })
    markRouteVerified('POST', '/robot/commands')
    return parseCommandDispatch(response.data, `${zoneId} 이동 요청을 보냈습니다.`)
  } catch (error) {
    markRouteFailed('POST', '/robot/commands')
    throw new Error(readApiErrorMessage(error, '구역 이동 요청을 처리하지 못했습니다.'))
  }
}

export async function requestHarvestMission({
  plantId,
  fruitId,
}: {
  plantId: string
  fruitId: string
}) {
  try {
    const response = await apiClient.post('/missions/harvest', {
      robot_id: 'AGR-02',
      plant_id: plantId,
      fruit_id: fruitId,
      requested_by: 'frontend-operator',
    })
    markRouteVerified('POST', '/missions/harvest')
    return parseMissionDispatch(response.data, `${fruitId} 수확 요청을 접수했습니다.`)
  } catch (error) {
    markRouteFailed('POST', '/missions/harvest')
    throw new Error(readApiErrorMessage(error, '수확 미션 요청을 처리하지 못했습니다.'))
  }
}

export async function startFieldPatrolMission({
  mode,
  zoneIds,
}: {
  mode: 'diagnosis' | 'harvest'
  zoneIds: string[]
}) {
  const fallbackZones = zoneIds.length > 0 ? zoneIds : ['farm_01']
  const successFallback =
    mode === 'diagnosis'
      ? '밭 전체 병 진단 패트롤 요청을 접수했습니다.'
      : '밭 전체 수확 패트롤 요청을 접수했습니다.'

  try {
    const response = await apiClient.post('/missions/patrol/start', {
      robot_id: 'AGR-02',
      zone_ids: fallbackZones,
      loop_count: 1,
      requested_by: 'frontend-operator',
      patrol_mode: mode,
    })
    markRouteVerified('POST', '/missions/patrol/start')
    return parseMissionDispatch(response.data, successFallback)
  } catch (error) {
    markRouteFailed('POST', '/missions/patrol/start')
    throw new Error(readApiErrorMessage(error, '패트롤 미션 요청을 처리하지 못했습니다.'))
  }
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

export async function triggerSprinklerWatering({
  deviceId,
  zoneId,
}: {
  deviceId: string
  zoneId: string
}) {
  return postWithFallback(
    [
      {
        path: '/actuations/watering',
        body: {
          zone_id: zoneId,
          device_id: deviceId,
          target_value: 3.0,
          value_unit: 'sec',
          requested_by: 'frontend-operator',
          request_source: 'farm_command_sprinkler_modal',
        },
      },
    ],
    `${deviceId} 스프링클러 물주기 요청을 보냈습니다.`,
  )
}

export async function triggerSprinklerNutrient({
  deviceId,
  zoneId,
}: {
  deviceId: string
  zoneId: string
}) {
  return postWithFallback(
    [
      {
        path: '/actuations/nutrients',
        body: {
          zone_id: zoneId,
          device_id: deviceId,
          target_value: 2.5,
          value_unit: 'sec',
          requested_by: 'frontend-operator',
          request_source: 'farm_command_sprinkler_modal',
          recommendation_id: 'manual-sprinkler-nutrient-001',
        },
      },
    ],
    `${deviceId} 스프링클러 영양제 주기 요청을 보냈습니다.`,
  )
}
