import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createGetSignal, createPostAction } from '@/app/dev-inspector'
import { AppIcon } from '@/components/app-icon'
import { DevSurface } from '@/components/dev-surface'
import { MockupImage } from '@/components/mockup-image'
import {
  RobotFacilityMap,
  summarizeSelectedAsset,
} from '@/components/robot-facility-map'
import {
  approveWateringRecommendation,
  dashboardFallback,
  emptyPlantObservationFeed,
  environmentFallback,
  getDashboardPageData,
  getEnvironmentPageData,
  getHarvestPageData,
  getLatestRobotCommandStatus,
  getPlantObservations,
  getMissionStatus,
  getPlantsPageData,
  getRobotPageData,
  harvestFallback,
  pauseRobotMotion,
  plantsFallback,
  requestHarvestMission,
  robotFallback,
  sendRobotControlAction,
  sendRobotNavigateCommand,
  sendRobotZoneMove,
  startFieldPatrolMission,
  stopPatrolMission,
  triggerNutrientInjection,
  type HarvestPageData,
  type MissionDispatch,
  type MissionStatus,
  type RobotCommandStatus,
  type RobotTargetPose,
} from '@/lib/api/agribot'
import {
  farmSemanticScene,
  parsePoseLabel,
  resolveSemanticTargetId,
  type SemanticAssetStatus,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'

const robotControlActions = [
  { id: 'pause', title: '일시정지', icon: 'pause_circle', nextState: '일시정지' },
  { id: 'resume', title: '재개', icon: 'play_circle', nextState: '재개중' },
  { id: 'home', title: '귀가', icon: 'route', nextState: '귀가중' },
] as const

type ActionRecordTone = 'accent' | 'danger' | 'healthy' | 'warning'

type AssetActionRecord = {
  label: string
  detail: string
  tone: ActionRecordTone
}

type PatrolActionRecord = {
  mode: 'diagnosis' | 'harvest'
  detail: string
}

type PlantModalDetail = {
  id: string
  targetId: string
  name: string
  zoneLabel: string
  positionLabel: string
  recommendedAction: string
  health: number
  status: string
  lastObserved: string
  latestLabel: string
  latestDisplayLabel: string
  latestImageUrl: string
}

type HarvestMissionInput = {
  plantId: string
  fruitId: string
  plantName: string
}

type PatrolMissionInput = {
  mode: 'diagnosis' | 'harvest'
  zoneIds: string[]
}

type PendingMissionRequest = {
  missionId: string
  requestedAt: number
  acceptedMessage: string
  mode?: 'diagnosis' | 'harvest'
  plantId?: string
  plantName?: string
}

type MissionFeedbackStatus = MissionStatus['status'] | 'accepted'

type MissionFeedback = {
  missionId: string | null
  status: MissionFeedbackStatus
  badgeLabel: string
  title: string
  detail: string
  tone: ActionRecordTone
  tagTone: 'table-tag--healthy' | 'table-tag--warning' | 'table-tag--danger'
  isTerminal: boolean
}

type MissionCopy = {
  acceptedTitle: string
  pendingTitle: string
  runningTitle: string
  successTitle: string
  failureTitle: string
  canceledTitle: string
}

type DiagnoseCommandTracker = {
  commandId: string
  plantId: string
  plantName: string
  baselineToken: string
  requestedAt: number
}

type DiagnoseUiState = {
  title: string
  detail: string
  badgeLabel: string
  badgeTone: 'table-tag--healthy' | 'table-tag--warning' | 'table-tag--danger'
  buttonLabel: string
  buttonMode: 'start' | 'stop'
  buttonDisabled: boolean
}

type PlantHarvestRuntime = {
  statusLabel: string
  phaseLabel: string
  detail: string
  basketLabel: string
  latestResultLabel: string
  isHandled: boolean
  isActive: boolean
}

function plantNeedsAttention(recommendedAction: string, status: string) {
  return recommendedAction.includes('병') || status.includes('재확인') || status.includes('병')
}

function normalizeHarvestPhase(phase?: string) {
  return (phase ?? '').trim().toUpperCase()
}

function formatHarvestPhase(phase?: string) {
  switch (normalizeHarvestPhase(phase)) {
    case 'APPROACHING':
      return '접근 중'
    case 'ALIGNING':
      return '자세 보정 중'
    case 'PICKING':
      return '토마토 집는 중'
    case 'STOWING':
      return '등 바구니에 적재 중'
    case 'RETURN_HOME':
      return '복귀 중'
    case 'RESUME':
      return '다음 작업 복귀 중'
    default:
      return phase?.trim() || '대기 중'
  }
}

function describeHarvestPhase(phase: string | undefined, plantName: string) {
  switch (normalizeHarvestPhase(phase)) {
    case 'APPROACHING':
      return `${plantName} 앞으로 이동해 수확 위치를 맞추는 중입니다.`
    case 'ALIGNING':
      return `${plantName} 앞에서 로봇팔 자세를 보정하고 있습니다.`
    case 'PICKING':
      return `${plantName}에서 토마토를 따는 중입니다.`
    case 'STOWING':
      return `${plantName}에서 딴 토마토를 등 바구니에 옮겨 담는 중입니다.`
    case 'RETURN_HOME':
      return '수확을 마치고 다음 이동 또는 복귀 경로를 준비하는 중입니다.'
    case 'RESUME':
      return '현재 수확 시퀀스를 마치고 다음 작업으로 복귀하는 중입니다.'
    default:
      return `${plantName} 수확 상태를 기다리는 중입니다.`
  }
}

function extractPlantIdFromFruitId(fruitId?: string | null) {
  const value = (fruitId ?? '').trim()
  if (!value) {
    return null
  }

  const match = value.match(/farm\d+_plant_\d{2}/)
  return match?.[0] ?? null
}

function buildPlantHarvestRuntime(
  plant: PlantModalDetail,
  harvest: HarvestPageData,
  missionStatus: MissionStatus | undefined,
  activeMission: PendingMissionRequest | null,
  missionFeedback: MissionFeedback | null,
): PlantHarvestRuntime {
  const relatedBatch =
    harvest.batches.find((batch) => (
      batch.plantId === plant.id
      || batch.fruitId === plant.targetId
      || extractPlantIdFromFruitId(batch.fruitId) === plant.id
    )) ?? null
  const activePlantId = extractPlantIdFromFruitId(harvest.activeTargetId)
  const latestHarvestedPlantId = extractPlantIdFromFruitId(harvest.lastHarvestedFruitId)
  const trackingThisMission =
    activeMission?.plantId === plant.id
    && missionStatus?.missionId === activeMission.missionId
  const isActive =
    trackingThisMission
    || (
      (harvest.missionStatus === 'pending' || harvest.missionStatus === 'running')
      && (harvest.activeTargetId === plant.targetId || activePlantId === plant.id)
    )
    || relatedBatch?.state.includes('진행') === true
  const isHandled =
    harvest.loadedFruitIds.includes(plant.targetId)
    || latestHarvestedPlantId === plant.id
    || relatedBatch?.success === true

  const phaseSource =
    trackingThisMission
      ? missionStatus?.currentPhase || harvest.currentPhase
      : isActive
        ? harvest.currentPhase || relatedBatch?.currentPhase
        : relatedBatch?.currentPhase || ''

  if (isHandled) {
    return {
      statusLabel: '수확 및 적재 완료',
      phaseLabel: '등 바구니 반영 완료',
      detail: `${harvest.lastHarvestedFruitId || plant.targetId}를 수확한 뒤 등 바구니에 적재했습니다.`,
      basketLabel: `현재 바구니 ${harvest.basketCount}개 적재`,
      latestResultLabel: harvest.lastHarvestedFruitId || plant.targetId,
      isHandled: true,
      isActive: false,
    }
  }

  if (trackingThisMission || isActive) {
    return {
      statusLabel: missionFeedback?.title || '수확 진행 중',
      phaseLabel: formatHarvestPhase(phaseSource),
      detail:
        missionStatus?.detailMessage
        || missionFeedback?.detail
        || harvest.detailMessage
        || describeHarvestPhase(phaseSource, plant.name),
      basketLabel: `현재 바구니 ${harvest.basketCount}개 적재`,
      latestResultLabel: harvest.lastHarvestedFruitId || '아직 수확 결과 없음',
      isHandled: false,
      isActive: true,
    }
  }

  if (relatedBatch?.success === false) {
    return {
      statusLabel: '최근 수확 실패',
      phaseLabel: '재시도 필요',
      detail: relatedBatch.summary || `${plant.name} 수확이 실패해 재확인이 필요합니다.`,
      basketLabel: `현재 바구니 ${harvest.basketCount}개 적재`,
      latestResultLabel: harvest.lastHarvestedFruitId || '실패 후 적재 없음',
      isHandled: false,
      isActive: false,
    }
  }

  return {
    statusLabel: plant.status.includes('수확') ? '수확 요청 가능' : '관찰 중',
    phaseLabel: plant.status.includes('수확') ? '수확 대기' : '관찰 우선',
    detail:
      plant.status.includes('수확')
        ? `${plant.name}은 수확 후보입니다. 버튼을 누르면 접근 → 집기 → 적재 순서로 진행합니다.`
        : `${plant.name}은 아직 수확보다 관찰이 우선인 상태입니다.`,
    basketLabel: `현재 바구니 ${harvest.basketCount}개 적재`,
    latestResultLabel: harvest.lastHarvestedFruitId || '아직 수확 결과 없음',
    isHandled: false,
    isActive: false,
  }
}

function previewImageForAsset(
  kind?: 'plant' | 'sprinkler',
  status?: 'normal' | 'target' | 'attention' | 'handled',
) {
  if (kind === 'sprinkler') {
    return '/mock-images/robot-camera-preview.png'
  }

  if (status === 'attention') {
    return '/mock-images/disease-closeup.png'
  }

  return '/mock-images/harvest-closeup.png'
}

function selectionTag(
  kind?: 'plant' | 'sprinkler',
  status?: 'normal' | 'target' | 'attention' | 'handled',
) {
  if (status === 'handled') {
    return {
      label: kind === 'plant' ? '수확 완료' : '조치 완료',
      tone: 'accent',
    } as const
  }

  if (status === 'attention') {
    return {
      label: '조치 필요',
      tone: 'danger',
    } as const
  }

  if (kind === 'sprinkler') {
    return {
      label: '급수 헤드',
      tone: 'healthy',
    } as const
  }

  return {
    label: '작물 확인',
    tone: 'warning',
  } as const
}

function missionTagTone(status: MissionFeedbackStatus): MissionFeedback['tagTone'] {
  if (status === 'running' || status === 'succeeded') {
    return 'table-tag--healthy'
  }
  if (status === 'failed') {
    return 'table-tag--danger'
  }
  return 'table-tag--warning'
}

function missionResultTone(status: MissionFeedbackStatus): ActionRecordTone {
  if (status === 'running' || status === 'succeeded') {
    return 'accent'
  }
  if (status === 'failed') {
    return 'danger'
  }
  return 'warning'
}

function isMissionTerminal(status: MissionStatus | null | undefined) {
  return status?.status === 'succeeded' || status?.status === 'failed' || status?.status === 'canceled'
}

function buildMissionFeedback(
  tracker: PendingMissionRequest | null,
  missionStatus: MissionStatus | undefined,
  missionError: Error | null,
  copy: MissionCopy,
): MissionFeedback | null {
  if (missionError) {
    return {
      missionId: tracker?.missionId ?? missionStatus?.missionId ?? null,
      status: 'failed',
      badgeLabel: 'failed',
      title: copy.failureTitle,
      detail: missionError.message,
      tone: 'danger',
      tagTone: 'table-tag--danger',
      isTerminal: true,
    }
  }

  if (!tracker) {
    return null
  }

  const pendingDelayMs = Date.now() - tracker.requestedAt
  const statusUnavailable =
    !missionStatus
    || !missionStatus.available
    || missionStatus.missionId !== tracker.missionId

  if (statusUnavailable || missionStatus.status === 'idle') {
    const detail =
      pendingDelayMs >= 4_000
        ? 'mission status polling 값이 아직 준비되지 않았습니다. 실제 상태가 확인될 때까지 성공으로 표시하지 않습니다.'
        : tracker.acceptedMessage

    return {
      missionId: tracker.missionId,
      status: 'accepted',
      badgeLabel: 'accepted',
      title: pendingDelayMs >= 4_000 ? '상태 반영 대기' : copy.acceptedTitle,
      detail,
      tone: 'warning',
      tagTone: 'table-tag--warning',
      isTerminal: false,
    }
  }

  const status = missionStatus.status
  const detail =
    missionStatus.detailMessage
    || missionStatus.message
    || missionStatus.operatorMessage
    || tracker.acceptedMessage

  if (status === 'pending') {
    return {
      missionId: tracker.missionId,
      status,
      badgeLabel: status,
      title:
        missionStatus.currentPhase
          ? `${copy.pendingTitle} · ${formatHarvestPhase(missionStatus.currentPhase)}`
          : copy.pendingTitle,
      detail,
      tone: missionResultTone(status),
      tagTone: missionTagTone(status),
      isTerminal: false,
    }
  }

  if (status === 'running') {
    return {
      missionId: tracker.missionId,
      status,
      badgeLabel: status,
      title:
        missionStatus.currentPhase
          ? `${copy.runningTitle} · ${formatHarvestPhase(missionStatus.currentPhase)}`
          : copy.runningTitle,
      detail,
      tone: missionResultTone(status),
      tagTone: missionTagTone(status),
      isTerminal: false,
    }
  }

  if (status === 'succeeded') {
    return {
      missionId: tracker.missionId,
      status,
      badgeLabel: status,
      title: copy.successTitle,
      detail,
      tone: missionResultTone(status),
      tagTone: missionTagTone(status),
      isTerminal: true,
    }
  }

  if (status === 'canceled') {
    return {
      missionId: tracker.missionId,
      status,
      badgeLabel: status,
      title: copy.canceledTitle,
      detail,
      tone: missionResultTone(status),
      tagTone: missionTagTone(status),
      isTerminal: true,
    }
  }

  return {
    missionId: tracker.missionId,
    status: 'failed',
    badgeLabel: 'failed',
    title: copy.failureTitle,
    detail: missionStatus.error ? `${detail} (${missionStatus.error})` : detail,
    tone: 'danger',
    tagTone: 'table-tag--danger',
    isTerminal: true,
  }
}

function latestCommandToken(status: RobotCommandStatus) {
  return `${status.commandId ?? 'none'}:${status.status}:${status.updatedAt}`
}

function sortedUniqueValues(values: number[]) {
  return [...new Set(values.map((value) => Number(value.toFixed(3))))].sort((left, right) => left - right)
}

function clampToSceneBounds(value: number, minValue: number, maxValue: number) {
  return Math.min(Math.max(value, minValue), maxValue)
}

function semanticRowGuideValues(scene: SemanticScene) {
  const rowGuideValues = sortedUniqueValues(
    scene.rowGuides
      .filter((guide) => guide.axis === 'x')
      .map((guide) => guide.value),
  )

  if (rowGuideValues.length > 0) {
    return rowGuideValues
  }

  return sortedUniqueValues(
    scene.assets
      .filter((asset) => asset.kind === 'plant')
      .map((asset) => asset.position.x),
  )
}

function buildInspectionPoseFromScene(
  position: { x: number, y: number },
  scene: SemanticScene,
): RobotTargetPose | null {
  const rowGuideValues = semanticRowGuideValues(scene)
  if (rowGuideValues.length < 2) {
    return null
  }

  const leftInspectionX = (rowGuideValues[0] + rowGuideValues[1]) / 2
  const rightInspectionX =
    (rowGuideValues[rowGuideValues.length - 2] + rowGuideValues[rowGuideValues.length - 1]) / 2
  const splitIndex = Math.floor(rowGuideValues.length / 2)
  const splitX =
    rowGuideValues.length >= 4
      ? (rowGuideValues[splitIndex - 1] + rowGuideValues[splitIndex]) / 2
      : (rowGuideValues[0] + rowGuideValues[rowGuideValues.length - 1]) / 2
  const targetX = position.x < splitX ? leftInspectionX : rightInspectionX
  const targetY = clampToSceneBounds(
    position.y,
    scene.bounds.minY + 0.5,
    scene.bounds.maxY - 0.5,
  )

  return {
    x: clampToSceneBounds(targetX, scene.bounds.minX + 0.5, scene.bounds.maxX - 0.5),
    y: targetY,
    z: 0,
    yaw: targetX < 0 ? -Math.PI / 2 : Math.PI / 2,
    frameId: 'map',
  }
}

function buildPlantTargetPose(
  plantId: string,
  preferredScene: SemanticScene,
  fallbackScene: SemanticScene,
  fallbackPositionLabel: string,
): RobotTargetPose | null {
  const preferredAsset = preferredScene.assets.find((asset) => asset.kind === 'plant' && asset.id === plantId)
  const fallbackAsset = fallbackScene.assets.find((asset) => asset.kind === 'plant' && asset.id === plantId)
  const targetAsset = preferredAsset ?? fallbackAsset

  if (targetAsset) {
    return (
      buildInspectionPoseFromScene(targetAsset.position, preferredScene)
      ?? buildInspectionPoseFromScene(targetAsset.position, fallbackScene)
    )
  }

  const parsedPose = parsePoseLabel(fallbackPositionLabel)
  if (!parsedPose) {
    return null
  }

  return (
    buildInspectionPoseFromScene(parsedPose, preferredScene)
    ?? buildInspectionPoseFromScene(parsedPose, fallbackScene)
  )
}

function buildDiagnoseBlockedMessage(status: RobotCommandStatus) {
  if (status.controlState?.mode === 'emergency_stop') {
    return '비상 정지 상태에서는 새 진단 이동 명령을 보낼 수 없습니다.'
  }

  if (status.controlState?.mode === 'paused') {
    return '일시정지 상태에서는 재개 전까지 새 진단 이동 명령을 보낼 수 없습니다.'
  }

  return null
}

function buildDiagnoseUiState(
  latestCommandStatus: RobotCommandStatus,
  activeDiagnoseCommand: DiagnoseCommandTracker | null,
  currentPlantId: string | null,
  targetPose: RobotTargetPose | null,
  mutationPending: boolean,
): DiagnoseUiState {
  if (mutationPending) {
    return {
      title: '진단 이동 요청 전송 중',
      detail: 'backend에 `navigate_to_pose` 요청을 보내는 중입니다.',
      badgeLabel: '전송 중',
      badgeTone: 'table-tag--warning',
      buttonLabel: '진단 요청 전송 중...',
      buttonMode: 'start',
      buttonDisabled: true,
    }
  }

  if (targetPose === null) {
    return {
      title: '좌표 정보 필요',
      detail: '선택한 식물의 진단 접근 좌표를 계산하지 못했습니다. live semantic layer를 다시 확인한 뒤 재시도하세요.',
      badgeLabel: '좌표 없음',
      badgeTone: 'table-tag--danger',
      buttonLabel: '진단하기',
      buttonMode: 'start',
      buttonDisabled: true,
    }
  }

  const blockedMessage = buildDiagnoseBlockedMessage(latestCommandStatus)
  const trackingCurrentPlant =
    activeDiagnoseCommand !== null && activeDiagnoseCommand.plantId === currentPlantId

  if (trackingCurrentPlant) {
    if (blockedMessage && latestCommandStatus.commandId !== activeDiagnoseCommand.commandId) {
      return {
        title: '새 진단 이동 차단됨',
        detail: blockedMessage,
        badgeLabel:
          latestCommandStatus.controlState?.mode === 'emergency_stop'
            ? '비상 정지'
            : '일시정지',
        badgeTone:
          latestCommandStatus.controlState?.mode === 'emergency_stop'
            ? 'table-tag--danger'
            : 'table-tag--warning',
        buttonLabel: '진단하기',
        buttonMode: 'start',
        buttonDisabled: true,
      }
    }

    const commandObserved = latestCommandStatus.commandId === activeDiagnoseCommand.commandId

    if (!commandObserved) {
      const pollingDelayed = Date.now() - activeDiagnoseCommand.requestedAt >= 4_000
      const commandStatusShifted =
        latestCommandToken(latestCommandStatus) !== activeDiagnoseCommand.baselineToken
      return {
        title: pollingDelayed ? 'backend 상태 반영 대기' : '진단 이동 명령 접수',
        detail: pollingDelayed
          ? '명령은 접수됐지만 `/robot/commands/latest` polling 결과가 아직 바뀌지 않았습니다. 실제 상태가 확인될 때까지 성공으로 표시하지 않습니다.'
          : commandStatusShifted
            ? '최신 상태 파일은 갱신됐지만 방금 보낸 `command_id`가 아직 authoritative 값으로 확인되지는 않았습니다.'
            : '명령은 접수됐고 executor가 최신 상태 파일에 반영하는 중입니다.',
        badgeLabel: pollingDelayed ? '반영 대기' : '접수됨',
        badgeTone: 'table-tag--warning',
        buttonLabel: '진단 중단',
        buttonMode: 'stop',
        buttonDisabled: false,
      }
    }

    switch (latestCommandStatus.status) {
      case 'pending':
        return {
          title: '진단 이동 준비 중',
          detail: latestCommandStatus.message || 'executor가 목표 좌표 이동을 준비 중입니다.',
          badgeLabel: 'pending',
          badgeTone: 'table-tag--warning',
          buttonLabel: '진단 중단',
          buttonMode: 'stop',
          buttonDisabled: false,
        }
      case 'running':
        return {
          title: '진단 위치로 이동 중',
          detail: latestCommandStatus.message || '로봇이 선택한 식물의 진단 위치로 이동 중입니다.',
          badgeLabel: 'running',
          badgeTone: 'table-tag--warning',
          buttonLabel: '진단 중단',
          buttonMode: 'stop',
          buttonDisabled: false,
        }
      case 'succeeded':
        return {
          title: '진단 위치 도착 완료',
          detail: latestCommandStatus.message || '선택한 식물 진단 위치까지 이동을 완료했습니다.',
          badgeLabel: 'succeeded',
          badgeTone: 'table-tag--healthy',
          buttonLabel: '다시 진단하기',
          buttonMode: 'start',
          buttonDisabled: blockedMessage !== null,
        }
      case 'failed':
        return {
          title: '진단 이동 실패',
          detail: latestCommandStatus.message || 'backend 또는 executor가 진단 이동 실패를 기록했습니다.',
          badgeLabel: 'failed',
          badgeTone: 'table-tag--danger',
          buttonLabel: '다시 진단하기',
          buttonMode: 'start',
          buttonDisabled: blockedMessage !== null,
        }
      case 'canceled':
        return {
          title: '진단 이동 취소됨',
          detail: latestCommandStatus.message || '진단 이동 명령이 취소되었거나 중단되었습니다.',
          badgeLabel: 'canceled',
          badgeTone: 'table-tag--warning',
          buttonLabel: '다시 진단하기',
          buttonMode: 'start',
          buttonDisabled: blockedMessage !== null,
        }
      default:
        break
    }
  }

  if (blockedMessage) {
    return {
      title: '새 진단 이동 차단됨',
      detail: blockedMessage,
      badgeLabel:
        latestCommandStatus.controlState?.mode === 'emergency_stop'
          ? '비상 정지'
          : '일시정지',
      badgeTone:
        latestCommandStatus.controlState?.mode === 'emergency_stop'
          ? 'table-tag--danger'
          : 'table-tag--warning',
      buttonLabel: '진단하기',
      buttonMode: 'start',
      buttonDisabled: true,
    }
  }

  return {
    title: '진단 이동 준비',
    detail: '버튼을 누르면 선택한 식물의 inspection 통로 좌표로 `navigate_to_pose`를 보내고 `/robot/commands/latest` 상태를 추적합니다.',
    badgeLabel: '대기',
    badgeTone: 'table-tag--healthy',
    buttonLabel: '진단하기',
    buttonMode: 'start',
    buttonDisabled: false,
  }
}

export function FarmCommandPage() {
  const queryClient = useQueryClient()
  const [activeStopRequest, setActiveStopRequest] = useState<
    'diagnosis' | 'harvest' | 'patrol-diagnosis' | 'patrol-harvest' | null
  >(null)
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [selectedPlantId, setSelectedPlantId] = useState<string | null>(null)
  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false)
  const [activityState, setActivityState] = useState<string | null>(null)
  const [uiMessage, setUiMessage] = useState<string | null>(null)
  const [actionRecords, setActionRecords] = useState<Record<string, AssetActionRecord>>({})
  const [lastPatrolAction, setLastPatrolAction] = useState<PatrolActionRecord | null>(null)
  const [activeHarvestMission, setActiveHarvestMission] = useState<PendingMissionRequest | null>(null)
  const [activePatrolMission, setActivePatrolMission] = useState<PendingMissionRequest | null>(null)
  const [lastHandledHarvestMissionKey, setLastHandledHarvestMissionKey] = useState<string | null>(null)
  const [lastHandledPatrolMissionKey, setLastHandledPatrolMissionKey] = useState<string | null>(null)
  const [activeDiagnoseCommand, setActiveDiagnoseCommand] = useState<DiagnoseCommandTracker | null>(null)
  const [observedDiagnoseState, setObservedDiagnoseState] = useState<string | null>(null)

  const dashboardQuery = useQuery({
    queryKey: ['page', 'dashboard'],
    queryFn: getDashboardPageData,
    initialData: dashboardFallback,
    refetchInterval: 20_000,
  })
  const robotQuery = useQuery({
    queryKey: ['page', 'robot'],
    queryFn: getRobotPageData,
    initialData: robotFallback,
    refetchInterval: 1_000,
  })
  const latestCommandStatusQuery = useQuery({
    queryKey: ['robot', 'command-status'],
    queryFn: getLatestRobotCommandStatus,
    initialData: robotFallback.latestCommandStatus,
    refetchInterval: 2_000,
  })
  const plantsQuery = useQuery({
    queryKey: ['page', 'plants'],
    queryFn: getPlantsPageData,
    initialData: plantsFallback,
    refetchInterval: 20_000,
  })
  const environmentQuery = useQuery({
    queryKey: ['page', 'environment'],
    queryFn: getEnvironmentPageData,
    initialData: environmentFallback,
    refetchInterval: 15_000,
  })
  const harvestQuery = useQuery({
    queryKey: ['page', 'harvest'],
    queryFn: getHarvestPageData,
    initialData: harvestFallback,
    refetchInterval: 20_000,
  })
  const harvestMissionStatusQuery = useQuery({
    queryKey: ['missions', 'status', activeHarvestMission?.missionId],
    queryFn: async () => {
      if (!activeHarvestMission) {
        throw new Error('수확 미션 ID가 없습니다.')
      }
      return getMissionStatus(activeHarvestMission.missionId)
    },
    enabled: activeHarvestMission !== null,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data as MissionStatus | undefined
      return activeHarvestMission !== null && !isMissionTerminal(status) ? 2_000 : false
    },
  })
  const patrolMissionStatusQuery = useQuery({
    queryKey: ['missions', 'status', activePatrolMission?.missionId],
    queryFn: async () => {
      if (!activePatrolMission) {
        throw new Error('패트롤 미션 ID가 없습니다.')
      }
      return getMissionStatus(activePatrolMission.missionId)
    },
    enabled: activePatrolMission !== null,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data as MissionStatus | undefined
      return activePatrolMission !== null && !isMissionTerminal(status) ? 2_000 : false
    },
  })

  const zoneMoveMutation = useMutation({
    mutationFn: sendRobotZoneMove,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
    },
  })
  const controlMutation = useMutation({
    mutationFn: sendRobotControlAction,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })
  const stopMotionMutation = useMutation({
    mutationFn: pauseRobotMotion,
    onSuccess: async () => {
      const refreshJobs = [
        queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['robot', 'command-status'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'harvest'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'plants'] }),
      ]

      if (activeHarvestMission?.missionId) {
        refreshJobs.push(queryClient.invalidateQueries({ queryKey: ['missions', 'status', activeHarvestMission.missionId] }))
      }

      await Promise.all(refreshJobs)
    },
  })
  const stopPatrolMutation = useMutation({
    mutationFn: stopPatrolMission,
    onSuccess: async () => {
      const refreshJobs = [
        queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'harvest'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'plants'] }),
      ]

      if (activePatrolMission?.missionId) {
        refreshJobs.push(queryClient.invalidateQueries({ queryKey: ['missions', 'status', activePatrolMission.missionId] }))
      }

      await Promise.all(refreshJobs)
    },
  })
  const diagnoseMutation = useMutation({
    mutationFn: sendRobotNavigateCommand,
    onSuccess: async (response, targetPose) => {
      const targetPlant =
        selectedAsset?.kind === 'plant' && selectedPlantDetail
          ? selectedPlantDetail
          : attentionPlant

      if (targetPlant) {
        setActiveDiagnoseCommand({
          commandId: response.commandId,
          plantId: targetPlant.id,
          plantName: targetPlant.name,
          baselineToken: latestCommandToken(latestCommandStatus),
          requestedAt: Date.now(),
        })
        setObservedDiagnoseState(null)
        setActivityState('진단 이동 준비중')
        setSelectedPlantId(targetPlant.id)
        setSelectedAssetId(targetPlant.id)
        setUiMessage(
          `${targetPlant.name} 진단 이동 요청을 접수했습니다. /robot/commands/latest 가 pending/running으로 바뀌는지 확인합니다.`,
        )
      } else {
        setUiMessage(
          `선택 좌표 x ${targetPose.x.toFixed(1)} / y ${targetPose.y.toFixed(1)} 진단 이동 요청을 접수했습니다.`,
        )
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
        queryClient.invalidateQueries({ queryKey: ['robot', 'command-status'] }),
      ])
    },
    onError: (error: Error) => {
      setUiMessage(error.message)
    },
  })
  const harvestMutation = useMutation({
    mutationFn: ({ plantId, fruitId }: HarvestMissionInput) => requestHarvestMission({ plantId, fruitId }),
    onSuccess: async (dispatch: MissionDispatch, variables) => {
      setActiveHarvestMission({
        missionId: dispatch.missionId,
        requestedAt: Date.now(),
        acceptedMessage: dispatch.operatorMessage,
        plantId: variables.plantId,
        plantName: variables.plantName,
      })
      setActivityState('수확 준비중')
      setUiMessage(
        `${variables.plantName} 수확 요청을 접수했습니다. 접근 → 집기 → 적재 단계가 실제 상태로 반영될 때까지 추적합니다.`,
      )
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['page', 'plants'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'harvest'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['missions', 'status', dispatch.missionId] }),
      ])
    },
  })
  const patrolMutation = useMutation({
    mutationFn: ({ mode, zoneIds }: PatrolMissionInput) => startFieldPatrolMission({ mode, zoneIds }),
    onSuccess: async (dispatch: MissionDispatch, variables) => {
      setActivePatrolMission({
        missionId: dispatch.missionId,
        requestedAt: Date.now(),
        acceptedMessage: dispatch.operatorMessage,
        mode: variables.mode,
      })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['missions', 'status', dispatch.missionId] }),
      ])
    },
  })
  const wateringMutation = useMutation({
    mutationFn: approveWateringRecommendation,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'environment'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })
  const nutrientMutation = useMutation({
    mutationFn: triggerNutrientInjection,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'environment'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })

  const dashboard = dashboardQuery.data
  const robot = robotQuery.data
  const latestCommandStatus = latestCommandStatusQuery.data ?? robot.latestCommandStatus
  const plants = plantsQuery.data
  const environment = environmentQuery.data
  const harvest = harvestQuery.data
  const harvestMissionStatus = harvestMissionStatusQuery.data
  const patrolMissionStatus = patrolMissionStatusQuery.data

  const mapSource = (path: string) => robot.debug.querySources[path] ?? 'fallback'
  const dashboardSource = (path: string) => dashboard.debug.querySources[path] ?? 'fallback'
  const plantsSource = (path: string) => plants.debug.querySources[path] ?? 'fallback'
  const fieldSource = (path: string) => environment.debug.querySources[path] ?? 'fallback'
  const harvestSource = (path: string) => harvest.debug.querySources[path] ?? 'fallback'

  const rememberAction = (
    assetId: string,
    label: string,
    detail: string,
    tone: ActionRecordTone = 'accent',
  ) => {
    setActionRecords((current) => ({
      ...current,
      [assetId]: {
        label,
        detail,
        tone,
      },
    }))
  }

  const robotPose = robot.pose
  const targetAssetId = resolveSemanticTargetId(robot.targetLabel)
  const plantLookup = useMemo(
    () => new Map(plants.plants.map((plant) => [plant.id, plant])),
    [plants.plants],
  )
  const runtimeActiveHarvestPlantId = useMemo(
    () => extractPlantIdFromFruitId(harvest.activeTargetId) ?? activeHarvestMission?.plantId ?? null,
    [activeHarvestMission?.plantId, harvest.activeTargetId],
  )
  const runtimeHandledFruitIds = useMemo(
    () => new Set(harvest.loadedFruitIds),
    [harvest.loadedFruitIds],
  )
  const attentionPlant =
    plants.plants.find((plant) => plantNeedsAttention(plant.recommendedAction, plant.status))
    ?? plants.plants[0]
  const activeHarvestPlant =
    plants.plants.find((plant) => (
      plant.id === runtimeActiveHarvestPlantId
      || plant.targetId === harvest.activeTargetId
    ))
    ?? null
  const harvestPlant =
    activeHarvestPlant
    ?? plants.plants.find((plant) => plant.status.includes('수확'))
    ?? plants.plants[0]
  const patrolZoneIds = robot.zonePresets.map((preset) => preset.id).filter(Boolean)
  const liveScene = useMemo<SemanticScene>(() => ({
    bounds: robot.scene.bounds,
    rowGuides: robot.scene.rowGuides.length > 0 ? robot.scene.rowGuides : farmSemanticScene.rowGuides,
    laneGuides: robot.scene.laneGuides.length > 0 ? robot.scene.laneGuides : farmSemanticScene.laneGuides,
    assets: robot.scene.assets.length > 0 ? robot.scene.assets : farmSemanticScene.assets,
  }), [robot.scene.assets, robot.scene.bounds, robot.scene.laneGuides, robot.scene.rowGuides])

  const mapScene = useMemo<SemanticScene>(() => ({
    ...liveScene,
    assets: liveScene.assets.map((asset) => {
      const actionRecord = actionRecords[asset.id]

      if (asset.kind === 'plant') {
        const plant = plantLookup.get(asset.id)
        const attention = plant ? plantNeedsAttention(plant.recommendedAction, plant.status) : asset.status === 'attention'
        const harvestTarget = plant ? plant.status.includes('수확') : asset.status === 'target'
        const runtimeHandled =
          plant !== undefined
          && (
            runtimeHandledFruitIds.has(plant.targetId)
            || extractPlantIdFromFruitId(harvest.lastHarvestedFruitId) === plant.id
          )
        const runtimeHarvestTarget =
          plant !== undefined
          && (
            plant.id === runtimeActiveHarvestPlantId
            || plant.targetId === harvest.activeTargetId
          )
        const status: SemanticAssetStatus =
          actionRecord || runtimeHandled
            ? 'handled'
            : attention
              ? 'attention'
              : runtimeHarvestTarget || harvestTarget
                ? 'target'
                : 'normal'

        return {
          ...asset,
          linkedId: plant?.targetId ?? asset.linkedId,
          label: plant?.name ?? asset.label,
          shortLabel: plant?.name.replace('토마토 ', '') ?? asset.shortLabel,
          description:
            actionRecord
              ? actionRecord.detail
              : runtimeHandled
                ? `${plant?.name ?? asset.label} 수확과 등 바구니 적재가 완료되었습니다.`
                : runtimeHarvestTarget
                  ? harvest.detailMessage || `${plant?.name ?? asset.label} ${formatHarvestPhase(harvest.currentPhase)}`
                  : plant
                    ? `${plant.status} · ${plant.recommendedAction}`
                    : asset.description,
          status,
        }
      }

      const sprinklerIndex = Number(asset.id.replace('sprinkler_', ''))
      const status: SemanticAssetStatus = actionRecord ? 'handled' : 'normal'

      return {
        ...asset,
        label: `${sprinklerIndex}번 급수 헤드`,
        shortLabel: `H${sprinklerIndex}`,
        description: actionRecord
          ? actionRecord.detail
          : '고장 없이 정상 작동하는 급수 포인트입니다.',
        status,
      }
    }),
  }), [
    actionRecords,
    harvest.activeTargetId,
    harvest.currentPhase,
    harvest.detailMessage,
    harvest.lastHarvestedFruitId,
    liveScene,
    plantLookup,
    runtimeActiveHarvestPlantId,
    runtimeHandledFruitIds,
  ])

  const selectedAsset = useMemo(
    () => mapScene.assets.find((asset) => asset.id === selectedAssetId) ?? null,
    [mapScene.assets, selectedAssetId],
  )
  const selectedSummary = summarizeSelectedAsset(selectedAsset)
  const selectedActionRecord = selectedAssetId ? actionRecords[selectedAssetId] ?? null : null
  const selectedPlantAsset = selectedAsset?.kind === 'plant' ? selectedAsset : null
  const selectedSprinklerAsset = selectedAsset?.kind === 'sprinkler' ? selectedAsset : null
  const selectedPlantDetail = useMemo<PlantModalDetail | null>(() => {
    const asset =
      selectedAsset?.kind === 'plant'
        ? selectedAsset
        : selectedPlantId
          ? mapScene.assets.find((item) => item.id === selectedPlantId && item.kind === 'plant') ?? null
          : null

    if (!asset || asset.kind !== 'plant') {
      if (!harvestPlant) {
        return null
      }

      return {
        id: harvestPlant.id,
        targetId: harvestPlant.targetId,
        name: harvestPlant.name,
        zoneLabel: harvestPlant.zoneLabel,
        positionLabel: harvestPlant.positionLabel,
        recommendedAction: harvestPlant.recommendedAction,
        health: harvestPlant.health,
        status: harvestPlant.status,
        lastObserved: harvestPlant.lastObserved,
        latestLabel: harvestPlant.latestLabel,
        latestDisplayLabel: harvestPlant.latestDisplayLabel,
        latestImageUrl: harvestPlant.latestImageUrl,
      }
    }

    const plant = plantLookup.get(asset.id)

    if (plant) {
      return {
        id: plant.id,
        targetId: plant.targetId,
        name: plant.name,
        zoneLabel: plant.zoneLabel,
        positionLabel: plant.positionLabel,
        recommendedAction: plant.recommendedAction,
        health: plant.health,
        status: plant.status,
        lastObserved: plant.lastObserved,
        latestLabel: plant.latestLabel,
        latestDisplayLabel: plant.latestDisplayLabel,
        latestImageUrl: plant.latestImageUrl,
      }
    }

    return {
      id: asset.id,
      targetId: asset.linkedId ?? `${asset.id}_fruit_01`,
      name: asset.label,
      zoneLabel: `zone ${asset.zoneId}`,
      positionLabel: `x ${asset.position.x.toFixed(1)} / y ${asset.position.y.toFixed(1)}`,
      recommendedAction: asset.status === 'target' ? '수확 요청 가능' : '개별 진단 권장',
      health: asset.status === 'attention' ? 62 : asset.status === 'target' ? 91 : 84,
      status: asset.status === 'attention' ? '재확인 필요' : asset.status === 'target' ? '수확 후보' : '관찰 중',
      lastObserved: '',
      latestLabel: '',
      latestDisplayLabel: '',
      latestImageUrl: '',
    }
  }, [harvestPlant, mapScene.assets, plantLookup, selectedAsset, selectedPlantId])
  const selectedPlantObservationQuery = useQuery({
    queryKey: ['plants', 'observations', selectedPlantDetail?.id ?? selectedPlantId],
    queryFn: async () => getPlantObservations(selectedPlantDetail?.id ?? selectedPlantId ?? ''),
    enabled: Boolean(selectedPlantDetail?.id ?? selectedPlantId),
    refetchInterval: 20_000,
  })
  const selectedPlantObservationFeed = selectedPlantObservationQuery.data ?? emptyPlantObservationFeed
  const selectedPlantObservation = selectedPlantObservationFeed.items[0] ?? null

  useEffect(() => {
    if (selectedAssetId && mapScene.assets.some((asset) => asset.id === selectedAssetId)) {
      return
    }

    if (targetAssetId) {
      setSelectedAssetId(targetAssetId)
      return
    }

    if (activeHarvestPlant) {
      setSelectedAssetId(activeHarvestPlant.id)
      return
    }

    if (attentionPlant) {
      setSelectedAssetId(attentionPlant.id)
    }
  }, [activeHarvestPlant, attentionPlant, mapScene.assets, selectedAssetId, targetAssetId])

  useEffect(() => {
    if (selectedAsset?.kind === 'plant') {
      setSelectedPlantId(selectedAsset.id)
      return
    }

    if (!selectedPlantId && harvestPlant) {
      setSelectedPlantId(harvestPlant.id)
      return
    }

    if (selectedPlantId && !plants.plants.some((plant) => plant.id === selectedPlantId)) {
      setSelectedPlantId(harvestPlant?.id ?? null)
    }
  }, [harvestPlant, plants.plants, selectedAsset, selectedPlantId])

  const controlMode = latestCommandStatus.controlState?.mode ?? 'normal'
  const missionControlBlocked = controlMode === 'paused' || controlMode === 'emergency_stop'
  const missionControlBlockMessage =
    controlMode === 'emergency_stop'
      ? '비상 정지 상태에서는 재개 전까지 새 미션을 시작할 수 없습니다.'
      : controlMode === 'paused'
        ? '일시정지 상태에서는 재개 전까지 새 미션을 시작할 수 없습니다.'
        : null
  const harvestMissionError =
    harvestMutation.isError
      ? harvestMutation.error
      : harvestMissionStatusQuery.isError && harvestMissionStatusQuery.error instanceof Error
        ? harvestMissionStatusQuery.error
        : null
  const patrolMissionError =
    patrolMutation.isError
      ? patrolMutation.error
      : patrolMissionStatusQuery.isError && patrolMissionStatusQuery.error instanceof Error
        ? patrolMissionStatusQuery.error
        : null
  const harvestMissionFeedback = buildMissionFeedback(
    activeHarvestMission,
    harvestMissionStatus,
    harvestMissionError,
    {
      acceptedTitle: '수확 요청 접수',
      pendingTitle: '수확 준비 중',
      runningTitle: '수확 진행 중',
      successTitle: '수확 완료',
      failureTitle: '수확 실패',
      canceledTitle: '수확 취소',
    },
  )
  const patrolMissionFeedback = buildMissionFeedback(
    activePatrolMission,
    patrolMissionStatus,
    patrolMissionError,
    activePatrolMission?.mode === 'harvest'
      ? {
          acceptedTitle: '수확 패트롤 요청 접수',
          pendingTitle: '수확 패트롤 준비 중',
          runningTitle: '수확 패트롤 진행 중',
          successTitle: '수확 패트롤 완료',
          failureTitle: '수확 패트롤 실패',
          canceledTitle: '수확 패트롤 취소',
        }
      : {
          acceptedTitle: '진단 패트롤 요청 접수',
          pendingTitle: '진단 패트롤 준비 중',
          runningTitle: '진단 패트롤 진행 중',
          successTitle: '진단 패트롤 완료',
          failureTitle: '진단 패트롤 실패',
          canceledTitle: '진단 패트롤 취소',
        },
  )
  const missionRequestInFlight =
    harvestMutation.isPending
    || patrolMutation.isPending
    || stopMotionMutation.isPending
    || stopPatrolMutation.isPending
    || (harvestMissionFeedback !== null && !harvestMissionFeedback.isTerminal)
    || (patrolMissionFeedback !== null && !patrolMissionFeedback.isTerminal)
  const harvestActionDisabled = missionControlBlocked || missionRequestInFlight
  const patrolActionDisabled = missionControlBlocked || missionRequestInFlight
  const selectedPlantHasActiveHarvestRequest =
    selectedPlantDetail !== null
    && activeHarvestMission?.plantId === selectedPlantDetail.id
    && harvestMissionFeedback !== null
    && !harvestMissionFeedback.isTerminal
    && !missionControlBlocked
  const diagnosisPatrolActive =
    activePatrolMission?.mode === 'diagnosis'
    && patrolMissionFeedback !== null
    && !patrolMissionFeedback.isTerminal
    && !missionControlBlocked
  const harvestPatrolActive =
    activePatrolMission?.mode === 'harvest'
    && patrolMissionFeedback !== null
    && !patrolMissionFeedback.isTerminal
    && !missionControlBlocked
  const selectedPlantHarvestRuntime = useMemo(
    () => (
      selectedPlantDetail
        ? buildPlantHarvestRuntime(
            selectedPlantDetail,
            harvest,
            harvestMissionStatus,
            activeHarvestMission,
            harvestMissionFeedback,
          )
        : null
    ),
    [
      activeHarvestMission,
      harvest,
      harvestMissionFeedback,
      harvestMissionStatus,
      selectedPlantDetail,
    ],
  )
  const currentMissionActivity =
    harvestMissionFeedback !== null && !harvestMissionFeedback.isTerminal
      ? harvestMissionFeedback.status === 'running'
        ? `수확 ${formatHarvestPhase(harvestMissionStatus?.currentPhase || harvest.currentPhase)}`
        : '수확 준비중'
      : harvest.missionStatus === 'running'
        ? `수확 ${formatHarvestPhase(harvest.currentPhase)}`
        : harvest.missionStatus === 'pending'
          ? '수확 준비중'
          : patrolMissionFeedback !== null && !patrolMissionFeedback.isTerminal
            ? activePatrolMission?.mode === 'harvest'
              ? patrolMissionFeedback.status === 'running'
                ? '패트롤 수확중'
                : '패트롤 수확 준비중'
              : patrolMissionFeedback.status === 'running'
                ? '패트롤 진단중'
                : '패트롤 진단 준비중'
            : null

  useEffect(() => {
    if (!activeHarvestMission || !harvestMissionFeedback?.isTerminal || !harvestMissionFeedback.missionId) {
      return
    }

    const missionKey = `${harvestMissionFeedback.missionId}:${harvestMissionFeedback.status}`
    if (lastHandledHarvestMissionKey === missionKey) {
      return
    }

    setLastHandledHarvestMissionKey(missionKey)

    if (harvestMissionFeedback.status === 'succeeded' && activeHarvestMission.plantId && activeHarvestMission.plantName) {
      const plantId = activeHarvestMission.plantId
      setActionRecords((current) => ({
        ...current,
        [plantId]: {
          label: '수확 완료',
          detail: `${activeHarvestMission.plantName} 수확이 실제 상태 기준으로 완료되었습니다.`,
          tone: 'accent',
        },
      }))
    }

    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ['page', 'plants'] }),
      queryClient.invalidateQueries({ queryKey: ['page', 'harvest'] }),
      queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] }),
      queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
    ])
  }, [
    activeHarvestMission,
    harvestMissionFeedback,
    lastHandledHarvestMissionKey,
    queryClient,
  ])

  useEffect(() => {
    if (!activePatrolMission || !patrolMissionFeedback?.isTerminal || !patrolMissionFeedback.missionId) {
      return
    }

    const missionKey = `${patrolMissionFeedback.missionId}:${patrolMissionFeedback.status}`
    if (lastHandledPatrolMissionKey === missionKey) {
      return
    }

    setLastHandledPatrolMissionKey(missionKey)

    if (patrolMissionFeedback.status === 'succeeded' && activePatrolMission.mode) {
      setLastPatrolAction({
        mode: activePatrolMission.mode,
        detail: patrolMissionFeedback.detail,
      })
    }

    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] }),
      queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
      queryClient.invalidateQueries({ queryKey: ['page', 'plants'] }),
      queryClient.invalidateQueries({ queryKey: ['page', 'harvest'] }),
    ])
  }, [
    activePatrolMission,
    lastHandledPatrolMissionKey,
    patrolMissionFeedback,
    queryClient,
  ])

  const weatherSummary = dashboard.environmentStats.length > 0
    ? dashboard.environmentStats.map((stat) => `${stat.label} ${stat.value}`).join(' · ')
    : '날씨 데이터 대기 중'

  const mildewAlertCount = plants.alerts.filter(
    (alert) => alert.id.includes('disease') || alert.title.includes('병'),
  ).length
  const mildewPercent = Math.round((mildewAlertCount / Math.max(plants.plants.length, 1)) * 100)
  const harvestableCount = plants.plants.filter((plant) => plant.status.includes('수확')).length
  const harvestablePercent = Math.round((harvestableCount / Math.max(plants.plants.length, 1)) * 100)
  const harvestProgressPercent = Math.round(
    Number.parseFloat(
      (harvest.metrics.find((metric) => metric.label.includes('성공'))?.value ?? '95%').replace(
        /[^\d.]/g,
        '',
      ),
    ),
  )
  const lastPlantAction =
    [...Object.entries(actionRecords)].reverse().find(([assetId]) => assetId.startsWith('farm01_plant_'))?.[1]
    ?? null
  const lastSprinklerAction =
    [...Object.entries(actionRecords)].reverse().find(([assetId]) => assetId.startsWith('sprinkler_'))?.[1]
    ?? null
  const sprinklerResultPercent = lastSprinklerAction || environment.history.length > 0 ? 100 : 0
  const selectedTag = selectionTag(selectedAsset?.kind, selectedAsset?.status)
  const selectedPlantPreviewImage =
    selectedPlantObservation?.imageUrl
    || selectedPlantDetail?.latestImageUrl
    || ''
  const selectedAssetPreviewImage =
    selectedAsset?.kind === 'plant'
      ? selectedPlantPreviewImage || previewImageForAsset('plant', selectedAsset.status)
      : previewImageForAsset(selectedAsset?.kind, selectedAsset?.status)
  const selectedAssetPreviewLabel =
    selectedAsset?.kind === 'plant'
      ? selectedPlantObservation?.displayLabel || selectedPlantDetail?.latestDisplayLabel || selectedTag.label
      : selectedTag.label
  const currentActivity = currentMissionActivity ?? activityState ?? robot.missionState
  const selectedPlantTargetPose = useMemo(() => {
    if (!selectedPlantDetail) {
      return null
    }

    return buildPlantTargetPose(
      selectedPlantDetail.id,
      liveScene,
      mapScene,
      selectedPlantDetail.positionLabel,
    )
  }, [liveScene, mapScene, selectedPlantDetail])
  const diagnoseUiState = buildDiagnoseUiState(
    latestCommandStatus,
    activeDiagnoseCommand,
    selectedPlantDetail?.id ?? null,
    selectedPlantTargetPose,
    diagnoseMutation.isPending,
  )

  const feedbackMessage = uiMessage
    ?? (
      zoneMoveMutation.isSuccess
        ? zoneMoveMutation.data.message
        : zoneMoveMutation.isError
          ? zoneMoveMutation.error.message
          : wateringMutation.isSuccess
            ? wateringMutation.data
            : wateringMutation.isError
              ? wateringMutation.error.message
              : nutrientMutation.isSuccess
                ? nutrientMutation.data
                : nutrientMutation.isError
                  ? nutrientMutation.error.message
                  : controlMutation.isSuccess
                    ? controlMutation.data
                    : controlMutation.isError
                      ? controlMutation.error.message
                      : null
    )

  const selectedStatusItems = selectedAsset?.kind === 'plant' && selectedPlantDetail
    ? [
        { label: '상태', value: selectedPlantDetail.status },
        {
          label: '최근 진단',
          value:
            selectedPlantObservation?.displayLabel
            || selectedPlantDetail.latestDisplayLabel
            || '진단 결과 대기',
        },
        {
          label: '진단 시각',
          value:
            selectedPlantObservation?.reviewedAt
            || selectedPlantDetail.lastObserved
            || '기록 없음',
        },
        { label: '권장 조치', value: selectedPlantDetail.recommendedAction },
        { label: '수확 단계', value: selectedPlantHarvestRuntime?.phaseLabel ?? '대기 중' },
        { label: '바구니 상태', value: selectedPlantHarvestRuntime?.basketLabel ?? `현재 바구니 ${harvest.basketCount}개 적재` },
        {
          label: '최근 결과',
          value:
            selectedPlantHarvestRuntime?.latestResultLabel
            ?? selectedActionRecord?.label
            ?? (selectedAsset.status === 'attention' ? '조치 필요함' : selectedAsset.status === 'target' ? '수확 후보' : '대기'),
        },
        { label: '건강도', value: `${selectedPlantDetail.health}%` },
      ]
    : selectedAsset?.kind === 'sprinkler'
      ? [
          { label: '장치', value: selectedAsset.label },
          { label: '장치 상태', value: '정상 작동' },
          { label: '가능 작업', value: '물주기 / 영양제 주기' },
          {
            label: '작업 상태',
            value: selectedActionRecord?.label ?? '대기',
          },
        ]
      : []

  const handleGuideMove = (guideId: string) => {
    setUiMessage(null)
    setActivityState('이동중')

    const guideZoneMap: Record<string, string> = {
      'row-1': robot.zonePresets[0]?.id ?? 'farm_01',
      'row-2': robot.zonePresets[0]?.id ?? 'farm_01',
      'row-3': robot.zonePresets[0]?.id ?? 'farm_01',
      'row-4': robot.zonePresets[0]?.id ?? 'farm_01',
    }
    const zoneId = guideZoneMap[guideId]

    if (!zoneId) {
      return
    }

    zoneMoveMutation.mutate(zoneId)
  }

  const handleSelectAsset = (assetId: string) => {
    setSelectedAssetId(assetId)
    setUiMessage(null)

    if (assetId.startsWith('farm01_plant_')) {
      setSelectedPlantId(assetId)
      setIsAssetModalOpen(true)
      return
    }

    if (assetId.startsWith('sprinkler_')) {
      setIsAssetModalOpen(true)
      return
    }

    setIsAssetModalOpen(false)
  }

  const closeAssetModal = () => {
    setIsAssetModalOpen(false)
  }

  const handleStartPatrol = (mode: 'diagnosis' | 'harvest') => {
    if (missionControlBlocked || patrolMutation.isPending || harvestMutation.isPending) {
      return
    }

    setUiMessage(null)
    setActivityState(null)
    if (activePatrolMission?.missionId) {
      queryClient.removeQueries({ queryKey: ['missions', 'status', activePatrolMission.missionId] })
    }
    setActivePatrolMission(null)
    patrolMutation.reset()
    patrolMutation.mutate({
      mode,
      zoneIds: patrolZoneIds,
    })
  }

  const handleStopMotion = (context: 'diagnosis' | 'harvest') => {
    if (stopMotionMutation.isPending) {
      return
    }

    setUiMessage(null)
    setActivityState(context === 'diagnosis' ? '진단 이동 중단 요청 중' : '수확 중단 요청 중')
    setActiveStopRequest(context)
    stopMotionMutation.mutate(undefined, {
      onSuccess: (message) => {
        if (context === 'diagnosis') {
          setActiveDiagnoseCommand(null)
          setObservedDiagnoseState(null)
        }

        setActivityState('일시정지')
        setUiMessage(message)
      },
      onError: (error: Error) => {
        setUiMessage(error.message)
      },
      onSettled: () => {
        setActiveStopRequest(null)
      },
    })
  }

  const handleStopPatrol = (mode: 'diagnosis' | 'harvest') => {
    if (stopPatrolMutation.isPending) {
      return
    }

    setUiMessage(null)
    setActivityState(mode === 'diagnosis' ? '진단 패트롤 중단 요청 중' : '수확 패트롤 중단 요청 중')
    setActiveStopRequest(mode === 'diagnosis' ? 'patrol-diagnosis' : 'patrol-harvest')
    stopPatrolMutation.mutate(undefined, {
      onSuccess: (message) => {
        setActivityState('일시정지')
        setUiMessage(message)
      },
      onError: (error: Error) => {
        setUiMessage(error.message)
      },
      onSettled: () => {
        setActiveStopRequest(null)
      },
    })
  }

  const handleDiagnose = () => {
    const targetPlant = selectedAsset?.kind === 'plant'
      ? selectedPlantDetail
      : attentionPlant

    if (!targetPlant) {
      return
    }

    const targetPose = buildPlantTargetPose(
      targetPlant.id,
      liveScene,
      mapScene,
      targetPlant.positionLabel,
    )

    if (targetPose === null) {
      setUiMessage(`${targetPlant.name} 진단 접근 좌표를 계산하지 못해 이동을 시작할 수 없습니다.`)
      return
    }

    const blockedMessage = buildDiagnoseBlockedMessage(latestCommandStatus)
    if (blockedMessage) {
      setUiMessage(blockedMessage)
      return
    }

    setActivityState('진단 이동 준비중')
    setUiMessage(null)
    setSelectedPlantId(targetPlant.id)
    setSelectedAssetId(targetPlant.id)
    diagnoseMutation.mutate(targetPose)
  }

  const handleHarvest = () => {
    const targetPlant = selectedPlantDetail

    if (!targetPlant || missionControlBlocked || patrolMutation.isPending || harvestMutation.isPending) {
      return
    }

    setUiMessage(null)
    setActivityState('수확 준비중')
    if (activeHarvestMission?.missionId) {
      queryClient.removeQueries({ queryKey: ['missions', 'status', activeHarvestMission.missionId] })
    }
    setActiveHarvestMission(null)
    harvestMutation.reset()
    harvestMutation.mutate({
      plantId: targetPlant.id,
      fruitId: targetPlant.targetId,
      plantName: targetPlant.name,
    })
  }

  useEffect(() => {
    if (activeDiagnoseCommand === null) {
      return
    }

    const commandObserved = latestCommandStatus.commandId === activeDiagnoseCommand.commandId
    if (!commandObserved) {
      return
    }

    const stateToken = `${latestCommandStatus.commandId}:${latestCommandStatus.status}:${latestCommandStatus.updatedAt}`
    if (observedDiagnoseState === stateToken) {
      return
    }

    setObservedDiagnoseState(stateToken)

    if (latestCommandStatus.status === 'pending') {
      setActivityState('진단 이동 준비중')
      return
    }

    if (latestCommandStatus.status === 'running') {
      setActivityState('진단 이동중')
      return
    }

    if (latestCommandStatus.status === 'succeeded') {
      setActivityState('진단 위치 도착')
      rememberAction(
        activeDiagnoseCommand.plantId,
        '진단 완료',
        `${activeDiagnoseCommand.plantName} 진단 위치까지 실제 이동을 완료했습니다.`,
        'accent',
      )
      setUiMessage(
        latestCommandStatus.message
        || `${activeDiagnoseCommand.plantName} 진단 위치까지 이동을 완료했습니다.`,
      )
      return
    }

    if (latestCommandStatus.status === 'failed') {
      setActivityState(null)
      setUiMessage(
        latestCommandStatus.message
        || `${activeDiagnoseCommand.plantName} 진단 위치 이동이 실패했습니다.`,
      )
      return
    }

    if (latestCommandStatus.status === 'canceled') {
      setActivityState(null)
      setUiMessage(
        latestCommandStatus.message
        || `${activeDiagnoseCommand.plantName} 진단 위치 이동이 취소되었습니다.`,
      )
    }
  }, [activeDiagnoseCommand, latestCommandStatus, observedDiagnoseState])

  const handleWatering = () => {
    if (selectedAsset?.kind !== 'sprinkler') {
      return
    }

    setActivityState('급수중')
    setUiMessage(null)
    wateringMutation.mutate(undefined, {
      onSuccess: () => {
        rememberAction(
          selectedAsset.id,
          '물주기 완료',
          `${selectedAsset.label} 물주기 요청을 등록했습니다.`,
          'healthy',
        )
        setUiMessage(`${selectedAsset.label} 물주기 요청을 등록했습니다.`)
      },
    })
  }

  const handleNutrient = () => {
    if (selectedAsset?.kind !== 'sprinkler') {
      return
    }

    setActivityState('영양제 주기')
    setUiMessage(null)
    nutrientMutation.mutate(undefined, {
      onSuccess: () => {
        rememberAction(
          selectedAsset.id,
          '영양제 주기 완료',
          `${selectedAsset.label} 영양제 주기 요청을 등록했습니다.`,
          'accent',
        )
        setUiMessage(`${selectedAsset.label} 영양제 주기 요청을 등록했습니다.`)
      },
    })
  }

  const diagnosisMissionResult =
    activePatrolMission?.mode === 'diagnosis'
      ? patrolMissionFeedback
      : null
  const harvestMissionResult =
    activePatrolMission?.mode === 'harvest'
      ? patrolMissionFeedback
      : harvestMissionFeedback
  const harvestButtonLabel =
    selectedPlantHasActiveHarvestRequest
      ? activeStopRequest === 'harvest' && stopMotionMutation.isPending
        ? '수확 중단 요청 중...'
        : '수확 중단'
      : selectedPlantHarvestRuntime?.isHandled
        ? '수확 및 적재 완료'
        : harvestMutation.isPending && activeHarvestMission === null
          ? '수확 요청 중...'
          : selectedPlantHarvestRuntime?.isActive
            ? `${selectedPlantHarvestRuntime.phaseLabel}`
            : missionRequestInFlight && activeHarvestMission !== null
              ? '다른 수확 진행 중...'
              : '수확하기'
  const harvestButtonDisabled =
    selectedPlantHasActiveHarvestRequest
      ? stopMotionMutation.isPending
      : harvestActionDisabled || selectedPlantHarvestRuntime?.isHandled === true
  const diagnosisPatrolButtonLabel =
    diagnosisPatrolActive
      ? activeStopRequest === 'patrol-diagnosis' && stopPatrolMutation.isPending
        ? '패트롤로 병 진단 중단 요청 중...'
        : '패트롤로 병 진단 중단'
      : patrolMutation.isPending && activePatrolMission === null
        ? '진단 패트롤 요청 중...'
        : '패트롤로 병 진단'
  const diagnosisPatrolButtonDisabled =
    diagnosisPatrolActive ? stopPatrolMutation.isPending : patrolActionDisabled
  const harvestPatrolButtonLabel =
    harvestPatrolActive
      ? activeStopRequest === 'patrol-harvest' && stopPatrolMutation.isPending
        ? '패트롤로 전체 수확 중단 요청 중...'
        : '패트롤로 전체 수확 중단'
      : patrolMutation.isPending && activePatrolMission === null
        ? '수확 패트롤 요청 중...'
        : '패트롤로 전체 수확'
  const harvestPatrolButtonDisabled =
    harvestPatrolActive ? stopPatrolMutation.isPending : patrolActionDisabled

  const resultItems = [
    {
      icon: 'warning',
      tone: diagnosisMissionResult?.tone ?? 'danger',
      text:
        diagnosisMissionResult?.detail
        ?? (lastPatrolAction?.mode === 'diagnosis'
          ? lastPatrolAction.detail
          : selectedPlantObservation
            ? `${selectedPlantObservation.displayLabel} · ${selectedPlantObservation.detail}`
          : lastPlantAction?.label === '진단 완료'
            ? lastPlantAction.detail
            : `흰가루병 개체 ${mildewPercent}% 발견했습니다.`),
    },
    {
      icon: 'water_drop',
      tone: 'accent',
      text: lastSprinklerAction?.detail
        ?? `0번 스프링쿨러 ${sprinklerResultPercent}% 약재 분사 완료하였습니다.`,
    },
    {
      icon: 'potted_plant',
      tone: harvestMissionResult?.tone ?? 'warning',
      text:
        harvestMissionResult?.detail
        ?? selectedPlantHarvestRuntime?.detail
        ?? (lastPatrolAction?.mode === 'harvest'
          ? lastPatrolAction.detail
          : lastPlantAction?.label === '수확 완료'
            ? lastPlantAction.detail
            : `수확 가능 개체 ${harvestablePercent}% 발견했습니다.`),
    },
    {
      icon: 'inventory_2',
      tone: 'accent',
      text:
        harvest.lastHarvestedFruitId
          ? `바구니 ${harvest.basketCount}개 적재 중이며 마지막 수확은 ${harvest.lastHarvestedFruitId}입니다.`
          : `${harvestProgressPercent}% 수확 완료하였습니다.`,
    },
  ] as const

  const selectedTaskTitle = selectedAsset ? `${selectedSummary.title} 작업` : '작업 대상을 선택하세요'
  const selectedTaskDescription = selectedAsset?.kind === 'plant'
    ? selectedPlantHarvestRuntime?.detail ?? '식물 개별 작업은 맵 팝업에서 바로 실행합니다.'
    : selectedAsset?.kind === 'sprinkler'
      ? '급수 개별 작업도 맵 팝업에서 바로 실행합니다.'
      : '밭 전체 패트롤 또는 개별 객체 작업을 선택할 수 있습니다.'

  return (
    <div className="farm-layout-page">
      <DevSurface
        as="section"
        className="panel farm-map-shell"
        contract={{
          title: '밭 맵',
          queries: [
            createGetSignal('로봇 상태', mapSource('/robot/status'), '/robot/status'),
            createGetSignal('로봇 위치', mapSource('/robot/pose'), '/robot/pose'),
            createGetSignal('날씨 메모', dashboardSource('/environment/latest'), '/environment/latest'),
          ],
          actions: [
            createPostAction('이랑 이동', ['/robot/commands']),
          ],
        }}
      >
        <div className="farm-map-header">
          <div>
            <span className="section-eyebrow">맵</span>
            <h2 className="section-title">밭 위치 보기</h2>
            <p className="section-description">
              이랑 라벨을 누르면 이동하고, 식물과 급수 헤드를 누르면 해당 작업 버튼만 오른쪽에 나타납니다.
            </p>
            <div className="farm-map-tip-row">
              <span className="chip">이랑 클릭 이동</span>
              <span className="chip">식물 선택 시 진단·수확</span>
              <span className="chip">급수 헤드 선택 시 물주기·영양제</span>
            </div>
          </div>
          <div className="farm-weather-card">
            <span className="panel-kicker">날씨</span>
            <strong>{weatherSummary}</strong>
          </div>
        </div>

        <div className="map-board farm-map-board">
          <div className="camera-peek">
            <span className="camera-live-pill">
              <span className="live-dot" />
              이미지 확인
            </span>
            <div className="camera-frame">
              <MockupImage
                alt="선택 객체 이미지"
                className="camera-frame-media"
                height="100%"
                label={selectedAssetPreviewLabel}
                src={selectedAssetPreviewImage}
              />
            </div>
          </div>

          <RobotFacilityMap
            onSelectAsset={handleSelectAsset}
            onSelectGuide={handleGuideMove}
            pose={robotPose}
            scene={mapScene}
            selectedAssetId={selectedAssetId}
            targetAssetId={targetAssetId}
            zoom={1}
          />
        </div>

        <div className="farm-map-footer">
          <article className="farm-info-card">
            <div className="split-row">
              <div>
                <span className="panel-kicker">객체 확인</span>
                <h3 className="list-title">{selectedSummary.title}</h3>
              </div>
              <span className={`table-tag table-tag--${selectedTag.tone}`}>{selectedTag.label}</span>
            </div>
            <p>{selectedSummary.subtitle}</p>
            <div className="farm-status-list">
              {selectedStatusItems.map((item) => (
                <div className="farm-status-item" key={item.label}>
                  <span className="detail-label">{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
            <div className="chip-row">
              {selectedSummary.chips.map((chip) => (
                <span className="chip" key={chip}>
                  {chip}
                </span>
              ))}
            </div>
          </article>

          <article className="farm-info-card">
            <div className="section-head">
              <div>
                <span className="panel-kicker">로봇 상태</span>
                <h3 className="list-title">{dashboard.location}</h3>
              </div>
            </div>
            <div className="farm-status-list">
              <div className="farm-status-item">
                <span className="detail-label">현재 위치</span>
                <strong>{robot.zoneLabel}</strong>
              </div>
              <div className="farm-status-item">
                <span className="detail-label">좌표</span>
                <strong>{robot.poseLabel}</strong>
              </div>
              <div className="farm-status-item">
                <span className="detail-label">배터리</span>
                <strong>{dashboard.battery}</strong>
              </div>
              <div className="farm-status-item">
                <span className="detail-label">활동상태</span>
                <strong>{currentActivity}</strong>
              </div>
            </div>
          </article>
        </div>
      </DevSurface>

      <DevSurface
        as="aside"
        className="panel farm-dashboard-shell"
        contract={{
          title: '오른쪽 대시보드',
          queries: [
            createGetSignal('작물 목록', plantsSource('/plants'), '/plants'),
            createGetSignal('밭 상태', fieldSource('/environment/latest'), '/environment/latest'),
            createGetSignal('수확 통계', harvestSource('/harvests/stats'), '/harvests/stats'),
            createGetSignal('로봇 상태', mapSource('/robot/status'), '/robot/status'),
          ],
          actions: [
            createPostAction('수확 요청', ['/missions/harvest']),
            createPostAction('전체 진단 패트롤', ['/missions/patrol/start', '/robot/commands'], 'any'),
            createPostAction('전체 수확 패트롤', ['/missions/patrol/start', '/robot/commands'], 'any'),
            createPostAction('물 주기', ['/actuations/recommendations/reco-water-001/approve', '/actuations/watering'], 'any'),
            createPostAction('영양제 주기', ['/actuations/nutrients']),
            createPostAction('일시정지', ['/missions/patrol/stop', '/robot/commands'], 'any'),
            createPostAction('재개', ['/robot/commands']),
            createPostAction('귀가', ['/missions/return-home', '/robot/commands'], 'any'),
          ],
        }}
      >
        <div className="section-head">
          <div>
            <span className="section-eyebrow">대시보드</span>
            <h2 className="section-title">오른쪽 조작판</h2>
            <p className="section-description">선택한 대상에 맞는 작업만 보여 주고, 결과와 로봇 조작만 남겼습니다.</p>
          </div>
          <span className="live-pill">
            {[dashboard.source, robot.source, plants.source, environment.source, harvest.source].some(
              (source) => source === 'live',
            )
              ? '실시간 연결'
              : '샘플 보드'}
          </span>
        </div>

        <section className="farm-section-card">
          <div className="section-head">
            <div>
              <span className="panel-kicker">농사</span>
              <h3 className="list-title">{selectedTaskTitle}</h3>
              <p className="farm-helper-copy">{selectedTaskDescription}</p>
            </div>
          </div>

          <div className="farm-action-groups">
            <div className="farm-action-group">
              <span className="detail-label">밭 전체 패트롤</span>
              <div className="farm-action-row">
                <button
                  className="action-button"
                  disabled={diagnosisPatrolButtonDisabled}
                  onClick={() => {
                    if (diagnosisPatrolActive) {
                      handleStopPatrol('diagnosis')
                      return
                    }

                    handleStartPatrol('diagnosis')
                  }}
                  type="button"
                >
                  {diagnosisPatrolButtonLabel}
                </button>
                <button
                  className="action-button action-button--warning"
                  disabled={harvestPatrolButtonDisabled}
                  onClick={() => {
                    if (harvestPatrolActive) {
                      handleStopPatrol('harvest')
                      return
                    }

                    handleStartPatrol('harvest')
                  }}
                  type="button"
                >
                  {harvestPatrolButtonLabel}
                </button>
              </div>
              {missionControlBlockMessage ? <p className="muted">{missionControlBlockMessage}</p> : null}
              {patrolMissionFeedback ? (
                <>
                  <div className="chip-row">
                    <span className={`table-tag ${patrolMissionFeedback.tagTone}`}>{patrolMissionFeedback.badgeLabel}</span>
                    {activePatrolMission?.mode ? (
                      <span className="chip">
                        {activePatrolMission.mode === 'diagnosis' ? '병 진단' : '전체 수확'}
                      </span>
                    ) : null}
                    {patrolMissionFeedback.missionId ? <span className="chip">{patrolMissionFeedback.missionId}</span> : null}
                  </div>
                  <p className="muted">{patrolMissionFeedback.title} · {patrolMissionFeedback.detail}</p>
                </>
              ) : null}
            </div>

            {selectedAsset ? (
              <div className="farm-empty-state">
                <AppIcon name={selectedAsset.kind === 'plant' ? 'potted_plant' : 'water_drop'} />
                <p>
                  {selectedAsset.kind === 'plant'
                    ? '식물을 누르면 이미지와 함께 `진단하기`, `수확하기` 팝업이 열립니다.'
                    : '급수 헤드를 누르면 이미지와 함께 `물주기`, `영양제 주기` 팝업이 열립니다.'}
                </p>
                {selectedAsset.kind === 'plant' && missionControlBlockMessage ? <p className="muted">{missionControlBlockMessage}</p> : null}
                {selectedAsset.kind === 'plant' && selectedPlantHarvestRuntime ? (
                  <>
                    <div className="chip-row">
                      <span className={`table-tag table-tag--${
                        selectedPlantHarvestRuntime.isHandled
                          ? 'healthy'
                          : selectedPlantHarvestRuntime.isActive
                            ? 'warning'
                            : 'accent'
                      }`}
                      >
                        {selectedPlantHarvestRuntime.statusLabel}
                      </span>
                      <span className="chip">{selectedPlantHarvestRuntime.phaseLabel}</span>
                      <span className="chip">{selectedPlantHarvestRuntime.basketLabel}</span>
                    </div>
                    <p className="muted">{selectedPlantHarvestRuntime.detail}</p>
                  </>
                ) : null}
                {selectedAsset.kind === 'plant' && harvestMissionFeedback ? (
                  <>
                    <div className="chip-row">
                      <span className={`table-tag ${harvestMissionFeedback.tagTone}`}>{harvestMissionFeedback.badgeLabel}</span>
                      {activeHarvestMission?.plantName ? <span className="chip">{activeHarvestMission.plantName}</span> : null}
                      {harvestMissionFeedback.missionId ? <span className="chip">{harvestMissionFeedback.missionId}</span> : null}
                    </div>
                    <p className="muted">{harvestMissionFeedback.title} · {harvestMissionFeedback.detail}</p>
                  </>
                ) : null}
              </div>
            ) : (
              <div className="farm-empty-state">
                <AppIcon name="my_location" />
                <p>맵에서 대상을 먼저 고르면 개별 작업이 나타나고, 패트롤 버튼은 밭 전체를 순회합니다.</p>
              </div>
            )}
          </div>
        </section>

        <section className="farm-section-card">
          <div className="section-head">
            <div>
              <span className="panel-kicker">결과</span>
              <h3 className="list-title">작업 요약</h3>
            </div>
          </div>
          <div className="farm-result-list">
            {resultItems.map((item) => (
              <article className={`farm-result-item farm-result-item--${item.tone}`} key={item.text}>
                <div className="farm-result-icon">
                  <AppIcon filled={item.tone === 'danger'} name={item.icon} />
                </div>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="farm-section-card">
          <div className="section-head">
            <div>
              <span className="panel-kicker">로봇 조작</span>
              <h3 className="list-title">일시정지, 재개, 귀가</h3>
            </div>
          </div>
          <div className="farm-action-row farm-action-row--robot">
            {robotControlActions.map((action) => (
              <button
                className="action-button action-button--soft"
                disabled={controlMutation.isPending}
                key={action.id}
                onClick={() => {
                  setUiMessage(null)
                  setActivityState(action.nextState)
                  controlMutation.mutate(action.id)
                }}
                type="button"
              >
                <AppIcon name={action.icon} />
                {action.title}
              </button>
            ))}
          </div>
          {feedbackMessage ? <p className="muted">{feedbackMessage}</p> : null}
        </section>
      </DevSurface>

      {isAssetModalOpen && selectedPlantAsset && selectedPlantDetail ? (
        <div
          className="farm-plant-modal"
          onClick={() => {
            closeAssetModal()
          }}
          role="presentation"
        >
          <div
            className="farm-plant-modal__card"
            onClick={(event) => {
              event.stopPropagation()
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="farm-plant-modal-title"
          >
            <button
              aria-label="식물 팝업 닫기"
              className="farm-plant-modal__close"
              onClick={() => {
                closeAssetModal()
              }}
              type="button"
            >
              <AppIcon name="remove" />
            </button>
            <div className="farm-plant-modal__content">
              <div className="farm-plant-modal__media">
                <MockupImage
                  alt={`${selectedPlantDetail.name} 확인 이미지`}
                  className="farm-plant-modal__image"
                  height="100%"
                  label={selectedPlantObservation?.displayLabel || selectedPlantDetail.latestDisplayLabel || '발표용 이미지'}
                  src={selectedPlantPreviewImage || previewImageForAsset('plant', selectedPlantAsset.status)}
                />
              </div>

              <div className="farm-plant-modal__body">
                <div className="split-row">
                  <div>
                    <span className="panel-kicker">작물 확인</span>
                    <h3 className="list-title" id="farm-plant-modal-title">{selectedPlantDetail.name}</h3>
                  </div>
                  <span className={`table-tag table-tag--${selectedTag.tone}`}>{selectedTag.label}</span>
                </div>

                <div className="farm-plant-modal__actions">
                  <button
                    className={diagnoseUiState.buttonMode === 'stop' ? 'action-button action-button--warning' : 'action-button'}
                    disabled={
                      diagnoseUiState.buttonMode === 'stop'
                        ? stopMotionMutation.isPending
                        : diagnoseUiState.buttonDisabled
                    }
                    onClick={() => {
                      if (diagnoseUiState.buttonMode === 'stop') {
                        handleStopMotion('diagnosis')
                        return
                      }

                      handleDiagnose()
                    }}
                    type="button"
                  >
                    {diagnoseUiState.buttonMode === 'stop' && activeStopRequest === 'diagnosis' && stopMotionMutation.isPending
                      ? '진단 중단 요청 중...'
                      : diagnoseUiState.buttonLabel}
                  </button>
                  <button
                    className="action-button action-button--warning"
                    disabled={harvestButtonDisabled}
                    onClick={() => {
                      if (selectedPlantHasActiveHarvestRequest) {
                        handleStopMotion('harvest')
                        return
                      }

                      handleHarvest()
                    }}
                    type="button"
                  >
                    {harvestButtonLabel}
                  </button>
                </div>

                <p className="farm-helper-copy">
                  {selectedPlantHarvestRuntime?.isActive || selectedPlantHarvestRuntime?.isHandled
                    ? `${selectedPlantHarvestRuntime.statusLabel} · ${selectedPlantHarvestRuntime.detail}`
                    : selectedPlantObservation
                      ? `상태가 좋지 않은 잎을 진단한 결과 ${selectedPlantObservation.displayLabel}로 기록되었습니다. ${selectedPlantDetail.recommendedAction}`
                      : selectedPlantHarvestRuntime
                        ? `${selectedPlantHarvestRuntime.statusLabel} · ${selectedPlantHarvestRuntime.detail}`
                        : `${selectedPlantDetail.status} · ${selectedPlantDetail.recommendedAction}`}
                </p>

                <div className="chip-row">
                  <span className="chip">{selectedPlantDetail.zoneLabel}</span>
                  <span className="chip">{selectedPlantDetail.positionLabel}</span>
                  <span className="chip">건강도 {selectedPlantDetail.health}%</span>
                  {selectedPlantHarvestRuntime ? <span className="chip">{selectedPlantHarvestRuntime.phaseLabel}</span> : null}
                  {selectedPlantHarvestRuntime ? <span className="chip">{selectedPlantHarvestRuntime.basketLabel}</span> : null}
                  {selectedPlantObservation?.reviewedAt ? <span className="chip">{selectedPlantObservation.reviewedAt}</span> : null}
                </div>
                {missionControlBlockMessage ? <p className="muted">{missionControlBlockMessage}</p> : null}
                {selectedPlantHarvestRuntime ? (
                  <div className="farm-plant-modal__feedback">
                    <div className="farm-plant-modal__feedback-head">
                      <strong>{selectedPlantHarvestRuntime.statusLabel}</strong>
                      <span className={`table-tag table-tag--${
                        selectedPlantHarvestRuntime.isHandled
                          ? 'healthy'
                          : selectedPlantHarvestRuntime.isActive
                            ? 'warning'
                            : 'accent'
                      }`}
                      >
                        {selectedPlantHarvestRuntime.phaseLabel}
                      </span>
                    </div>
                    <p className="muted">{selectedPlantHarvestRuntime.detail}</p>
                    <div className="chip-row">
                      <span className="chip">{selectedPlantHarvestRuntime.latestResultLabel}</span>
                      {activeHarvestMission?.missionId ? <span className="chip">{activeHarvestMission.missionId}</span> : null}
                    </div>
                  </div>
                ) : null}
                {harvestMissionFeedback ? (
                  <>
                    <div className="chip-row">
                      <span className={`table-tag ${harvestMissionFeedback.tagTone}`}>{harvestMissionFeedback.badgeLabel}</span>
                      {activeHarvestMission?.plantName ? <span className="chip">{activeHarvestMission.plantName}</span> : null}
                      {harvestMissionFeedback.missionId ? <span className="chip">{harvestMissionFeedback.missionId}</span> : null}
                    </div>
                    <p className="muted">{harvestMissionFeedback.title} · {harvestMissionFeedback.detail}</p>
                  </>
                ) : null}

                <div className="farm-plant-modal__feedback">
                  <div className="farm-plant-modal__feedback-head">
                    <strong>최근 진단 결과</strong>
                    <span className={`table-tag ${selectedPlantObservation ? 'table-tag--danger' : 'table-tag--warning'}`}>
                      {selectedPlantObservation ? 'live' : '대기'}
                    </span>
                  </div>
                  <p className="muted">
                    {selectedPlantObservation
                      ? `${selectedPlantObservation.displayLabel} · ${selectedPlantObservation.reviewedAt || '시각 기록 대기'}`
                      : '상태가 좋지 않은 잎을 진단하면 사진과 라벨이 여기 표시됩니다.'}
                  </p>
                  <p className="muted">
                    {selectedPlantObservation?.detail
                      || 'backend에서 실제 진단 결과가 들어오면 mock 이미지 대신 실제 사진이 우선 표시됩니다.'}
                  </p>
                </div>

                <div className="farm-plant-modal__feedback">
                  <div className="farm-plant-modal__feedback-head">
                    <strong>{diagnoseUiState.title}</strong>
                    <span className={`table-tag ${diagnoseUiState.badgeTone}`}>
                      {diagnoseUiState.badgeLabel}
                    </span>
                  </div>
                  <p className="muted">{diagnoseUiState.detail}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {isAssetModalOpen && selectedSprinklerAsset ? (
        <div
          className="farm-plant-modal"
          onClick={() => {
            closeAssetModal()
          }}
          role="presentation"
        >
          <div
            className="farm-plant-modal__card"
            onClick={(event) => {
              event.stopPropagation()
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="farm-sprinkler-modal-title"
          >
            <button
              aria-label="급수 팝업 닫기"
              className="farm-plant-modal__close"
              onClick={() => {
                closeAssetModal()
              }}
              type="button"
            >
              <AppIcon name="remove" />
            </button>
            <div className="farm-plant-modal__content">
              <div className="farm-plant-modal__media">
                <MockupImage
                  alt={`${selectedSprinklerAsset.label} 확인 이미지`}
                  className="farm-plant-modal__image"
                  height="100%"
                  src={previewImageForAsset('sprinkler', selectedSprinklerAsset.status)}
                />
              </div>

              <div className="farm-plant-modal__body">
                <div className="split-row">
                  <div>
                    <span className="panel-kicker">급수 확인</span>
                    <h3 className="list-title" id="farm-sprinkler-modal-title">{selectedSprinklerAsset.label}</h3>
                  </div>
                  <span className={`table-tag table-tag--${selectedTag.tone}`}>{selectedTag.label}</span>
                </div>

                <p className="farm-helper-copy">정상 작동 중 · 물주기와 영양제 주기를 바로 실행할 수 있습니다.</p>

                <div className="chip-row">
                  <span className="chip">zone {selectedSprinklerAsset.zoneId}</span>
                  <span className="chip">x {selectedSprinklerAsset.position.x.toFixed(1)} / y {selectedSprinklerAsset.position.y.toFixed(1)}</span>
                  <span className="chip">{selectedActionRecord?.label ?? '작업 대기'}</span>
                </div>

                <div className="farm-plant-modal__actions">
                  <button
                    className="action-button action-button--soft"
                    disabled={wateringMutation.isPending}
                    onClick={() => {
                      handleWatering()
                      closeAssetModal()
                    }}
                    type="button"
                  >
                    {wateringMutation.isPending ? '물 주는 중...' : '물주기'}
                  </button>
                  <button
                    className="action-button"
                    disabled={nutrientMutation.isPending}
                    onClick={() => {
                      handleNutrient()
                      closeAssetModal()
                    }}
                    type="button"
                  >
                    {nutrientMutation.isPending ? '영양제 주는 중...' : '영양제 주기'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
