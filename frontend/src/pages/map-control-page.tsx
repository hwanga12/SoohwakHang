import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createGetSignal, createPostAction } from '@/app/dev-inspector'
import { AppIcon } from '@/components/app-icon'
import { DevSurface } from '@/components/dev-surface'
import { MetricCard } from '@/components/metric-card'
import { MockupImage } from '@/components/mockup-image'
import {
  RobotFacilityMap,
  summarizeSelectedAsset,
} from '@/components/robot-facility-map'
import {
  getLatestRobotCommandStatus,
  getRobotPageData,
  robotFallback,
  sendRobotControlAction,
  sendRobotNavigateCommand,
  sendRobotZoneMove,
  type RobotCommandStatus,
  type RobotTargetPose,
  type RobotZonePreset,
} from '@/lib/api/agribot'
import { resolveSemanticTargetId } from '@/lib/robot-map/farm-semantic-map'

const controlActions = [
  { id: 'pause', title: '일시 정지', icon: 'pause_circle', tone: 'soft' },
  { id: 'resume', title: '재개', icon: 'play_circle', tone: 'soft' },
  { id: 'home', title: '홈 포즈로 복귀', icon: 'home', tone: 'soft' },
  { id: 'emergency', title: '비상 정지', icon: 'emergency_home', tone: 'danger' },
] as const

type ControlActionId = (typeof controlActions)[number]['id']
type PendingControlRequest = {
  action: Exclude<ControlActionId, 'home'>
  baselineToken: string
  requestedAt: number
}

type NavigationTransitionFeedback = {
  previousCommandId: string | null
  targetSummary: string
}

type ControlCurrentState = 'idle' | 'paused' | 'emergency_stopped' | 'resumed'

type ControlSummary = {
  currentState: ControlCurrentState
  currentStateCode: 'idle' | 'paused' | 'emergency_stopped' | 'resumed'
  currentStateTone: 'table-tag--healthy' | 'table-tag--warning' | 'table-tag--danger'
  commandStageLabel: string
  commandStageTone: 'table-tag--healthy' | 'table-tag--warning' | 'table-tag--danger'
  title: string
  detail: string
  helper: string | null
  helperTone: 'control-feedback--warning' | 'control-feedback--danger' | 'control-feedback--healthy'
  movementLocked: boolean
  movementLockMessage: string | null
  latestCommandLabel: string
  activeActivityLabel: string
  resumeAvailabilityLabel: string
}

type CommandSummary = {
  tone: 'table-tag--healthy' | 'table-tag--warning' | 'table-tag--danger'
  title: string
  detail: string
  badgeLabel: string
}

const pauseCommandTypes = new Set(['pause_motion', 'pause_patrol'])
const resumeCommandTypes = new Set(['resume_motion', 'resume_patrol'])
const controlCommandTypes = new Set([
  'pause_motion',
  'pause_patrol',
  'resume_motion',
  'resume_patrol',
  'emergency_stop',
])

const controlCommandLabels: Record<string, string> = {
  emergency_stop: '비상 정지',
  pause_motion: '일시 정지',
  pause_patrol: '일시 정지',
  resume_motion: '재개',
  resume_patrol: '재개',
}

const activityLabels = {
  idle: '대기',
  manual_navigation: '수동 이동',
  patrol: '순찰',
} as const

function formatPose(pose: RobotTargetPose) {
  return `x ${pose.x.toFixed(2)} / y ${pose.y.toFixed(2)}`
}

function isNavigationCommandInProgress(status: RobotCommandStatus) {
  return (
    status.available
    && (status.requestedCommandType === 'navigate_to_pose'
      || status.requestedCommandType === 'move_to_zone'
      || status.requestedCommandType === 'return_home')
    && (status.status === 'pending' || status.status === 'running')
  )
}

function buildTransitionNotice(feedback: NavigationTransitionFeedback) {
  if (feedback.previousCommandId) {
    return `기존 ${feedback.previousCommandId} 이동을 중단하고 ${feedback.targetSummary} 목표로 전환 중입니다.`
  }

  return `${feedback.targetSummary} 목표로 전환 중입니다.`
}

function latestCommandToken(status: RobotCommandStatus) {
  return `${status.commandId ?? 'none'}:${status.status}:${status.updatedAt}`
}

function isPauseCommandType(commandType: string) {
  return pauseCommandTypes.has(commandType)
}

function isResumeCommandType(commandType: string) {
  return resumeCommandTypes.has(commandType)
}

function isControlCommandType(commandType: string) {
  return controlCommandTypes.has(commandType)
}

function latestRequestedCommandType(status: RobotCommandStatus) {
  return status.requestedCommandType || status.commandType
}

function actionMatchesCommandType(action: PendingControlRequest['action'], commandType: string) {
  if (action === 'pause') {
    return isPauseCommandType(commandType)
  }
  if (action === 'resume') {
    return isResumeCommandType(commandType)
  }
  return commandType === 'emergency_stop'
}

function deriveCurrentControlState(status: RobotCommandStatus): ControlCurrentState {
  if (status.controlState?.mode === 'emergency_stop') {
    return 'emergency_stopped'
  }
  if (status.controlState?.mode === 'paused') {
    return 'paused'
  }
  if (
    isResumeCommandType(latestRequestedCommandType(status))
    && status.status === 'succeeded'
    && status.result !== 'no_op'
  ) {
    return 'resumed'
  }
  return 'idle'
}

