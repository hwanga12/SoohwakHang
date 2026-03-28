import type { RobotTargetPose } from '@/lib/api/agribot'
import { buildPlantInspectionTargetPose } from '@/lib/robot-map/approach-pose'
import type { SemanticScene } from '@/lib/robot-map/farm-semantic-map'

export type PlantNavigationStepPhase = 'transit' | 'inspection'

export type PlantNavigationStep = {
  phase: PlantNavigationStepPhase
  pose: RobotTargetPose
}

export type PlantNavigationPlan = {
  inspectionPose: RobotTargetPose
  steps: PlantNavigationStep[]
}

function poseDistanceXY(
  left: { x: number, y: number } | null | undefined,
  right: { x: number, y: number } | null | undefined,
) {
  if (!left || !right) {
    return Number.POSITIVE_INFINITY
  }

  return Math.hypot(left.x - right.x, left.y - right.y)
}

function sortedUnique(values: number[]) {
  return Array.from(new Set(values.map((value) => Number(value.toFixed(2))))).sort((left, right) => left - right)
}

function laneCentersFromScene(scene: SemanticScene) {
  return sortedUnique(
    scene.assets
      .filter((asset) => asset.kind === 'plant' && asset.navigationPose)
      .map((asset) => asset.navigationPose!.x),
  )
}

function laneStopsFromScene(scene: SemanticScene) {
  return sortedUnique(
    scene.assets
      .filter((asset) => asset.kind === 'plant' && asset.navigationPose)
      .map((asset) => asset.navigationPose!.y),
  )
}

function connectorBandYs(scene: SemanticScene) {
  const laneStops = laneStopsFromScene(scene)
  if (laneStops.length === 0) {
    return null
  }

  const typicalGap =
    laneStops.length > 1
      ? Math.abs(laneStops[1] - laneStops[0])
      : 2
  const connectorOffset = Math.max(typicalGap * 1.3, 2.2)

  return {
    south: Number((laneStops[0] - connectorOffset).toFixed(2)),
    north: Number((laneStops[laneStops.length - 1] + connectorOffset).toFixed(2)),
  }
}

function nearestLaneCenter(
  laneCenters: number[],
  currentX: number,
  targetX: number,
) {
  return laneCenters.reduce((bestValue, candidate) => {
    const bestDistance = Math.abs(bestValue - currentX)
    const candidateDistance = Math.abs(candidate - currentX)
    if (candidateDistance !== bestDistance) {
      return candidateDistance < bestDistance ? candidate : bestValue
    }

    return Math.abs(candidate - targetX) < Math.abs(bestValue - targetX)
      ? candidate
      : bestValue
  }, laneCenters[0])
}

function buildTransitPose(referencePose: RobotTargetPose, x: number, y: number): RobotTargetPose {
  return {
    x,
    y,
    z: referencePose.z,
    yaw: referencePose.yaw,
    frameId: referencePose.frameId,
  }
}

function dedupeSteps(
  currentPose: { x: number, y: number } | null,
  steps: PlantNavigationStep[],
) {
  const deduped: PlantNavigationStep[] = []
  let lastPose = currentPose

  for (const step of steps) {
    if (poseDistanceXY(lastPose, step.pose) <= 0.35) {
      continue
    }

    deduped.push(step)
    lastPose = step.pose
  }

  return deduped
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

  const laneCenters = laneCentersFromScene(preferredScene)
  const connectorBands = connectorBandYs(preferredScene)
  if (!currentPose || laneCenters.length === 0 || connectorBands === null) {
    return {
      inspectionPose,
      steps: [{ phase: 'inspection', pose: inspectionPose }],
    }
  }

  const currentLaneX = nearestLaneCenter(laneCenters, currentPose.x, inspectionPose.x)
  const usesSameLane = Math.abs(currentLaneX - inspectionPose.x) <= 0.25
  const shouldUseConnectorTransit =
    !usesSameLane
    && poseDistanceXY(currentPose, inspectionPose) > 2.4

  const northCost =
    Math.abs(currentPose.y - connectorBands.north)
    + Math.abs(inspectionPose.y - connectorBands.north)
  const southCost =
    Math.abs(currentPose.y - connectorBands.south)
    + Math.abs(inspectionPose.y - connectorBands.south)
  const chosenConnectorY = northCost <= southCost ? connectorBands.north : connectorBands.south

  const steps: PlantNavigationStep[] = []
  if (shouldUseConnectorTransit) {
    steps.push({
      phase: 'transit',
      pose: buildTransitPose(inspectionPose, currentLaneX, chosenConnectorY),
    })
    steps.push({
      phase: 'transit',
      pose: buildTransitPose(inspectionPose, inspectionPose.x, chosenConnectorY),
    })
  }

  steps.push({
    phase: 'inspection',
    pose: inspectionPose,
  })

  return {
    inspectionPose,
    steps: dedupeSteps(currentPose, steps),
  }
}
