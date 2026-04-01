/*
 * 이 모듈은 작물 단위 이동 계획을 만든다.
 */
import type { RobotObservationGoalCandidate, RobotTargetPose } from '@/lib/api/agribot'
import {
  resolvePlantObservationSelection,
  type PlantObservationSelectionStrategy,
} from '@/lib/robot-map/approach-pose'
import type { SemanticScene } from '@/lib/robot-map/farm-semantic-map'

const FINAL_OBSERVATION_STAGE_TRIGGER_DISTANCE_M = 0.08

/**
 * 작물 주행 step phase 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type PlantNavigationStepPhase = 'route_anchor' | 'final_observation'

/**
 * 작물 주행 step 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type PlantNavigationStep = {
  phase: PlantNavigationStepPhase
  pose: RobotTargetPose
  displayPose: RobotTargetPose
}

/**
 * 작물 주행 plan 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type PlantNavigationPlan = {
  routeAnchorPose: RobotTargetPose
  routeAnchorDisplayPose: RobotTargetPose
  finalObservationPose: RobotTargetPose
  finalObservationDisplayPose: RobotTargetPose
  inspectionPose: RobotTargetPose
  inspectionDisplayPose: RobotTargetPose
  inspectWaypointId: string | null
  inspectWaypointIds: string[]
  inspectWaypointName: string | null
  observationCandidates: RobotObservationGoalCandidate[]
  steps: PlantNavigationStep[]
}

/**
 * 작물 주행 plan options 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type PlantNavigationPlanOptions = {
  selectionStrategy?: PlantObservationSelectionStrategy
  selectedCandidateOnly?: boolean
}

function poseDistance(left: RobotTargetPose, right: RobotTargetPose) {
  return Math.hypot(left.x - right.x, left.y - right.y)
}

/**
 * 작물 점검 주행 plan을 조합해 만드는 함수다.
 */
export function buildPlantInspectionNavigationPlan(
  plantId: string,
  preferredScene: SemanticScene,
  fallbackScene: SemanticScene,
  fallbackPositionLabel: string,
  currentPose: { x: number, y: number } | null,
  options?: PlantNavigationPlanOptions,
): PlantNavigationPlan | null {
  const selectionStrategy = options?.selectionStrategy ?? 'nearest'
  const observationSelection = resolvePlantObservationSelection(
    plantId,
    preferredScene,
    fallbackScene,
    fallbackPositionLabel,
    currentPose,
    selectionStrategy,
  )

  if (!observationSelection) {
    return null
  }

  const routeAnchorPose = observationSelection.navigationPose
  const routeAnchorDisplayPose = observationSelection.navigationPose
  const finalObservationPose = observationSelection.approachPose ?? observationSelection.displayPose
  const finalObservationDisplayPose = observationSelection.displayPose
  const needsTwoStageApproach =
    poseDistance(routeAnchorPose, finalObservationPose) > FINAL_OBSERVATION_STAGE_TRIGGER_DISTANCE_M
  const selectedCandidate =
    observationSelection.inspectWaypointId !== null
      ? observationSelection.observationCandidates.find(
          (candidate) => candidate.inspectWaypointId === observationSelection.inspectWaypointId,
        ) ?? null
      : null
  const exportedObservationCandidates =
    options?.selectedCandidateOnly && selectedCandidate
      ? [selectedCandidate]
      : observationSelection.observationCandidates
  const exportedInspectWaypointIds =
    options?.selectedCandidateOnly && observationSelection.inspectWaypointId
      ? [observationSelection.inspectWaypointId]
      : observationSelection.inspectWaypointIds

  return {
    routeAnchorPose,
    routeAnchorDisplayPose,
    finalObservationPose,
    finalObservationDisplayPose,
    inspectionPose: finalObservationPose,
    inspectionDisplayPose: finalObservationDisplayPose,
    inspectWaypointId: observationSelection.inspectWaypointId,
    inspectWaypointIds: exportedInspectWaypointIds,
    inspectWaypointName: observationSelection.inspectWaypointName,
    observationCandidates: exportedObservationCandidates,
    steps: needsTwoStageApproach
      ? [
          {
            phase: 'route_anchor',
            pose: routeAnchorPose,
            displayPose: routeAnchorDisplayPose,
          },
          {
            phase: 'final_observation',
            pose: finalObservationPose,
            displayPose: finalObservationDisplayPose,
          },
        ]
      : [
          {
            phase: 'final_observation',
            pose: finalObservationPose,
            displayPose: finalObservationDisplayPose,
          },
        ],
  }
}
