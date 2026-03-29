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
    inspectionPose: observationSelection.navigationPose,
    inspectionDisplayPose: observationSelection.displayPose,
    inspectWaypointId: observationSelection.inspectWaypointId,
    inspectWaypointIds: observationSelection.inspectWaypointIds,
    inspectWaypointName: observationSelection.inspectWaypointName,
    steps: [{
      phase: 'inspection',
      pose: observationSelection.navigationPose,
      displayPose: observationSelection.displayPose,
    }],
  }
}
