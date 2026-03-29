import type { RobotTargetPose } from '@/lib/api/agribot'
import { resolvePlantObservationSelection } from '@/lib/robot-map/approach-pose'
import type { SemanticScene } from '@/lib/robot-map/farm-semantic-map'

export type PlantNavigationStepPhase = 'inspection'

export type PlantNavigationStep = {
  phase: PlantNavigationStepPhase
  pose: RobotTargetPose
  displayPose: RobotTargetPose
}

export type PlantNavigationPlan = {
  inspectionPose: RobotTargetPose
  inspectionDisplayPose: RobotTargetPose
  inspectWaypointId: string | null
  inspectWaypointIds: string[]
  inspectWaypointName: string | null
  steps: PlantNavigationStep[]
}

export function buildPlantInspectionNavigationPlan(
  plantId: string,
  preferredScene: SemanticScene,
  fallbackScene: SemanticScene,
  fallbackPositionLabel: string,
  currentPose: { x: number, y: number } | null,
): PlantNavigationPlan | null {
  const observationSelection = resolvePlantObservationSelection(
    plantId,
    preferredScene,
    fallbackScene,
    fallbackPositionLabel,
    currentPose,
  )

  if (!observationSelection) {
    return null
  }

  return {
    // 식물 클릭 이동은 안전한 inspect waypoint를 기준으로 경로를 고르되,
    // 실제 최종 정지는 작물 쪽 관측 pose 로 마무리한다.
    inspectionPose: observationSelection.goalPose,
    inspectionDisplayPose: observationSelection.displayPose,
    inspectWaypointId: observationSelection.inspectWaypointId,
    inspectWaypointIds: observationSelection.inspectWaypointIds,
    inspectWaypointName: observationSelection.inspectWaypointName,
    steps: [{
      phase: 'inspection',
      pose: observationSelection.goalPose,
      displayPose: observationSelection.displayPose,
    }],
  }
}
