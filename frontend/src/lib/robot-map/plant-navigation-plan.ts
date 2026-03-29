import type { RobotTargetPose } from '@/lib/api/agribot'
import { buildPlantInspectionTargetPose } from '@/lib/robot-map/approach-pose'
import type { SemanticScene } from '@/lib/robot-map/farm-semantic-map'

export type PlantNavigationStepPhase = 'inspection'

export type PlantNavigationStep = {
  phase: PlantNavigationStepPhase
  pose: RobotTargetPose
}

export type PlantNavigationPlan = {
  inspectionPose: RobotTargetPose
  steps: PlantNavigationStep[]
}

export function buildPlantInspectionNavigationPlan(
  plantId: string,
  preferredScene: SemanticScene,
  fallbackScene: SemanticScene,
  fallbackPositionLabel: string,
  currentPose: { x: number, y: number } | null,
): PlantNavigationPlan | null {
  const inspectionPose = buildPlantInspectionTargetPose(
    plantId,
    preferredScene,
    fallbackScene,
    fallbackPositionLabel,
    currentPose,
  )

  if (!inspectionPose) {
    return null
  }

  return {
    inspectionPose,
    steps: [{ phase: 'inspection', pose: inspectionPose }],
  }
}
