import { useCallback, useEffect, useMemo, useState } from 'react'
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
  dashboardFallback,
  emptyLiveCameraSnapshot,
  emptyPlantObservationFeed,
  environmentFallback,
  getDashboardPageData,
  getEnvironmentPageData,
  getHarvestPageData,
  getLiveCameraSnapshot,
  getPlantObservations,
  getMissionStatus,
  getPlantsPageData,
  getRobotPageData,
  harvestFallback,
  pauseRobotMotion,
  plantNeedsDiagnosis,
  plantsFallback,
  requestHarvestMission,
  robotFallback,
  runDemoDiagnosis,
  sendRobotControlAction,
  sendRobotNavigateCommand,
  sendRobotZoneMove,
  startFieldPatrolMission,
  stopPatrolMission,
  triggerSprinklerNutrient,
  triggerSprinklerWatering,
  type DemoDiagnosisResult,
  type HarvestPageData,
  type HealthTone,
  type MissionDispatch,
  type MissionStatus,
  type PlantObservationEntry,
  type PlantObservationFeed,
  type PlantsPageData,
  type PlantRow,
  type RobotCommandStatus,
  type RobotObservationGoalCandidate,
  type RobotTargetPose,
} from '@/lib/api/agribot'
import {
  farmSemanticScene,
  resolveSemanticTargetId,
  type SemanticAssetStatus,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'
import {
  useStablePreviewPath,
  useStableRobotPose,
  useStableSemanticScene,
} from '@/lib/robot-map/render-stability'
import { resolveObservationCandidateDisplayPose } from '@/lib/robot-map/approach-pose'
import {
  buildPlantInspectionNavigationPlan,
  type PlantNavigationPlan,
} from '@/lib/robot-map/plant-navigation-plan'
import { buildNavigationPreviewPath } from '@/lib/robot-map/navigation-preview'

const robotControlActions = [
  { id: 'pause', title: '일시정지', icon: 'pause_circle', nextState: '일시정지' },
  { id: 'resume', title: '재개', icon: 'play_circle', nextState: '재개중' },
  { id: 'home', title: '귀가', icon: 'route', nextState: '귀가중' },
] as const

const LIVE_CAMERA_POLL_INTERVAL_MS = 2_500

const DEMO_DIAGNOSIS_PLANT_ID = 'farm01_plant_18'

type ActionRecordTone = 'accent' | 'danger' | 'healthy' | 'warning'
type AssetActionStatusEffect = 'none' | 'handled'

type AssetActionRecord = {
  label: string
  detail: string
  tone: ActionRecordTone
  statusEffect: AssetActionStatusEffect
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
  inspectWaypointId?: string | null
  inspectWaypointIds?: string[]
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

function diagnosisToneFromResult(result: DemoDiagnosisResult): HealthTone {
  if (result.diagnosisNeeded) {
    return 'critical'
  }

  return result.healthPercent < 75 ? 'warning' : 'healthy'
}

function mergeDiagnosisIntoPlantsPage(
  current: PlantsPageData | undefined,
  plantId: string,
  result: DemoDiagnosisResult,
): PlantsPageData | undefined {
  if (!current) {
    return current
  }

  const nextPlants = current.plants.map((plant): PlantRow => {
    if (plant.id !== plantId) {
      return plant
    }

    return {
      ...plant,
      lastObserved: result.reviewedAt || plant.lastObserved,
      recommendedAction: result.recommendedAction,
      health: result.healthPercent,
      tone: diagnosisToneFromResult(result),
      status: result.diagnosisNeeded ? '조치 필요' : result.displayLabel,
      latestLabel: result.finalLabel,
      latestDisplayLabel: result.displayLabel,
      latestImageUrl: result.imageUrl,
    }
  })

  const diagnosisNeededCount = nextPlants.filter((plant) => plantNeedsDiagnosis(plant)).length
  const averageHealth =
    nextPlants.length > 0
      ? Math.round(nextPlants.reduce((total, plant) => total + plant.health, 0) / nextPlants.length)
      : null

  return {
    ...current,
    source: 'live',
    healthSummary: averageHealth !== null ? `${averageHealth}%` : current.healthSummary,
    criticalCount: String(diagnosisNeededCount).padStart(2, '0'),
    plants: nextPlants,
  }
}

function mergeDiagnosisIntoObservationFeed(
  current: PlantObservationFeed | undefined,
  plantId: string,
  plantName: string,
  result: DemoDiagnosisResult,
): PlantObservationFeed {
  const nextItem: PlantObservationEntry = {
    id: result.observationId,
    label: result.finalLabel,
    displayLabel: result.displayLabel,
    reviewedAt: result.reviewedAt,
    imageUrl: result.imageUrl,
    decisionSource: result.decisionSource,
    healthPercent: result.healthPercent,
    detail: result.detail,
  }

  return {
    source: 'live',
    plantId,
    plantName: current?.plantName || plantName,
    items: [
      nextItem,
      ...(current?.items ?? []).filter((item) => item.id !== result.observationId),
    ],
  }
}

type DiagnosePhase = 'transit' | 'inspection'

type DiagnoseRouteStep = {
  phase: DiagnosePhase
  pose: RobotTargetPose
  displayPose: RobotTargetPose
}

type DiagnoseCommandTracker = {
  commandId: string
  plantId: string
  fruitId: string
  plantName: string
  inspectWaypointId: string | null
  inspectWaypointIds: string[]
  observationCandidates: RobotObservationGoalCandidate[]
  targetPose: RobotTargetPose
  targetDisplayPose: RobotTargetPose
  routeSteps: DiagnoseRouteStep[]
  currentStepIndex: number
  currentTargetPose: RobotTargetPose
  currentTargetDisplayPose: RobotTargetPose
  phase: DiagnosePhase
  baselineToken: string
  requestedAt: number
}

type DiagnoseDispatchInput = {
  plantId: string
  fruitId: string
  plantName: string
  inspectWaypointId: string | null
  inspectWaypointIds: string[]
  observationCandidates: RobotObservationGoalCandidate[]
  targetPose: RobotTargetPose
  targetDisplayPose: RobotTargetPose
  routeSteps: DiagnoseRouteStep[]
  currentStepIndex: number
  currentTargetPose: RobotTargetPose
  currentTargetDisplayPose: RobotTargetPose
  phase: DiagnosePhase
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

type QueuedDiagnoseStart = {
  plantId: string
  fruitId: string
  plantName: string
  plan: PlantNavigationPlan
}

function plantNumberLabel(name: string, id: string) {
  return name.match(/\d+/)?.[0] ?? id.match(/\d+/)?.[0] ?? '00'
}

function plantModalTitle(name: string, id: string) {
  return `${plantNumberLabel(name, id)}번 토마토`
}

function sprinklerModalTitle(label: string, id: string) {
  const sprinklerNumber = label.match(/\d+/)?.[0] ?? id.replace('sprinkler_', '') ?? '0'
  return `${sprinklerNumber}번 스프링클러`
}

function diseaseNameLabel(latestDisplayLabel: string, latestLabel: string) {
  return latestDisplayLabel || latestLabel || '병해'
}

function treatmentNameLabel(recommendedAction: string) {
  const normalized = recommendedAction.trim()
  if (!normalized || normalized === '수확 요청 가능') {
    return '약재'
  }

  return normalized
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
        : '',
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
    return '/mock-images/sprinkler-gazebo.jpg'
  }

  if (status === 'attention') {
    return '/mock-images/disease-closeup.png'
  }

  return '/mock-images/healthy-default.jpg'
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
      label: kind === 'plant' ? '진단 필요' : '조치 필요',
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

const DIAGNOSE_OBSERVATION_DWELL_MS = 1200
const PLANT_OBSERVATION_SELECTION_STRATEGY = 'nearest' as const

function buildDiagnoseRoutePlan(
  plantId: string,
  targetPose: RobotTargetPose,
  currentPose: { x: number, y: number } | null,
  scene: SemanticScene,
  fallbackPositionLabel: string,
) {
  const plan = buildPlantInspectionNavigationPlan(
    plantId,
    scene,
    farmSemanticScene,
    fallbackPositionLabel,
    currentPose,
    {
      selectionStrategy: PLANT_OBSERVATION_SELECTION_STRATEGY,
      selectedCandidateOnly: true,
    },
  )

  const routeSteps: DiagnoseRouteStep[] =
    plan?.steps.map((step) => ({
      phase: (step.phase === 'final_observation' ? 'inspection' : 'transit') as DiagnosePhase,
      pose: step.pose,
      displayPose: step.displayPose,
    }))
    ?? [{ phase: 'inspection', pose: targetPose, displayPose: targetPose }]

  return {
    steps: routeSteps,
    inspectionPose: plan?.inspectionPose ?? targetPose,
    inspectionDisplayPose: plan?.inspectionDisplayPose ?? targetPose,
    inspectWaypointId: plan?.inspectWaypointId ?? null,
    inspectWaypointIds: plan?.inspectWaypointIds ?? [],
    observationCandidates: plan?.observationCandidates ?? [],
  }
}

function describeDiagnosePhase(phase: DiagnosePhase) {
  switch (phase) {
    case 'transit':
      return '연결 통로'
    case 'inspection':
    default:
      return '관측 위치'
  }
}

function diagnosePhaseFromStatus(status: RobotCommandStatus, fallbackPhase: DiagnosePhase) {
  if (status.navigationPhase === 'route_anchor') {
    return 'transit' as const
  }
  if (status.navigationPhase === 'final_observation') {
    return 'inspection' as const
  }

  return fallbackPhase
}

function canRestartDiagnosisWhilePaused(status: RobotCommandStatus) {
  return status.controlState?.mode === 'paused' && status.controlState.resumeAvailable
}

function buildDiagnoseBlockedMessage(status: RobotCommandStatus) {
  if (status.controlState?.mode === 'emergency_stop') {
    return '비상 정지 상태에서는 새 진단 이동 명령을 보낼 수 없습니다.'
  }

  if (canRestartDiagnosisWhilePaused(status)) {
    return null
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
      detail: '선택한 식물의 통로 관측 좌표를 계산하지 못했습니다. live semantic layer를 다시 확인한 뒤 재시도하세요.',
      badgeLabel: '좌표 없음',
      badgeTone: 'table-tag--danger',
      buttonLabel: '진단하기',
      buttonMode: 'start',
      buttonDisabled: true,
    }
  }

  const blockedMessage = buildDiagnoseBlockedMessage(latestCommandStatus)
  const resumeReadyWhilePaused = canRestartDiagnosisWhilePaused(latestCommandStatus)
  const trackingCurrentPlant =
    activeDiagnoseCommand !== null && activeDiagnoseCommand.plantId === currentPlantId
  const phaseLabel =
    activeDiagnoseCommand !== null
      ? describeDiagnosePhase(diagnosePhaseFromStatus(latestCommandStatus, activeDiagnoseCommand.phase))
      : '관측 위치'

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
            : '명령은 접수됐고 executor가 최신 상태 파일에 반영하는 중입니다.'
        ,
        badgeLabel: pollingDelayed ? '반영 대기' : '접수됨',
        badgeTone: 'table-tag--warning',
        buttonLabel: '진단 이동중...',
        buttonMode: 'start',
        buttonDisabled: true,
      }
    }

    switch (latestCommandStatus.status) {
      case 'pending':
        return {
          title: '관측 위치 이동 준비 중',
          detail:
            latestCommandStatus.message
            || 'executor가 통로 관측 위치 이동을 준비 중입니다.',
          badgeLabel: 'pending',
          badgeTone: 'table-tag--warning',
          buttonLabel: '진단 이동중...',
          buttonMode: 'start',
          buttonDisabled: true,
        }
      case 'running':
        return {
          title: '관측 위치로 이동 중',
          detail:
            latestCommandStatus.message
            || '로봇이 선택한 식물을 볼 수 있는 통로 관측 위치로 이동 중입니다.',
          badgeLabel: 'running',
          badgeTone: 'table-tag--warning',
          buttonLabel: '진단 이동중...',
          buttonMode: 'start',
          buttonDisabled: true,
        }
      case 'succeeded':
        return {
          title: '관측 위치 도착 완료',
          detail:
            latestCommandStatus.message
            || '목표 지점에 도착했습니다. 선택한 식물을 볼 수 있는 통로 관측 위치까지 이동을 완료했습니다.',
          badgeLabel: 'succeeded',
          badgeTone: 'table-tag--healthy',
          buttonLabel: '다시 진단하기',
          buttonMode: 'start',
          buttonDisabled: blockedMessage !== null,
        }
      case 'failed':
        return {
          title: `${phaseLabel} 이동 실패`,
          detail:
            latestCommandStatus.message
            || `backend 또는 executor가 ${phaseLabel} 이동 실패를 기록했습니다.`,
          badgeLabel: 'failed',
          badgeTone: 'table-tag--danger',
          buttonLabel: '다시 진단하기',
          buttonMode: 'start',
          buttonDisabled: blockedMessage !== null,
        }
      case 'canceled':
        return {
          title: `${phaseLabel} 이동 취소됨`,
          detail:
            latestCommandStatus.message
            || `${phaseLabel} 이동 명령이 취소되었거나 중단되었습니다.`,
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

  if (resumeReadyWhilePaused) {
    return {
      title: '진단 재시작 가능',
      detail: '일시정지된 수동 이동 문맥을 먼저 해제한 뒤, 통로 관측 위치로 진단 이동을 다시 시작합니다.',
      badgeLabel: '일시정지',
      badgeTone: 'table-tag--warning',
      buttonLabel: '다시 진단하기',
      buttonMode: 'start',
      buttonDisabled: false,
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
    detail: '버튼을 누르면 해당 식물을 볼 수 있는 가장 가까운 통로 관측 위치로 `navigate_to_pose`를 한 번 전송하고 `/robot/commands/latest` 상태를 추적합니다.',
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
  const [, setUiMessage] = useState<string | null>(null)
  const [actionRecords, setActionRecords] = useState<Record<string, AssetActionRecord>>({})
  const [activeHarvestMission, setActiveHarvestMission] = useState<PendingMissionRequest | null>(null)
  const [activePatrolMission, setActivePatrolMission] = useState<PendingMissionRequest | null>(null)
  const [lastHandledHarvestMissionKey, setLastHandledHarvestMissionKey] = useState<string | null>(null)
  const [lastHandledPatrolMissionKey, setLastHandledPatrolMissionKey] = useState<string | null>(null)
  const [activeDiagnoseCommand, setActiveDiagnoseCommand] = useState<DiagnoseCommandTracker | null>(null)
  const [observedDiagnoseState, setObservedDiagnoseState] = useState<string | null>(null)
  const [triggeredDemoDiagnosisCommandIds, setTriggeredDemoDiagnosisCommandIds] = useState<Record<string, boolean>>({})
  const [queuedDiagnoseStart, setQueuedDiagnoseStart] = useState<QueuedDiagnoseStart | null>(null)

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
    refetchOnWindowFocus: false,
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

  const controlMutation = useMutation({
    mutationFn: sendRobotControlAction,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })
  const zoneMoveMutation = useMutation({
    mutationFn: sendRobotZoneMove,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
    },
  })
  const stopMotionMutation = useMutation({
    mutationFn: pauseRobotMotion,
    onSuccess: async () => {
      const refreshJobs = [
        queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] }),
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
    mutationFn: ({ targetPose, inspectWaypointId, inspectWaypointIds, observationCandidates, plantId }: DiagnoseDispatchInput) => sendRobotNavigateCommand(
      targetPose,
      {
        inspectWaypointId,
        inspectWaypointIds,
        observationCandidates,
        plantId,
      },
    ),
    onSuccess: async (response, variables) => {
      setActiveDiagnoseCommand({
        commandId: response.commandId,
        plantId: variables.plantId,
        fruitId: variables.fruitId,
        plantName: variables.plantName,
        inspectWaypointId: variables.inspectWaypointId,
        inspectWaypointIds: variables.inspectWaypointIds,
        observationCandidates: variables.observationCandidates,
        targetPose: variables.targetPose,
        targetDisplayPose: variables.targetDisplayPose,
        routeSteps: variables.routeSteps,
        currentStepIndex: variables.currentStepIndex,
        currentTargetPose: variables.currentTargetPose,
        currentTargetDisplayPose: variables.currentTargetDisplayPose,
        phase: variables.phase,
        baselineToken: latestCommandToken(latestCommandStatus),
        requestedAt: Date.now(),
      })
      setObservedDiagnoseState(null)
      setActivityState('안전 관측 경로 이동 중')
      setSelectedPlantId(variables.plantId)
      setSelectedAssetId(variables.plantId)
      setUiMessage(
        `${variables.plantName} 진단 이동 요청을 접수했습니다. executor가 안전 경유점과 최종 관측점을 순서대로 처리합니다.`,
      )

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
      ])
    },
    onError: (error: Error) => {
      setUiMessage(error.message)
    },
  })
  const demoDiagnosisMutation = useMutation({
    mutationFn: ({
      plantId,
      fruitId,
      targetPose,
    }: {
      plantId: string
      fruitId: string
      plantName: string
      targetPose: RobotTargetPose
    }) => runDemoDiagnosis({ plantId, fruitId, targetPose }),
    onSuccess: async (result, variables) => {
      setActivityState('AI 진단 완료')
      rememberAction(
        variables.plantId,
        'AI 진단 저장',
        `${variables.plantName} 진단 결과 ${result.displayLabel} 이 DB에 저장되었습니다.`,
        result.diagnosisNeeded ? 'danger' : 'healthy',
      )
      setUiMessage(
        `${variables.plantName} 시연용 AI 진단이 완료되었습니다. ${result.displayLabel} 결과가 저장되었습니다.`,
      )

      queryClient.setQueryData<PlantsPageData>(
        ['page', 'plants'],
        (current) => mergeDiagnosisIntoPlantsPage(current, variables.plantId, result),
      )
      queryClient.setQueryData<PlantObservationFeed>(
        ['plants', 'observations', variables.plantId],
        (current) => mergeDiagnosisIntoObservationFeed(current, variables.plantId, variables.plantName, result),
      )

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['page', 'plants'] }),
        queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] }),
        queryClient.invalidateQueries({ queryKey: ['plants', 'observations', variables.plantId] }),
      ])
    },
    onError: (error: Error) => {
      setActivityState('진단 위치 도착')
      setUiMessage(error.message)
    },
  })
  const harvestMutation = useMutation({
    mutationFn: ({ plantId, fruitId, inspectWaypointId, inspectWaypointIds }: HarvestMissionInput) =>
      requestHarvestMission({
        plantId,
        fruitId,
        inspectWaypointId,
        inspectWaypointIds,
      }),
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
    mutationFn: triggerSprinklerWatering,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'environment'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })
  const nutrientMutation = useMutation({
    mutationFn: triggerSprinklerNutrient,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'environment'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })

  const dashboard = dashboardQuery.data
  const robot = robotQuery.data
  const latestCommandStatus = robot.latestCommandStatus
  const navigationPreview = robot.navigationPreview
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
    statusEffect: AssetActionStatusEffect = 'none',
  ) => {
    setActionRecords((current) => ({
      ...current,
      [assetId]: {
        label,
        detail,
        tone,
        statusEffect,
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
    plants.plants.find((plant) => plantNeedsDiagnosis(plant))
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
  const stableLiveScene = useStableSemanticScene(liveScene)
  const stableRobotPose = useStableRobotPose(robotPose)

  const mapScene = useMemo<SemanticScene>(() => ({
    ...stableLiveScene,
    assets: stableLiveScene.assets.map((asset) => {
      const actionRecord = actionRecords[asset.id]

      if (asset.kind === 'plant') {
        const plant = plantLookup.get(asset.id)
        const attention = plant ? plantNeedsDiagnosis(plant) : asset.status === 'attention'
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
          actionRecord?.statusEffect === 'handled' || runtimeHandled
            ? 'handled'
            : attention
              ? 'attention'
              : runtimeHarvestTarget || harvestTarget
                ? 'target'
                : 'normal'
        const nextLinkedId = plant?.targetId ?? asset.linkedId
        const nextLabel = plant?.name ?? asset.label
        const nextShortLabel = plant?.name.replace('토마토 ', '') ?? asset.shortLabel
        const nextDescription =
          actionRecord
            ? actionRecord.detail
            : runtimeHandled
              ? `${plant?.name ?? asset.label} 수확과 등 바구니 적재가 완료되었습니다.`
              : runtimeHarvestTarget
                ? harvest.detailMessage || `${plant?.name ?? asset.label} ${formatHarvestPhase(harvest.currentPhase)}`
                : plant
                  ? `${plant.status} · ${plant.recommendedAction}`
                  : asset.description

        if (
          nextLinkedId === asset.linkedId
          && nextLabel === asset.label
          && nextShortLabel === asset.shortLabel
          && nextDescription === asset.description
          && status === asset.status
        ) {
          return asset
        }

        return {
          ...asset,
          linkedId: nextLinkedId,
          label: nextLabel,
          shortLabel: nextShortLabel,
          description: nextDescription,
          status,
        }
      }

      const sprinklerIndex = Number(asset.id.replace('sprinkler_', ''))
      const status: SemanticAssetStatus = actionRecord?.statusEffect === 'handled' ? 'handled' : 'normal'
      const nextLabel = `${sprinklerIndex + 1}번 급수 헤드`
      const nextShortLabel = `S${sprinklerIndex + 1}`
      const nextDescription = actionRecord
        ? actionRecord.detail
        : '고장 없이 정상 작동하는 급수 포인트입니다.'

      if (
        nextLabel === asset.label
        && nextShortLabel === asset.shortLabel
        && nextDescription === asset.description
        && status === asset.status
      ) {
        return asset
      }

      return {
        ...asset,
        label: nextLabel,
        shortLabel: nextShortLabel,
        description: nextDescription,
        status,
      }
    }),
  }), [
    actionRecords,
    harvest.activeTargetId,
    harvest.currentPhase,
    harvest.detailMessage,
    harvest.lastHarvestedFruitId,
    stableLiveScene,
    plantLookup,
    runtimeActiveHarvestPlantId,
    runtimeHandledFruitIds,
  ])
  const stableMapScene = useStableSemanticScene(mapScene)

  const selectedAsset = useMemo(
    () => stableMapScene.assets.find((asset) => asset.id === selectedAssetId) ?? null,
    [selectedAssetId, stableMapScene.assets],
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
          ? stableMapScene.assets.find((item) => item.id === selectedPlantId && item.kind === 'plant') ?? null
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
      status: asset.status === 'attention' ? '진단 필요' : asset.status === 'target' ? '수확 후보' : '관찰 중',
      lastObserved: '',
      latestLabel: '',
      latestDisplayLabel: '',
      latestImageUrl: '',
    }
  }, [harvestPlant, plantLookup, selectedAsset, selectedPlantId, stableMapScene.assets])
  const selectedPlantObservationQuery = useQuery({
    queryKey: ['plants', 'observations', selectedPlantDetail?.id ?? selectedPlantId],
    queryFn: async () => getPlantObservations(selectedPlantDetail?.id ?? selectedPlantId ?? ''),
    enabled: Boolean(selectedPlantDetail?.id ?? selectedPlantId),
    refetchInterval: isAssetModalOpen ? 5_000 : 20_000,
  })
  const selectedPlantObservationFeed = selectedPlantObservationQuery.data ?? emptyPlantObservationFeed
  const selectedPlantObservation = selectedPlantObservationFeed.items[0] ?? null
  const selectedPlantLiveCameraQuery = useQuery({
    queryKey: ['robot', 'live-camera', 'latest'],
    queryFn: async () => getLiveCameraSnapshot(),
    enabled: isAssetModalOpen && Boolean(selectedPlantDetail?.id ?? selectedPlantId),
    refetchInterval: isAssetModalOpen ? LIVE_CAMERA_POLL_INTERVAL_MS : false,
  })
  const selectedPlantLiveCamera = selectedPlantLiveCameraQuery.data ?? emptyLiveCameraSnapshot

  useEffect(() => {
    if (selectedAssetId && stableMapScene.assets.some((asset) => asset.id === selectedAssetId)) {
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
  }, [activeHarvestPlant, attentionPlant, selectedAssetId, stableMapScene.assets, targetAssetId])

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
          statusEffect: 'handled',
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

  const selectedTag = selectionTag(selectedAsset?.kind, selectedAsset?.status)
  const selectedPlantLiveCameraImage = useMemo(() => {
    if (
      !selectedPlantLiveCamera.available
      || selectedPlantLiveCamera.isStale
      || !selectedPlantLiveCamera.imageUrl
    ) {
      return ''
    }

    const cacheKey = selectedPlantLiveCamera.capturedAt || String(Date.now())
    try {
      const url = new URL(selectedPlantLiveCamera.imageUrl)
      url.searchParams.set('captured_at', cacheKey)
      return url.toString()
    } catch {
      const delimiter = selectedPlantLiveCamera.imageUrl.includes('?') ? '&' : '?'
      return `${selectedPlantLiveCamera.imageUrl}${delimiter}captured_at=${encodeURIComponent(cacheKey)}`
    }
  }, [
    selectedPlantLiveCamera.available,
    selectedPlantLiveCamera.capturedAt,
    selectedPlantLiveCamera.imageUrl,
    selectedPlantLiveCamera.isStale,
  ])
  const selectedPlantMatchedObservationImage =
    selectedPlantLiveCamera.plantId === selectedPlantDetail?.id
      ? selectedPlantLiveCamera.observationImageUrl
      : ''
  const selectedPlantPreviewImage =
    selectedPlantMatchedObservationImage
    || selectedPlantObservation?.imageUrl
    || selectedPlantDetail?.latestImageUrl
    || selectedPlantLiveCameraImage
    || ''
  const selectedPlantPreviewLabel =
    selectedPlantMatchedObservationImage
      ? '방금 촬영된 작물 이미지'
      : selectedPlantObservation?.displayLabel
        || selectedPlantDetail?.latestDisplayLabel
        || (selectedPlantLiveCameraImage ? '실시간 로봇 카메라' : '발표용 이미지')
  const selectedPlantPreviewNote =
    selectedPlantMatchedObservationImage
      ? '선택한 식물에 대해 가장 최근에 저장된 자동 관측 이미지입니다.'
      : selectedPlantObservation !== null
        ? '최근 자동 관측으로 저장된 식물 스냅샷입니다.'
        : selectedPlantDetail?.latestImageUrl
          ? '최근 저장된 식물 이미지입니다.'
          : selectedPlantLiveCameraImage
            ? '현재 로봇이 보는 Gazebo 카메라 전체 화면입니다. 식물별 관측 이미지가 생기면 그 사진을 먼저 보여줍니다.'
            : '백엔드 live 이미지가 없으면 시연용 기본 이미지를 표시합니다.'
  const currentActivity = currentMissionActivity ?? activityState ?? robot.missionState
  const selectedPlantNavigationPlan = useMemo(() => {
    if (!selectedPlantDetail) {
      return null
    }

    return buildPlantInspectionNavigationPlan(
      selectedPlantDetail.id,
      stableLiveScene,
      stableMapScene,
      selectedPlantDetail.positionLabel,
      stableRobotPose
        ? {
            x: stableRobotPose.x,
            y: stableRobotPose.y,
          }
        : null,
      {
        selectionStrategy: PLANT_OBSERVATION_SELECTION_STRATEGY,
        selectedCandidateOnly: true,
      },
    )
  }, [selectedPlantDetail, stableLiveScene, stableMapScene, stableRobotPose])
  const selectedPlantTargetPose = selectedPlantNavigationPlan?.inspectionPose ?? null
  const diagnoseCommandActive =
    latestCommandStatus.status === 'pending' || latestCommandStatus.status === 'running'
  const mapPreviewPath = useMemo(() => {
    if (
      activeDiagnoseCommand !== null
      && navigationPreview.available
      && navigationPreview.points.length >= 2
      && diagnoseCommandActive
    ) {
      return buildNavigationPreviewPath(stableRobotPose, navigationPreview.points)
    }

    if (
      activeDiagnoseCommand !== null
      && latestCommandStatus.routeTargetPose
      && latestCommandStatus.finalTargetPose
      && diagnoseCommandActive
    ) {
      return buildNavigationPreviewPath(
        stableRobotPose,
        latestCommandStatus.navigationPhase === 'route_anchor'
          ? [latestCommandStatus.routeTargetPose, latestCommandStatus.finalTargetPose]
          : [latestCommandStatus.finalTargetPose],
      )
    }

    if (activeDiagnoseCommand !== null) {
      return buildNavigationPreviewPath(
        stableRobotPose,
        activeDiagnoseCommand.routeSteps
          .slice(activeDiagnoseCommand.currentStepIndex)
          .map((step) => step.pose),
      )
    }

    if (selectedPlantTargetPose) {
      return buildNavigationPreviewPath(stableRobotPose, [selectedPlantTargetPose])
    }

    return []
  }, [activeDiagnoseCommand, diagnoseCommandActive, latestCommandStatus, navigationPreview, selectedPlantTargetPose, stableRobotPose])
  const stableMapPreviewPath = useStablePreviewPath(mapPreviewPath)
  const activeDiagnoseAsset = useMemo(
    () => (
      activeDiagnoseCommand
        ? stableMapScene.assets.find((asset) => asset.id === activeDiagnoseCommand.plantId) ?? null
        : null
    ),
    [activeDiagnoseCommand, stableMapScene.assets],
  )
  const activeDiagnoseFinalTarget = useMemo(() => {
    if (!diagnoseCommandActive) {
      return null
    }

    return latestCommandStatus.finalTargetPose ?? activeDiagnoseCommand?.targetPose ?? selectedPlantTargetPose
  }, [
    activeDiagnoseCommand,
    diagnoseCommandActive,
    latestCommandStatus.finalTargetPose,
    selectedPlantTargetPose,
  ])
  const activeDiagnoseMarkerPose = useMemo(() => {
    if (!diagnoseCommandActive || !latestCommandStatus.targetPose) {
      return null
    }

    if (latestCommandStatus.navigationPhase === 'final_observation') {
      return (
        resolveObservationCandidateDisplayPose(activeDiagnoseAsset, activeDiagnoseFinalTarget)
        ?? activeDiagnoseCommand?.targetDisplayPose
        ?? selectedPlantNavigationPlan?.inspectionDisplayPose
        ?? activeDiagnoseFinalTarget
        ?? latestCommandStatus.targetPose
      )
    }

    return latestCommandStatus.routeTargetPose ?? latestCommandStatus.targetPose
  }, [
    activeDiagnoseAsset,
    activeDiagnoseCommand,
    activeDiagnoseFinalTarget,
    diagnoseCommandActive,
    latestCommandStatus.navigationPhase,
    latestCommandStatus.routeTargetPose,
    latestCommandStatus.targetPose,
    selectedPlantNavigationPlan,
  ])
  const activeDiagnoseFinalMarkerPose = useMemo(() => {
    if (!diagnoseCommandActive || !activeDiagnoseFinalTarget) {
      return null
    }

    return (
      resolveObservationCandidateDisplayPose(activeDiagnoseAsset, activeDiagnoseFinalTarget)
      ?? activeDiagnoseCommand?.targetDisplayPose
      ?? selectedPlantNavigationPlan?.inspectionDisplayPose
      ?? activeDiagnoseFinalTarget
    )
  }, [
    activeDiagnoseAsset,
    activeDiagnoseCommand,
    activeDiagnoseFinalTarget,
    diagnoseCommandActive,
    selectedPlantNavigationPlan,
  ])
  const stableActiveCommandTarget = useStableRobotPose(
    diagnoseCommandActive ? latestCommandStatus.targetPose : null,
  )
  const stableActiveDiagnoseMarkerPose = useStableRobotPose(activeDiagnoseMarkerPose)
  const stableActiveDiagnoseFinalTarget = useStableRobotPose(
    diagnoseCommandActive ? activeDiagnoseFinalTarget : null,
  )
  const stableActiveDiagnoseFinalMarkerPose = useStableRobotPose(activeDiagnoseFinalMarkerPose)
  const stablePendingDiagnosePose = useStableRobotPose(selectedPlantTargetPose)
  const stablePendingDiagnoseMarkerPose = useStableRobotPose(
    selectedPlantNavigationPlan?.inspectionDisplayPose
    ?? selectedPlantTargetPose,
  )
  const diagnoseUiState = buildDiagnoseUiState(
    latestCommandStatus,
    activeDiagnoseCommand,
    selectedPlantDetail?.id ?? null,
    selectedPlantTargetPose,
    diagnoseMutation.isPending || queuedDiagnoseStart !== null,
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
          { label: '가능 작업', value: '물 주기 / 약 주기' },
          {
            label: '작업 상태',
            value: selectedActionRecord?.label ?? '대기',
          },
        ]
      : []

  const dispatchDiagnoseStart = useCallback((input: QueuedDiagnoseStart) => {
    const diagnoseRoute = buildDiagnoseRoutePlan(
      input.plantId,
      input.plan.inspectionPose,
      stableRobotPose
        ? {
            x: stableRobotPose.x,
            y: stableRobotPose.y,
          }
        : null,
      stableLiveScene,
      plantLookup.get(input.plantId)?.positionLabel ?? '',
    )
    const firstStep = diagnoseRoute.steps[0]

    if (!firstStep) {
      setUiMessage(`${input.plantName} 진단 경로를 계산하지 못했습니다.`)
      return
    }

    setActivityState(firstStep.phase === 'inspection' ? '진단 이동 준비중' : '진단 경로 준비중')
    setUiMessage(null)
    setSelectedPlantId(input.plantId)
    setSelectedAssetId(input.plantId)
    diagnoseMutation.mutate({
      plantId: input.plantId,
      fruitId: input.fruitId,
      plantName: input.plantName,
      inspectWaypointId: diagnoseRoute.inspectWaypointId,
      inspectWaypointIds: diagnoseRoute.inspectWaypointIds,
      observationCandidates: diagnoseRoute.observationCandidates,
      targetPose: diagnoseRoute.inspectionPose,
      targetDisplayPose: diagnoseRoute.inspectionDisplayPose,
      routeSteps: diagnoseRoute.steps,
      currentStepIndex: 0,
      currentTargetPose: firstStep.pose,
      currentTargetDisplayPose: firstStep.displayPose,
      phase: firstStep.phase,
    })
  }, [diagnoseMutation, plantLookup, stableLiveScene, stableRobotPose])

  const handleGuideMove = useCallback((guideId: string) => {
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
  }, [robot.zonePresets, zoneMoveMutation])

  const handleSelectAsset = useCallback((assetId: string) => {
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
  }, [])

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

    const inspectionPlan = buildPlantInspectionNavigationPlan(
      targetPlant.id,
      stableLiveScene,
      stableMapScene,
      targetPlant.positionLabel,
      stableRobotPose
        ? {
            x: stableRobotPose.x,
            y: stableRobotPose.y,
          }
        : null,
      {
        selectionStrategy: PLANT_OBSERVATION_SELECTION_STRATEGY,
        selectedCandidateOnly: true,
      },
    )

    if (inspectionPlan === null) {
      setUiMessage(`${targetPlant.name} 진단 관측 경로를 계산하지 못해 이동을 시작할 수 없습니다.`)
      return
    }

    const diagnoseStartInput = {
      plantId: targetPlant.id,
      fruitId: targetPlant.targetId,
      plantName: targetPlant.name,
      plan: inspectionPlan,
    } satisfies QueuedDiagnoseStart

    if (canRestartDiagnosisWhilePaused(latestCommandStatus)) {
      setQueuedDiagnoseStart(diagnoseStartInput)
      setActivityState('일시정지 해제 후 진단 재시작 중')
      setUiMessage('저장된 일시정지 문맥을 해제한 뒤 새 진단 경로를 시작합니다.')
      controlMutation.mutate('resume', {
        onError: (error: Error) => {
          setQueuedDiagnoseStart(null)
          setUiMessage(error.message)
        },
      })
      return
    }

    const blockedMessage = buildDiagnoseBlockedMessage(latestCommandStatus)
    if (blockedMessage) {
      setUiMessage(blockedMessage)
      return
    }

    dispatchDiagnoseStart(diagnoseStartInput)
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
      inspectWaypointId: selectedPlantNavigationPlan?.inspectWaypointId ?? null,
      inspectWaypointIds: selectedPlantNavigationPlan?.inspectWaypointIds ?? [],
    })
  }

  useEffect(() => {
    if (queuedDiagnoseStart === null) {
      return
    }

    if (latestCommandStatus.controlState?.mode !== 'normal') {
      return
    }

    setQueuedDiagnoseStart(null)
    dispatchDiagnoseStart(queuedDiagnoseStart)
  }, [
    dispatchDiagnoseStart,
    latestCommandStatus.controlState?.mode,
    queuedDiagnoseStart,
  ])

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
      setActivityState(
        latestCommandStatus.navigationPhase === 'final_observation'
          ? '최종 관측 접근 중'
          : '안전 경유점 이동 중',
      )
      return
    }

    if (latestCommandStatus.status === 'succeeded') {
      const shouldRunDemoDiagnosis =
        activeDiagnoseCommand.plantId === DEMO_DIAGNOSIS_PLANT_ID
        && !triggeredDemoDiagnosisCommandIds[activeDiagnoseCommand.commandId]

      setActivityState(shouldRunDemoDiagnosis ? 'AI 진단중' : '관측 위치 도착')
      rememberAction(
        activeDiagnoseCommand.plantId,
        '진단 완료',
        `${activeDiagnoseCommand.plantName} 통로 관측 위치까지 실제 이동을 완료했습니다.`,
        'accent',
      )
      if (shouldRunDemoDiagnosis) {
        setActivityState('관측 정지중')
        setTriggeredDemoDiagnosisCommandIds((current) => ({
          ...current,
          [activeDiagnoseCommand.commandId]: true,
        }))
        setUiMessage(
          `${activeDiagnoseCommand.plantName} 통로 관측 위치에 정지했습니다. 잠시 안정화한 뒤 시연용 기준 이미지를 AI에 전달합니다.`,
        )
        setTimeout(() => {
          demoDiagnosisMutation.mutate({
            plantId: activeDiagnoseCommand.plantId,
            fruitId: activeDiagnoseCommand.fruitId,
            plantName: activeDiagnoseCommand.plantName,
            targetPose: activeDiagnoseCommand.targetPose,
          })
        }, DIAGNOSE_OBSERVATION_DWELL_MS)
        return
      }

      setUiMessage(
        latestCommandStatus.message
        || `${activeDiagnoseCommand.plantName} 목표 지점에 도착했습니다. 작물 관측 이동을 완료했습니다.`,
      )
      return
    }

    if (latestCommandStatus.status === 'failed') {
      setActivityState(null)
      setUiMessage(
        latestCommandStatus.message
        || (
          `${activeDiagnoseCommand.plantName} ${describeDiagnosePhase(diagnosePhaseFromStatus(latestCommandStatus, activeDiagnoseCommand.phase))} 이동이 실패했습니다.`
        ),
      )
      return
    }

    if (latestCommandStatus.status === 'canceled') {
      setActivityState(null)
      setUiMessage(
        latestCommandStatus.message
        || (
          `${activeDiagnoseCommand.plantName} ${describeDiagnosePhase(diagnosePhaseFromStatus(latestCommandStatus, activeDiagnoseCommand.phase))} 이동이 취소되었습니다.`
        ),
      )
    }
  }, [
    activeDiagnoseCommand,
    demoDiagnosisMutation,
    latestCommandStatus,
    observedDiagnoseState,
    triggeredDemoDiagnosisCommandIds,
  ])

  const handleWatering = () => {
    if (selectedAsset?.kind !== 'sprinkler') {
      return
    }

    setActivityState('급수중')
    setUiMessage(null)
    wateringMutation.mutate({
      deviceId: selectedAsset.id,
      zoneId: selectedAsset.zoneId,
    }, {
      onSuccess: () => {
        rememberAction(
          selectedAsset.id,
          '물 주기 요청 등록',
          `${selectedAsset.label} 물 주기 명령을 IoT 제어 파이프라인에 전달했습니다.`,
          'healthy',
        )
        setUiMessage(`${selectedAsset.label} 물 주기 명령을 전달했습니다.`)
      },
    })
  }

  const handleNutrient = () => {
    if (selectedAsset?.kind !== 'sprinkler') {
      return
    }

    setActivityState('약 주기')
    setUiMessage(null)
    nutrientMutation.mutate({
      deviceId: selectedAsset.id,
      zoneId: selectedAsset.zoneId,
    }, {
      onSuccess: () => {
        rememberAction(
          selectedAsset.id,
          '약 주기 요청 등록',
          `${selectedAsset.label} 약 주기 분사 명령을 IoT 제어 파이프라인에 전달했습니다.`,
          'accent',
        )
        setUiMessage(`${selectedAsset.label} 약 주기 분사 명령을 전달했습니다.`)
      },
    })
  }

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
        ? '전체 진단 중단 요청 중...'
        : '전체 진단 중단'
      : patrolMutation.isPending && activePatrolMission === null
        ? '전체 진단 요청 중...'
        : '전체 진단하기'
  const diagnosisPatrolButtonDisabled =
    diagnosisPatrolActive ? stopPatrolMutation.isPending : patrolActionDisabled
  const harvestPatrolButtonLabel =
    harvestPatrolActive
      ? activeStopRequest === 'patrol-harvest' && stopPatrolMutation.isPending
        ? '전체 수확 중단 요청 중...'
        : '전체 수확 중단'
      : patrolMutation.isPending && activePatrolMission === null
        ? '전체 수확 요청 중...'
        : '전체 수확하기'
  const harvestPatrolButtonDisabled =
    harvestPatrolActive ? stopPatrolMutation.isPending : patrolActionDisabled

  const handledSummaryItems = stableMapScene.assets
    .filter((asset) => asset.kind === 'plant' && asset.status === 'handled')
    .map((asset) => {
      const plant = plantLookup.get(asset.id)
      const actionRecord = actionRecords[asset.id]

      return {
        assetId: asset.id,
        plant: plant ?? null,
        actionRecord: actionRecord ?? null,
      }
    })
    .filter(({ plant, actionRecord }) => (
      (actionRecord?.label !== '수확 완료')
      && Boolean(plant?.latestDisplayLabel || plant?.latestLabel || actionRecord)
    ))
    .map(({ assetId, plant }) => ({
      key: `handled:${assetId}`,
      kind: 'handled' as const,
      plantNumber: plantNumberLabel(plant?.name ?? assetId, assetId),
      diseaseName: diseaseNameLabel(plant?.latestDisplayLabel ?? '', plant?.latestLabel ?? ''),
      treatmentName: treatmentNameLabel(plant?.recommendedAction ?? ''),
    }))
  const handledPlantIds = new Set(handledSummaryItems.map((item) => item.key.replace('handled:', '')))
  const attentionSummaryItems = stableMapScene.assets
    .filter((asset) => asset.kind === 'plant' && asset.status === 'attention' && !handledPlantIds.has(asset.id))
    .map((asset) => plantLookup.get(asset.id) ?? null)
    .filter((plant): plant is NonNullable<typeof plant> => plant !== null)
    .map((plant) => ({
      key: `attention:${plant.id}`,
      kind: 'attention' as const,
      plantNumber: plantNumberLabel(plant.name, plant.id),
      diseaseName: diseaseNameLabel(plant.latestDisplayLabel, plant.latestLabel),
    }))
  const targetPlantCount = stableMapScene.assets.filter((asset) => asset.kind === 'plant' && asset.status === 'target').length
  const summaryAlertItems = [
    {
      key: 'target-summary',
      kind: 'target' as const,
      countLabel: String(targetPlantCount).padStart(2, '0'),
    },
    ...handledSummaryItems,
    ...attentionSummaryItems,
  ]

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
            createGetSignal('예상 경로', mapSource('/robot/navigation-preview'), '/robot/navigation-preview'),
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
              이랑 라벨을 누르면 이동하고, 식물을 누르면 선택 후 진단하기로 관측 위치까지 이동합니다. 급수 헤드는 눌러서 작업 팝업만 엽니다.
            </p>
            <div className="farm-map-tip-row">
              <span className="chip">이랑 클릭 이동</span>
              <span className="chip">식물 선택 후 진단하기</span>
              <span className="chip">급수 헤드 선택 시 물 주기·약 주기</span>
            </div>
          </div>
          <div className="farm-weather-card">
            <span className="panel-kicker">날씨</span>
            <strong>{weatherSummary}</strong>
          </div>
        </div>

        <div className="map-board farm-map-board">
          <RobotFacilityMap
            activeCommandTarget={stableActiveCommandTarget}
            activeCommandTargetLabel="실행 중 목표"
            activeCommandTargetMarker={stableActiveDiagnoseMarkerPose}
            activeFinalCommandTarget={stableActiveDiagnoseFinalTarget}
            activeFinalCommandTargetLabel="최종 관측 목표"
            activeFinalCommandTargetMarker={stableActiveDiagnoseFinalMarkerPose}
            onSelectAsset={handleSelectAsset}
            onSelectGuide={handleGuideMove}
            pendingTarget={stablePendingDiagnosePose}
            pendingTargetLabel="선택한 관측 후보"
            pendingTargetMarker={stablePendingDiagnoseMarkerPose}
            pose={stableRobotPose}
            previewPath={stableMapPreviewPath}
            scene={stableMapScene}
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
        hideNote
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
        <section className="farm-section-card farm-section-card--summary">
          <div className="section-head">
            <div>
              <h3 className="list-title">알림창</h3>
            </div>
          </div>
          <div className="farm-result-list">
            {summaryAlertItems.map((item) => (
              <article className={`farm-result-item farm-result-item--${item.kind}`} key={item.key}>
                <div className="farm-result-icon farm-result-icon--tomato">
                  <span className={`farm-summary-tomato farm-summary-tomato--${item.kind}`}>
                    <span className="farm-summary-tomato__leaf" />
                    <span className="farm-summary-tomato__body" />
                  </span>
                </div>
                <p>
                  {item.kind === 'target' ? (
                    <>수확 가능 개체 총 {item.countLabel}개</>
                  ) : item.kind === 'handled' ? (
                    <>
                      <strong>{item.plantNumber}</strong> : {item.diseaseName} 발견, {item.treatmentName} 조치 완료
                    </>
                  ) : (
                    <>
                      <strong>{item.plantNumber}</strong> : {item.diseaseName} 발견
                    </>
                  )}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="farm-section-card farm-section-card--controls">
          <div className="farm-action-groups">
            <div className="farm-action-group">
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
            </div>
          </div>
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
            <div className="farm-plant-modal__content">
              <div className="farm-plant-modal__header">
                <h3 className="list-title" id="farm-plant-modal-title">
                  {plantModalTitle(selectedPlantDetail.name, selectedPlantDetail.id)}
                </h3>
                <button
                  aria-label="식물 팝업 닫기"
                  className="farm-plant-modal__close"
                  onClick={() => {
                    closeAssetModal()
                  }}
                  type="button"
                >
                  <AppIcon name="close" />
                </button>
              </div>

              <div className="farm-plant-modal__media">
                <MockupImage
                  alt={`${selectedPlantDetail.name} 확인 이미지`}
                  className="farm-plant-modal__image"
                  height="100%"
                  label={selectedPlantPreviewLabel}
                  src={selectedPlantPreviewImage || previewImageForAsset('plant', selectedPlantAsset.status)}
                />
              </div>

              <div className="farm-plant-modal__body">
                <p className="farm-plant-modal__media-note">{selectedPlantPreviewNote}</p>
                <div className="farm-plant-modal__actions">
                  <button
                    className="action-button"
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
            <div className="farm-plant-modal__content">
              <div className="farm-plant-modal__header">
                <h3 className="list-title" id="farm-sprinkler-modal-title">
                  {sprinklerModalTitle(selectedSprinklerAsset.label, selectedSprinklerAsset.id)}
                </h3>
                <button
                  aria-label="급수 팝업 닫기"
                  className="farm-plant-modal__close"
                  onClick={() => {
                    closeAssetModal()
                  }}
                  type="button"
                >
                  <AppIcon name="close" />
                </button>
              </div>
              <div className="farm-plant-modal__media">
                <MockupImage
                  alt={`${selectedSprinklerAsset.label} 확인 이미지`}
                  className="farm-plant-modal__image"
                  height="100%"
                  src={previewImageForAsset('sprinkler', selectedSprinklerAsset.status)}
                />
              </div>

              <div className="farm-plant-modal__body">
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
                    {wateringMutation.isPending ? '물 주는 중...' : '물 주기'}
                  </button>
                  <button
                    className="action-button action-button--soft"
                    disabled={nutrientMutation.isPending}
                    onClick={() => {
                      handleNutrient()
                      closeAssetModal()
                    }}
                    type="button"
                  >
                    {nutrientMutation.isPending ? '약 주는 중...' : '약 주기'}
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