function hasObservedPendingControlRequest(
  status: RobotCommandStatus,
  pendingControlRequest: PendingControlRequest | null,
) {
  if (pendingControlRequest === null) {
    return false
  }

  if (pendingControlRequest.action === 'pause' && status.controlState?.mode === 'paused') {
    return true
  }
  if (pendingControlRequest.action === 'emergency' && status.controlState?.mode === 'emergency_stop') {
    return true
  }
  if (
    pendingControlRequest.action === 'resume'
    && status.controlState?.mode === 'normal'
    && (isResumeCommandType(latestRequestedCommandType(status)) || status.result === 'no_op')
  ) {
    return true
  }

  const commandType = latestRequestedCommandType(status)
  return (
    actionMatchesCommandType(pendingControlRequest.action, commandType)
    && latestCommandToken(status) !== pendingControlRequest.baselineToken
  )
}

function buildControlSummary(
  status: RobotCommandStatus,
  pendingControlRequest: PendingControlRequest | null,
): ControlSummary {
  const currentState = deriveCurrentControlState(status)
  const commandType = latestRequestedCommandType(status)
  const isLatestControlCommand = isControlCommandType(commandType)
  const activeActivityLabel = activityLabels[status.controlState?.activeActivity ?? 'idle']
  const latestCommandLabel = isLatestControlCommand
    ? `${controlCommandLabels[commandType] ?? commandType} · ${status.status}`
    : '최근 제어 명령 없음'
  const resumeAvailabilityLabel =
    status.controlState?.resumeAvailable
      ? status.controlState.resumeContextType === 'patrol'
        ? '가능 · 저장된 순찰'
        : '가능 · 저장된 수동 이동'
      : '없음'
  const pendingObserved = hasObservedPendingControlRequest(status, pendingControlRequest)
  const movementLockedByControlCommand =
    isLatestControlCommand
    && (status.status === 'pending' || status.status === 'running')
    && (commandType === 'emergency_stop' || isPauseCommandType(commandType))
  const movementLockedByPendingRequest =
    pendingControlRequest !== null
    && !pendingObserved
    && (pendingControlRequest.action === 'pause' || pendingControlRequest.action === 'emergency')
  const movementLocked =
    status.controlState?.mode === 'paused'
    || status.controlState?.mode === 'emergency_stop'
    || movementLockedByControlCommand
    || movementLockedByPendingRequest

  if (!status.available) {
    return {
      currentState,
      currentStateCode: 'idle',
      currentStateTone: 'table-tag--healthy',
      commandStageLabel: '대기',
      commandStageTone: 'table-tag--warning',
      title: '제어 상태 파일 대기',
      detail: 'executor가 control_state와 command status를 기록하기 전까지는 마지막 준비 데이터를 보여줍니다.',
      helper: null,
      helperTone: 'control-feedback--warning',
      movementLocked: false,
      movementLockMessage: null,
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  if (pendingControlRequest !== null && !pendingObserved) {
    const pendingTitle =
      pendingControlRequest.action === 'emergency'
        ? '비상 정지 명령 접수'
        : pendingControlRequest.action === 'pause'
          ? '일시정지 명령 접수'
          : '재개 명령 접수'
    const pendingDetail =
      pendingControlRequest.action === 'emergency'
        ? 'backend polling이 실제 비상 정지를 확인할 때까지 현재 상태는 마지막 authoritative 값으로 유지됩니다.'
        : pendingControlRequest.action === 'pause'
          ? 'backend polling이 실제 일시정지를 확인할 때까지 현재 상태는 마지막 authoritative 값으로 유지됩니다.'
          : 'backend polling이 실제 재개 또는 재개 불가를 확인할 때까지 현재 상태는 마지막 authoritative 값으로 유지됩니다.'

    return {
      currentState,
      currentStateCode: currentState,
      currentStateTone:
        currentState === 'emergency_stopped'
          ? 'table-tag--danger'
          : currentState === 'paused'
            ? 'table-tag--warning'
            : 'table-tag--healthy',
      commandStageLabel: '명령 접수',
      commandStageTone: 'table-tag--warning',
      title: pendingTitle,
      detail: pendingDetail,
      helper:
        pendingControlRequest.action === 'emergency'
          ? '비상 정지 확인 전까지는 홈 복귀와 새 이동 명령을 잠시 보류합니다.'
          : pendingControlRequest.action === 'pause'
            ? '일시정지 확인 전까지는 새 이동 명령을 잠시 보류합니다.'
            : null,
      helperTone: 'control-feedback--warning',
      movementLocked,
      movementLockMessage:
        pendingControlRequest.action === 'emergency'
          ? '비상 정지 확인 중에는 새 이동 명령을 보낼 수 없습니다.'
          : pendingControlRequest.action === 'pause'
            ? '일시정지 확인 중에는 새 이동 명령을 보낼 수 없습니다.'
            : null,
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  if (status.controlState?.mode === 'emergency_stop') {
    return {
      currentState,
      currentStateCode: 'emergency_stopped',
      currentStateTone: 'table-tag--danger',
      commandStageLabel: '실제 정지됨',
      commandStageTone: 'table-tag--danger',
      title: '실제 비상 정지됨',
      detail:
        status.controlState.message
        || status.message
        || '비상 정지가 유지되는 동안 backend가 새 이동 명령을 거부합니다.',
      helper: '비상 정지 상태에서는 홈 복귀와 새 이동 명령이 막혀 있습니다.',
      helperTone: 'control-feedback--danger',
      movementLocked: true,
      movementLockMessage: '비상 정지 상태에서는 새 이동 명령을 보낼 수 없습니다.',
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  if (status.controlState?.mode === 'paused') {
    return {
      currentState,
      currentStateCode: 'paused',
      currentStateTone: 'table-tag--warning',
      commandStageLabel: '실제 정지됨',
      commandStageTone: 'table-tag--warning',
      title: '실제 일시정지됨',
      detail:
        status.controlState.message
        || status.message
        || '재개 전까지 현재 주행과 순찰이 멈춘 상태입니다.',
      helper: '일시정지 상태에서는 재개 전까지 새 이동 명령이 막혀 있습니다.',
      helperTone: 'control-feedback--warning',
      movementLocked: true,
      movementLockMessage: '일시정지 상태에서는 새 이동 명령을 보낼 수 없습니다.',
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  if (isLatestControlCommand && status.status === 'running') {
    const title =
      commandType === 'emergency_stop'
        ? '비상 정지 적용 중'
        : isPauseCommandType(commandType)
          ? '일시정지 적용 중'
          : '재개 실행 중'

    return {
      currentState,
      currentStateCode: currentState,
      currentStateTone: currentState === 'resumed' ? 'table-tag--healthy' : 'table-tag--healthy',
      commandStageLabel: '실행 중',
      commandStageTone: 'table-tag--warning',
      title,
      detail: status.message || 'executor가 실제 제어 상태 전환을 진행 중입니다.',
      helper: null,
      helperTone: 'control-feedback--warning',
      movementLocked,
      movementLockMessage:
        commandType === 'emergency_stop'
          ? '비상 정지 적용 중에는 새 이동 명령을 보낼 수 없습니다.'
          : isPauseCommandType(commandType)
            ? '일시정지 적용 중에는 새 이동 명령을 보낼 수 없습니다.'
            : null,
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  if (isLatestControlCommand && status.status === 'pending') {
    return {
      currentState,
      currentStateCode: currentState,
      currentStateTone: currentState === 'resumed' ? 'table-tag--healthy' : 'table-tag--healthy',
      commandStageLabel: '명령 접수',
      commandStageTone: 'table-tag--warning',
      title: '제어 명령 접수됨',
      detail: status.message || 'executor가 제어 상태 전환 명령을 읽는 중입니다.',
      helper: null,
      helperTone: 'control-feedback--warning',
      movementLocked,
      movementLockMessage:
        commandType === 'emergency_stop'
          ? '비상 정지 명령 확인 중에는 새 이동 명령을 보낼 수 없습니다.'
          : isPauseCommandType(commandType)
            ? '일시정지 명령 확인 중에는 새 이동 명령을 보낼 수 없습니다.'
            : null,
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  if (isResumeCommandType(commandType) && status.status === 'succeeded' && status.result === 'no_op') {
    return {
      currentState,
      currentStateCode: 'idle',
      currentStateTone: 'table-tag--healthy',
      commandStageLabel: '재개 불가',
      commandStageTone: 'table-tag--warning',
      title: '재개할 작업이 없습니다',
      detail:
        status.message
        || '저장된 재개 문맥이 없어 제어 latch만 해제했거나 추가로 재개할 동작이 없습니다.',
      helper: '현재 backend 기준으로 이어서 실행할 작업이 없습니다.',
      helperTone: 'control-feedback--warning',
      movementLocked: false,
      movementLockMessage: null,
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  if (isResumeCommandType(commandType) && status.status === 'succeeded') {
    return {
      currentState,
      currentStateCode: 'resumed',
      currentStateTone: 'table-tag--healthy',
      commandStageLabel: '재개됨',
      commandStageTone: 'table-tag--healthy',
      title: '재개됨',
      detail: status.message || '저장된 순찰 또는 수동 이동 문맥이 다시 시작되었습니다.',
      helper: null,
      helperTone: 'control-feedback--healthy',
      movementLocked: false,
      movementLockMessage: null,
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  if (isLatestControlCommand && status.status === 'failed') {
    const title =
      commandType === 'emergency_stop'
        ? '비상 정지 실패'
        : isPauseCommandType(commandType)
          ? '일시정지 실패'
          : '재개 실패'

    return {
      currentState,
      currentStateCode: currentState,
      currentStateTone: currentState === 'resumed' ? 'table-tag--healthy' : 'table-tag--healthy',
      commandStageLabel: '실패',
      commandStageTone: 'table-tag--danger',
      title,
      detail: status.message || 'backend 또는 executor가 제어 명령 실패를 기록했습니다.',
      helper: status.error ? `실패 코드: ${status.error}` : null,
      helperTone: 'control-feedback--danger',
      movementLocked: false,
      movementLockMessage: null,
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  if (isLatestControlCommand && status.status === 'canceled') {
    return {
      currentState,
      currentStateCode: currentState,
      currentStateTone: currentState === 'resumed' ? 'table-tag--healthy' : 'table-tag--healthy',
      commandStageLabel: '취소됨',
      commandStageTone: 'table-tag--warning',
      title: '제어 명령 취소됨',
      detail: status.message || '대기 중이던 제어 명령이 취소되었습니다.',
      helper: null,
      helperTone: 'control-feedback--warning',
      movementLocked: false,
      movementLockMessage: null,
      latestCommandLabel,
      activeActivityLabel,
      resumeAvailabilityLabel,
    }
  }

  return {
    currentState,
    currentStateCode: currentState,
    currentStateTone: currentState === 'resumed' ? 'table-tag--healthy' : 'table-tag--healthy',
    commandStageLabel: currentState === 'resumed' ? '재개됨' : '대기',
    commandStageTone: currentState === 'resumed' ? 'table-tag--healthy' : 'table-tag--healthy',
    title: currentState === 'resumed' ? '재개 후 정상 대기' : '제어 대기',
    detail:
      currentState === 'resumed'
        ? '제어 latch가 해제되어 새 이동 또는 후속 시연을 진행할 수 있습니다.'
        : status.controlState?.message
          || (status.controlState?.activeActivity === 'patrol'
            ? '현재 순찰 문맥을 그대로 유지 중입니다.'
            : status.controlState?.activeActivity === 'manual_navigation'
              ? '현재 수동 이동 문맥을 그대로 유지 중입니다.'
              : '제어 latch 없이 대기 중입니다.'),
    helper:
      status.controlState?.mode === 'normal'
      && !status.controlState?.resumeAvailable
      && currentState !== 'resumed'
        ? '재개 버튼은 저장된 문맥이 있거나 제어 latch가 걸린 경우에만 활성화됩니다.'
        : null,
    helperTone: 'control-feedback--healthy',
    movementLocked: false,
    movementLockMessage: null,
    latestCommandLabel,
    activeActivityLabel,
    resumeAvailabilityLabel,
  }
}

function commandStatusCopy(
  status: RobotCommandStatus,
  isTracked: boolean,
  transitionFeedback: NavigationTransitionFeedback | null,
  controlSummary: ControlSummary,
): CommandSummary {
  if (!status.available) {
    return {
      tone: 'table-tag--warning',
      title: '상태 파일 대기',
      detail: 'executor가 첫 상태 파일을 쓰기 전까지는 이 카드에 최신 진행 상황이 나타납니다.',
      badgeLabel: '대기',
    }
  }

  if (controlSummary.movementLocked) {
    return {
      tone:
        controlSummary.currentState === 'emergency_stopped'
          ? 'table-tag--danger'
          : 'table-tag--warning',
      title:
        controlSummary.currentState === 'emergency_stopped'
          ? '새 이동 명령 차단됨'
          : '새 이동 명령 일시 차단됨',
      detail:
        controlSummary.movementLockMessage
        || '현재 제어 상태가 풀리기 전까지는 새 이동 명령을 보낼 수 없습니다.',
      badgeLabel: controlSummary.currentStateCode,
    }
  }

  if (transitionFeedback && !isTracked) {
    return {
      tone: 'table-tag--warning',
      title: '새 목표 전환 요청',
      detail: buildTransitionNotice(transitionFeedback),
      badgeLabel: '전환 중',
    }
  }

  if (!isTracked) {
    return {
      tone: 'table-tag--healthy',
      title: '최근 명령 대기',
      detail: '방금 요청한 명령을 보내면 이 카드가 pending/running/succeeded/failed 상태로 갱신됩니다.',
      badgeLabel: '대기',
    }
  }

  switch (status.status) {
    case 'pending':
      return {
        tone: 'table-tag--warning',
        title: transitionFeedback ? '새 목표 전환 준비' : '명령 접수됨',
        detail:
          transitionFeedback
            ? buildTransitionNotice(transitionFeedback)
            : status.message || 'executor가 파일을 읽고 실제 주행 요청으로 넘기는 중입니다.',
        badgeLabel: 'pending',
      }
    case 'running':
      return {
        tone: 'table-tag--healthy',
        title: transitionFeedback ? '새 목표로 전환 중' : '이동 실행 중',
        detail:
          transitionFeedback
            ? buildTransitionNotice(transitionFeedback)
            : status.message || '로봇이 목표 pose 또는 대표 구역 좌표로 이동 중입니다.',
        badgeLabel: 'running',
      }
    case 'succeeded':
      return {
        tone: 'table-tag--healthy',
        title: '명령 완료',
        detail: '최근 요청이 성공적으로 끝났습니다. 다음 시연 입력을 진행하면 됩니다.',
        badgeLabel: 'succeeded',
      }
    case 'failed':
      return {
        tone: 'table-tag--danger',
        title: '명령 실패',
        detail: status.message || 'backend 또는 executor가 실패를 기록했습니다.',
        badgeLabel: 'failed',
      }
    case 'canceled':
      return {
        tone: 'table-tag--warning',
        title: '명령 취소',
        detail: status.message || '명령이 취소되었거나 중단되었습니다.',
        badgeLabel: 'canceled',
      }
    default:
      return {
        tone: 'table-tag--healthy',
        title: '명령 대기',
        detail: status.message || '새로운 이동 요청을 기다리는 상태입니다.',
        badgeLabel: 'idle',
      }
  }
}

export function MapControlPage() {
  const queryClient = useQueryClient()
  const [mapZoom, setMapZoom] = useState(1)
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [pendingTarget, setPendingTarget] = useState<RobotTargetPose | null>(null)
  const [activeCommandTarget, setActiveCommandTarget] = useState<RobotTargetPose | null>(null)
  const [lastCommandId, setLastCommandId] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [observedCommandState, setObservedCommandState] = useState<string | null>(null)
  const [transitionFeedback, setTransitionFeedback] = useState<NavigationTransitionFeedback | null>(null)
  const [pendingControlRequest, setPendingControlRequest] = useState<PendingControlRequest | null>(null)

  const robotQuery = useQuery({
    queryKey: ['page', 'robot'],
    queryFn: getRobotPageData,
    initialData: robotFallback,
    refetchInterval: 10_000,
  })
  const latestCommandStatusQuery = useQuery({
    queryKey: ['robot', 'command-status'],
    queryFn: getLatestRobotCommandStatus,
    initialData: robotFallback.latestCommandStatus,
    refetchInterval: 2_000,
  })
  const controlMutation = useMutation({
    mutationFn: sendRobotControlAction,
    onSuccess: async (_message, action) => {
      if (action === 'home') {
        setNotice('홈 복귀 명령을 접수했습니다. 상태 카드에서 진행 상황을 확인하세요.')
      } else {
        setPendingControlRequest({
          action,
          baselineToken: latestCommandToken(latestCommandStatus),
          requestedAt: Date.now(),
        })
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
        queryClient.invalidateQueries({ queryKey: ['robot', 'command-status'] }),
      ])
    },
    onError: () => {
      setPendingControlRequest(null)
    },
  })
  const zoneMoveMutation = useMutation({
    mutationFn: async (preset: RobotZonePreset) => {
      const response = await sendRobotZoneMove(preset.id)
      return { preset, response }
    },
    onSuccess: async ({ preset, response }) => {
      const nextTarget = response.targetPose ?? preset.representativePose
      const shouldAnnounceTransition =
        response.preemptCurrentNavigation && isNavigationCommandInProgress(latestCommandStatus)
      const nextTransitionFeedback = shouldAnnounceTransition
        ? {
            previousCommandId: latestCommandStatus.commandId,
            targetSummary: `${preset.name} (${formatPose(nextTarget)})`,
          }
        : null

      setLastCommandId(response.commandId)
      setObservedCommandState(null)
      setActiveCommandTarget(nextTarget)
      setPendingTarget(null)
      setTransitionFeedback(nextTransitionFeedback)
      setNotice(
        nextTransitionFeedback
          ? `${buildTransitionNotice(nextTransitionFeedback)} 상태 카드에서 새 목표 전환 진행 상황을 확인하세요.`
          : `${preset.name} 이동 요청을 보냈습니다. 상태 카드에서 진행 상황을 확인하세요.`,
      )
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
        queryClient.invalidateQueries({ queryKey: ['robot', 'command-status'] }),
      ])
    },
    onError: (error: Error) => {
      setNotice(error.message)
    },
  })
  const navigateMutation = useMutation({
    mutationFn: sendRobotNavigateCommand,
    onSuccess: async (response) => {
      const nextTarget = response.targetPose
      const shouldAnnounceTransition =
        response.preemptCurrentNavigation && isNavigationCommandInProgress(latestCommandStatus)
      const nextTransitionFeedback =
        shouldAnnounceTransition && nextTarget
          ? {
              previousCommandId: latestCommandStatus.commandId,
              targetSummary: `좌표 ${formatPose(nextTarget)}`,
            }
          : null

      setLastCommandId(response.commandId)
      setObservedCommandState(null)
      if (nextTarget) {
        setActiveCommandTarget(nextTarget)
      }
      setPendingTarget(null)
      setTransitionFeedback(nextTransitionFeedback)
      setNotice(
        nextTransitionFeedback
          ? `${buildTransitionNotice(nextTransitionFeedback)} 상태 카드가 pending/running으로 바뀌는지 확인하세요.`
          : '클릭한 좌표로 이동 요청을 보냈습니다. 상태 카드가 pending/running으로 바뀌는지 확인하세요.',
      )
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['page', 'robot'] }),
        queryClient.invalidateQueries({ queryKey: ['robot', 'command-status'] }),
      ])
    },
    onError: (error: Error) => {
      setNotice(error.message)
    },
  })

  const page = robotQuery.data
  const latestCommandStatus = latestCommandStatusQuery.data ?? page.latestCommandStatus
  const querySource = (path: string) =>
    page.debug.querySources[path]
    ?? (path === '/robot/commands/latest' ? latestCommandStatus.source : 'fallback')
  const targetAssetId = resolveSemanticTargetId(page.targetLabel)
  const selectedAsset = useMemo(
    () => page.scene.assets.find((asset) => asset.id === selectedAssetId) ?? null,
    [page.scene.assets, selectedAssetId],
  )
  const selectedSummary = summarizeSelectedAsset(selectedAsset)
  const controlRequestObserved = hasObservedPendingControlRequest(latestCommandStatus, pendingControlRequest)
  const controlSummary = buildControlSummary(latestCommandStatus, pendingControlRequest)
  const controlActionPending = controlMutation.isPending
  const movementActionPending = zoneMoveMutation.isPending || navigateMutation.isPending
  const movementCommandBlocked = controlSummary.movementLocked
  const movementCommandBlockMessage =
    controlSummary.movementLockMessage
    || '현재 제어 상태가 해제되기 전까지 새 이동 명령을 보낼 수 없습니다.'
  const movementButtonsDisabled = movementActionPending || controlActionPending || movementCommandBlocked
  const controlFeedbackMessage = controlMutation.isError
    ? controlMutation.error.message
    : controlSummary.helper
  const controlFeedbackTone = controlMutation.isError
    ? 'control-feedback--danger'
    : controlSummary.helperTone
  const missionStateBadgeLabel =
    controlSummary.currentState === 'emergency_stopped'
      ? '비상 정지'
      : controlSummary.currentState === 'paused'
        ? '일시정지'
        : controlSummary.currentState === 'resumed'
          ? '재개됨'
          : page.missionState
  const missionStateBadgeTone =
    controlSummary.currentState === 'emergency_stopped'
      ? 'table-tag--danger'
      : controlSummary.currentState === 'paused'
        ? 'table-tag--warning'
        : 'table-tag--healthy'
  const trackedCommand = lastCommandId !== null && latestCommandStatus.commandId === lastCommandId
  const commandSummary = commandStatusCopy(
    latestCommandStatus,
    trackedCommand,
    transitionFeedback,
    controlSummary,
  )

  const controlActionDisabledReason = (actionId: ControlActionId) => {
    if (actionId === 'emergency') {
      if (controlActionPending) {
        return '제어 명령을 전송 중입니다.'
      }
      if (
        controlSummary.currentState === 'emergency_stopped'
        || (pendingControlRequest?.action === 'emergency' && !controlRequestObserved)
      ) {
        return '이미 비상 정지 상태이거나 실제 정지 확인 중입니다.'
      }
      return null
    }

    if (actionId === 'pause') {
      if (controlActionPending) {
        return '제어 명령을 전송 중입니다.'
      }
      if (controlSummary.currentState === 'emergency_stopped') {
        return '비상 정지 해제 후 일시정지를 사용할 수 있습니다.'
      }
      if (
        controlSummary.currentState === 'paused'
        || (pendingControlRequest?.action === 'pause' && !controlRequestObserved)
      ) {
        return '이미 일시정지 상태이거나 실제 정지 확인 중입니다.'
      }
      if ((latestCommandStatus.controlState?.activeActivity ?? 'idle') === 'idle') {
        return '일시정지할 이동 또는 순찰이 없습니다.'
      }
      return null
    }

    if (actionId === 'resume') {
      if (controlActionPending) {
        return '제어 명령을 전송 중입니다.'
      }
      if (pendingControlRequest?.action === 'resume' && !controlRequestObserved) {
        return '재개 상태를 확인 중입니다.'
      }
      if (
        latestCommandStatus.controlState?.mode === 'normal'
        && !latestCommandStatus.controlState?.resumeAvailable
      ) {
        return '재개할 작업이 없습니다.'
      }
      return null
    }

    if (controlActionPending || movementActionPending) {
      return '다른 이동 또는 제어 요청을 처리 중입니다.'
    }
    if (movementCommandBlocked) {
      return movementCommandBlockMessage
    }
    return null
  }

  useEffect(() => {
    if (!selectedAssetId && targetAssetId) {
      setSelectedAssetId(targetAssetId)
      return
    }

    if (!selectedAssetId && page.scene.assets[0]) {
      setSelectedAssetId(page.scene.assets[0].id)
    }
  }, [page.scene.assets, selectedAssetId, targetAssetId])

  useEffect(() => {
    if (!trackedCommand) {
      return
    }

    const stateToken = `${latestCommandStatus.commandId}:${latestCommandStatus.status}`
    if (observedCommandState === stateToken) {
      return
    }

    setObservedCommandState(stateToken)
    if (latestCommandStatus.status === 'succeeded') {
      if (transitionFeedback) {
        setNotice(`${transitionFeedback.targetSummary} 기준 새 목표 전환 이동이 완료되었습니다.`)
        setTransitionFeedback(null)
      } else {
        setNotice('최근 이동 요청이 성공적으로 완료되었습니다.')
      }
      return
    }
    if (latestCommandStatus.status === 'failed') {
      setTransitionFeedback(null)
      setNotice(latestCommandStatus.message || '최근 이동 요청이 실패했습니다.')
      return
    }
    if (latestCommandStatus.status === 'canceled') {
      setTransitionFeedback(null)
      setNotice(latestCommandStatus.message || '최근 이동 요청이 취소되었습니다.')
    }
  }, [latestCommandStatus, observedCommandState, trackedCommand, transitionFeedback])

  useEffect(() => {
    if (pendingControlRequest !== null && controlRequestObserved) {
      setPendingControlRequest(null)
    }
  }, [controlRequestObserved, pendingControlRequest])

  useEffect(() => {
    if (!movementCommandBlocked || pendingTarget === null) {
      return
    }

    setPendingTarget(null)
    setNotice(movementCommandBlockMessage)
  }, [movementCommandBlockMessage, movementCommandBlocked, pendingTarget])

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
          contract={{
            title: '실제 지도와 목표 지정 보드',
            queries: [
              createGetSignal('로봇 상태', querySource('/robot/status'), '/robot/status'),
              createGetSignal('로봇 위치', querySource('/robot/pose'), '/robot/pose'),
              createGetSignal('정적 지도', querySource('/robot/map'), '/robot/map'),
              createGetSignal('지도 레이어', querySource('/robot/map/layers'), '/robot/map/layers'),
              createGetSignal('명령 상태', querySource('/robot/commands/latest'), '/robot/commands/latest'),
            ],
            actions: [
              createPostAction('좌표 이동', ['/robot/commands']),
              createPostAction('구역 이동', ['/robot/commands']),
            ],
          }}
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

          <RobotFacilityMap
            activeCommandTarget={activeCommandTarget}
            map={page.map}
            onMapClickFeedback={setNotice}
            onSelectAsset={setSelectedAssetId}
            onSelectMapTarget={(target) => {
              if (movementCommandBlocked) {
                setNotice(movementCommandBlockMessage)
                return
              }
              setPendingTarget(target)
              setNotice(`선택 좌표 ${formatPose(target)}. 아래 확인 버튼으로 이동 명령을 보낼 수 있습니다.`)
            }}
            pendingTarget={pendingTarget}
            pose={page.robotPose}
            scene={page.scene}
            selectedAssetId={selectedAssetId}
            targetAssetId={targetAssetId}
            zoom={mapZoom}
          />

          <div className="map-controls">
            <button
              className="icon-button"
              onClick={() => {
                setMapZoom((current) => Math.min(current + 0.1, 1.8))
              }}
              type="button"
            >
              <AppIcon name="add" />
            </button>
            <button
              className="icon-button"
              onClick={() => {
                setMapZoom((current) => Math.max(current - 0.1, 0.8))
              }}
              type="button"
            >
              <AppIcon name="remove" />
            </button>
            <button
              className="icon-button icon-button--active"
              onClick={() => {
                setMapZoom(1)
                setPendingTarget(null)
                if (targetAssetId) {
                  setSelectedAssetId(targetAssetId)
                }
              }}
              type="button"
            >
              <AppIcon filled name="my_location" />
            </button>
          </div>

          {pendingTarget ? (
            <div className="map-target-sheet">
              <div>
                <span className="panel-kicker">클릭 이동 확인</span>
                <strong>{formatPose(pendingTarget)}</strong>
                <p>빈 지도 영역을 눌러 잡은 목표입니다. 확인을 누르면 `navigate_to_pose`로 전송됩니다.</p>
              </div>
              <div className="map-target-sheet__actions">
                <button
                  className="action-button"
                  disabled={movementButtonsDisabled}
                  onClick={() => {
                    navigateMutation.mutate(pendingTarget)
                  }}
                  type="button"
                >
                  이 좌표로 이동
                </button>
                <button
                  className="action-button action-button--ghost"
                  onClick={() => {
                    setPendingTarget(null)
                    setNotice('선택한 이동 목표를 취소했습니다.')
                  }}
                  type="button"
                >
                  취소
                </button>
              </div>
            </div>
          ) : null}
        </DevSurface>

        <aside className="map-sidebar">
          <DevSurface
            as="article"
            className="panel"
            contract={{
              title: '미션 진행률',
              queries: [
                createGetSignal('로봇 상태', querySource('/robot/status'), '/robot/status'),
                createGetSignal('로봇 위치', querySource('/robot/pose'), '/robot/pose'),
              ],
            }}
          >
            <div className="section-head">
              <div>
                <span className="section-eyebrow">미션 진행</span>
                <h3 className="section-title">{page.progressPct}%</h3>
                <p className="section-description">{page.eta}</p>
              </div>
              <span className={`table-tag ${missionStateBadgeTone}`}>{missionStateBadgeLabel}</span>
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
            contract={{
              title: '이동 명령 상태',
              queries: [
                createGetSignal('명령 상태', querySource('/robot/commands/latest'), '/robot/commands/latest'),
              ],
            }}
          >
            <div className="section-head">
              <div>
                <span className="section-eyebrow">클릭 이동 피드백</span>
                <h3 className="section-title">{commandSummary.title}</h3>
                <p className="section-description">{commandSummary.detail}</p>
              </div>
              <span className={`table-tag ${commandSummary.tone}`}>{commandSummary.badgeLabel}</span>
            </div>
            <div className="detail-grid">
              <article className="detail-card">
                <span className="detail-label">최근 command_id</span>
                <strong className="detail-value">{latestCommandStatus.commandId ?? '대기'}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">요청 타입</span>
                <strong className="detail-value">
                  {latestCommandStatus.requestedCommandType || '아직 없음'}
                </strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">대상 구역</span>
                <strong className="detail-value">{latestCommandStatus.targetZoneId ?? '좌표 직접 지정'}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">최종 갱신</span>
                <strong className="detail-value">{latestCommandStatus.updatedAt || '대기 중'}</strong>
              </article>
              {activeCommandTarget ? (
                <article className="detail-card">
                  <span className="detail-label">최근 목표 좌표</span>
                  <strong className="detail-value">{formatPose(activeCommandTarget)}</strong>
                </article>
              ) : null}
            </div>
            {transitionFeedback && !movementCommandBlocked ? (
              <div className="command-transition-note">
                <span className="panel-kicker">새 목적지 우선 적용</span>
                <strong>{transitionFeedback.targetSummary}</strong>
                <p>{buildTransitionNotice(transitionFeedback)}</p>
              </div>
            ) : null}
            {notice ? <p className="muted">{notice}</p> : null}
          </DevSurface>

          <DevSurface
            as="article"
            className="panel"
            contract={{
              title: '지도 자산 레이어',
              queries: [
                createGetSignal('지도 레이어', querySource('/robot/map/layers'), '/robot/map/layers'),
                createGetSignal('구역 목록', querySource('/zones'), '/zones'),
              ],
            }}
          >
            <div className="section-head">
              <div>
                <span className="section-eyebrow">시설 레이어</span>
                <h3 className="section-title">{selectedSummary.title}</h3>
                <p className="section-description">{selectedSummary.subtitle}</p>
              </div>
            </div>
            <div className="chip-row">
              {selectedSummary.chips.map((chip) => (
                <span className="chip chip--active" key={chip}>
                  {chip}
                </span>
              ))}
            </div>
            <div className="detail-grid">
              <article className="detail-card">
                <span className="detail-label">식물 레이어</span>
                <strong className="detail-value">
                  {page.scene.assets.filter((asset) => asset.kind === 'plant').length}주 배치
                </strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">급수 포인트</span>
                <strong className="detail-value">
                  {page.scene.assets.filter((asset) => asset.kind === 'sprinkler').length}개 헤드
                </strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">현재 타깃</span>
                <strong className="detail-value">{targetAssetId ?? '선택 대기'}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">렌더링 기준</span>
                <strong className="detail-value">
                  {page.map.imageUrl ? 'robot/map + robot/map/raw' : 'semantic fallback'}
                </strong>
              </article>
            </div>
          </DevSurface>

          <DevSurface
            as="article"
            className="panel"
            contract={{
              title: '로봇 제어 센터',
              queries: [
                createGetSignal('로봇 상태', querySource('/robot/status'), '/robot/status'),
              ],
              actions: [
                createPostAction('정지 요청', ['/missions/patrol/stop', '/robot/commands'], 'any'),
                createPostAction('재개 요청', ['/robot/commands']),
                createPostAction('복귀 요청', ['/missions/return-home', '/robot/commands'], 'any'),
                createPostAction('비상 정지', ['/robot/commands']),
              ],
            }}
          >
            <div className="section-head">
              <div>
                <span className="section-eyebrow">로봇 제어</span>
                <h3 className="section-title">기본 제어 버튼</h3>
                <p className="section-description">
                  이 카드는 `/robot/commands/latest` polling 결과를 기준으로 현재 제어 상태와 최근 제어 명령 단계를 함께 보여줍니다.
                </p>
              </div>
              <span className="table-tag table-tag--warning">
                {page.source === 'live' ? '실 API' : '준비 데이터'}
              </span>
            </div>
            <div
              className={`control-status-banner ${
                controlSummary.currentState === 'emergency_stopped'
                  ? 'control-status-banner--danger'
                  : controlSummary.currentState === 'paused'
                    ? 'control-status-banner--warning'
                    : 'control-status-banner--healthy'
              }`}
            >
              <div>
                <span className="panel-kicker">현재 제어 상태</span>
                <strong>{controlSummary.title}</strong>
                <p>{controlSummary.detail}</p>
              </div>
              <div className="control-status-banner__chips">
                <span className={`table-tag ${controlSummary.currentStateTone}`}>
                  {controlSummary.currentStateCode}
                </span>
                <span className={`table-tag ${controlSummary.commandStageTone}`}>
                  {controlSummary.commandStageLabel}
                </span>
              </div>
            </div>
            <div className="detail-grid">
              <article className="detail-card">
                <span className="detail-label">현재 상태</span>
                <strong className="detail-value">{controlSummary.currentStateCode}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">최근 제어 명령</span>
                <strong className="detail-value">{controlSummary.latestCommandLabel}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">활성 활동</span>
                <strong className="detail-value">{controlSummary.activeActivityLabel}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">재개 가능 문맥</span>
                <strong className="detail-value">{controlSummary.resumeAvailabilityLabel}</strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">이동 차단</span>
                <strong className="detail-value">
                  {movementCommandBlocked ? '차단됨' : '허용됨'}
                </strong>
              </article>
              <article className="detail-card">
                <span className="detail-label">최종 갱신</span>
                <strong className="detail-value">{latestCommandStatus.updatedAt || '대기 중'}</strong>
              </article>
            </div>
            {controlFeedbackMessage ? (
              <p className={`control-feedback ${controlFeedbackTone}`}>{controlFeedbackMessage}</p>
            ) : null}
            <div className="control-tile-grid">
              {controlActions.map((action) => (
                <button
                  className={`control-tile${action.tone === 'danger' ? ' control-tile--danger' : ''}`}
                  disabled={controlActionDisabledReason(action.id) !== null}
                  key={action.title}
                  onClick={() => {
                    controlMutation.mutate(action.id)
                  }}
                  title={controlActionDisabledReason(action.id) ?? action.title}
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
          </DevSurface>

          <DevSurface
            as="article"
            className="panel"
            contract={{
              title: '빠른 구역 이동',
              queries: [
                createGetSignal('구역 목록', querySource('/zones'), '/zones'),
              ],
              actions: [
                createPostAction('구역 이동', ['/robot/commands']),
              ],
            }}
          >
            <div className="section-head">
              <div>
                <span className="section-eyebrow">구역 이동</span>
                <h3 className="section-title">빠른 구역 이동</h3>
                <p className="section-description">
                  `/zones`의 representative_pose를 그대로 사용합니다. 초보 시연자는 여기 버튼만 눌러도 됩니다.
                </p>
              </div>
            </div>
            <div className="preset-grid">
              {page.zonePresets.map((preset) => (
                <button
                  className="preset-button"
                  disabled={movementButtonsDisabled}
                  key={preset.id}
                  onClick={() => {
                    if (movementCommandBlocked) {
                      setNotice(movementCommandBlockMessage)
                      return
                    }
                    zoneMoveMutation.mutate(preset)
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
                  <strong className="preset-button__pose">{formatPose(preset.representativePose)}</strong>
                </button>
              ))}
            </div>
          </DevSurface>

          <DevSurface
            as="article"
            className="panel"
            contract={{
              title: '이벤트 로그',
              queries: [
                createGetSignal('로봇 상태', querySource('/robot/status'), '/robot/status'),
              ],
            }}
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
