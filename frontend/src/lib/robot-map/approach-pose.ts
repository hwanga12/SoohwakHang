import type { RobotTargetPose } from '@/lib/api/agribot'
import {
  parsePoseLabel,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'

function clampToSceneBounds(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value))
}

function sortedUniqueValues(values: number[]) {
  return Array.from(new Set(values)).sort((left, right) => left - right)
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

function resolveObservationAislePoseX(
  positionX: number,
  rowGuideValues: number[],
  referenceX: number | null,
) {
  const nearestRowIndex = rowGuideValues.reduce((bestIndex, currentValue, currentIndex) => {
    const bestDistance = Math.abs(rowGuideValues[bestIndex] - positionX)
    const currentDistance = Math.abs(currentValue - positionX)
    return currentDistance < bestDistance ? currentIndex : bestIndex
  }, 0)

  const rowCount = rowGuideValues.length
  const rowValue = rowGuideValues[nearestRowIndex]

  if (rowCount < 2) {
    return {
      x: rowValue,
      yaw: rowValue < positionX ? 0 : Math.PI,
    }
  }

  const aisleCandidates: number[] = []

  if (nearestRowIndex > 0) {
    aisleCandidates.push((rowGuideValues[nearestRowIndex - 1] + rowValue) / 2)
  } else {
    aisleCandidates.push(rowValue - ((rowGuideValues[1] - rowValue) / 2))
  }

  if (nearestRowIndex < rowCount - 1) {
    aisleCandidates.push((rowValue + rowGuideValues[nearestRowIndex + 1]) / 2)
  } else {
    aisleCandidates.push(rowValue + ((rowValue - rowGuideValues[rowCount - 2]) / 2))
  }

  const targetX = aisleCandidates.reduce((bestValue, candidateValue) => {
    const reference = referenceX ?? 0
    const bestDistance = Math.abs(bestValue - reference)
    const candidateDistance = Math.abs(candidateValue - reference)
    return candidateDistance < bestDistance ? candidateValue : bestValue
  })

  return {
    x: targetX,
    yaw: targetX < positionX ? 0 : Math.PI,
  }
}

function buildInspectionPoseFromScene(
  position: { x: number, y: number },
  scene: SemanticScene,
  currentPose: { x: number, y: number } | null,
): RobotTargetPose | null {
  const rowGuideValues = semanticRowGuideValues(scene)
  if (rowGuideValues.length < 2) {
    return null
  }

  const observationPose = resolveObservationAislePoseX(position.x, rowGuideValues, currentPose?.x ?? null)

  return {
    // 식물 중심이 아니라 실제로 멈출 수 있는 통로 좌표를 계산한다.
    x: clampToSceneBounds(observationPose.x, scene.bounds.minX + 0.5, scene.bounds.maxX - 0.5),
    y: clampToSceneBounds(position.y, scene.bounds.minY + 0.5, scene.bounds.maxY - 0.5),
    z: 0,
    yaw: observationPose.yaw,
    frameId: 'map',
  }
}

function buildPlantPoseWithPreference(
  plantId: string,
  preferredScene: SemanticScene,
  fallbackScene: SemanticScene,
  fallbackPositionLabel: string,
  currentPose: { x: number, y: number } | null,
  posePreference: 'approach-first' | 'navigation-first',
): RobotTargetPose | null {
  const preferredAsset = preferredScene.assets.find((asset) => asset.kind === 'plant' && asset.id === plantId)
  const fallbackAsset = fallbackScene.assets.find((asset) => asset.kind === 'plant' && asset.id === plantId)
  const targetAsset = preferredAsset ?? fallbackAsset

  if (targetAsset) {
    const prioritizedPose =
      posePreference === 'navigation-first'
        ? targetAsset.navigationPose ?? targetAsset.approachPose
        : targetAsset.approachPose ?? targetAsset.navigationPose

    return (
      prioritizedPose
      ?? buildInspectionPoseFromScene(targetAsset.position, preferredScene, currentPose)
      ?? buildInspectionPoseFromScene(targetAsset.position, fallbackScene, currentPose)
    )
  }

  const parsedPose = parsePoseLabel(fallbackPositionLabel)
  if (!parsedPose) {
    return null
  }

  return (
    buildInspectionPoseFromScene(parsedPose, preferredScene, currentPose)
    ?? buildInspectionPoseFromScene(parsedPose, fallbackScene, currentPose)
  )
}

export function buildPlantTargetPose(
  plantId: string,
  preferredScene: SemanticScene,
  fallbackScene: SemanticScene,
  fallbackPositionLabel: string,
  currentPose: { x: number, y: number } | null,
): RobotTargetPose | null {
  return buildPlantPoseWithPreference(
    plantId,
    preferredScene,
    fallbackScene,
    fallbackPositionLabel,
    currentPose,
    'approach-first',
  )
}

export function buildPlantInspectionTargetPose(
  plantId: string,
  preferredScene: SemanticScene,
  fallbackScene: SemanticScene,
  fallbackPositionLabel: string,
  currentPose: { x: number, y: number } | null,
): RobotTargetPose | null {
  return buildPlantPoseWithPreference(
    plantId,
    preferredScene,
    fallbackScene,
    fallbackPositionLabel,
    currentPose,
    'navigation-first',
  )
}
