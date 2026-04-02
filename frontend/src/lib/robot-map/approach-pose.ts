/*
 * 이 모듈은 작물 접근 자세를 계산한다.
 */
import type { RobotObservationGoalCandidate, RobotTargetPose } from '@/lib/api/agribot'
import {
  parsePoseLabel,
  type SemanticAsset,
  type SemanticObservationCandidate,
  type SemanticPose,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'

const OBSERVATION_CANDIDATE_MATCH_TOLERANCE_M = 0.15

/**
 * 작물 관측 selection 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type PlantObservationSelection = {
  targetAsset: SemanticAsset | null
  inspectWaypointId: string | null
  inspectWaypointIds: string[]
  inspectWaypointName: string | null
  navigationPose: RobotTargetPose
  displayPose: RobotTargetPose
  approachPose: RobotTargetPose | null
  observationCandidates: RobotObservationGoalCandidate[]
}

/**
 * 작물 관측 selection strategy 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type PlantObservationSelectionStrategy = 'nearest' | 'harvest-primary'

function clampToSceneBounds(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value))
}

function toRobotTargetPose(pose: SemanticPose): RobotTargetPose {
  return {
    x: pose.x,
    y: pose.y,
    z: pose.z,
    yaw: pose.yaw,
    frameId: pose.frameId,
  }
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

function uniqueWaypointIds(candidates: SemanticObservationCandidate[]) {
  return Array.from(
    new Set(
      candidates
        .map((candidate) => candidate.inspectWaypointId?.trim() ?? '')
        .filter((waypointId) => waypointId.length > 0),
    ),
  )
}

function candidateNavigationPose(candidate: SemanticObservationCandidate) {
  return candidate.navigationPose ?? candidate.approachPose ?? null
}

function candidateDisplayPose(candidate: SemanticObservationCandidate) {
  return candidate.approachPose ?? candidate.navigationPose
}

function toRobotObservationGoalCandidate(candidate: SemanticObservationCandidate): RobotObservationGoalCandidate | null {
  const inspectWaypointId = candidate.inspectWaypointId?.trim() ?? ''
  const navigationPose = candidateNavigationPose(candidate)
  const finalTargetPose = candidateDisplayPose(candidate)

  if (!inspectWaypointId || !navigationPose || !finalTargetPose) {
    return null
  }

  return {
    inspectWaypointId,
    inspectWaypointName: candidate.inspectWaypointName?.trim() || null,
    navigationPose: toRobotTargetPose(navigationPose),
    finalTargetPose: toRobotTargetPose(finalTargetPose),
  }
}

function normalizeObservationCandidates(asset: SemanticAsset | null) {
  if (!asset) {
    return []
  }

  if (asset.observationCandidates && asset.observationCandidates.length > 0) {
    return asset.observationCandidates.filter((candidate) => candidateNavigationPose(candidate) !== null)
  }

  if (asset.navigationPose || asset.approachPose) {
    return [{
      inspectWaypointId: asset.inspectWaypointId,
      inspectWaypointName: asset.inspectWaypointName,
      navigationPose: asset.navigationPose ?? asset.approachPose!,
      approachPose: asset.approachPose,
    }]
  }

  return []
}

function observationCandidateCost(
  candidate: SemanticObservationCandidate,
  options: {
    plantPosition: { x: number, y: number }
    currentPose: { x: number, y: number } | null
  },
) {
  const { plantPosition, currentPose } = options
  const navigationPose = candidateNavigationPose(candidate)
  const displayPose = candidateDisplayPose(candidate)
  if (!navigationPose || !displayPose) {
    return {
      travelDistance: Number.POSITIVE_INFINITY,
      centerBias: Number.POSITIVE_INFINITY,
      cropDistance: Number.POSITIVE_INFINITY,
      waypointId: '',
    }
  }

  const referencePose = currentPose ?? plantPosition
  const travelDistance = Math.hypot(
    navigationPose.x - referencePose.x,
    navigationPose.y - referencePose.y,
  )
  const centerBias = Math.abs(navigationPose.x)
  const cropDistance = Math.hypot(
    displayPose.x - plantPosition.x,
    displayPose.y - plantPosition.y,
  )

  return {
    travelDistance,
    centerBias,
    cropDistance,
    waypointId: candidate.inspectWaypointId ?? '',
  }
}

function selectObservationCandidate(
  targetAsset: SemanticAsset,
  candidates: SemanticObservationCandidate[],
  currentPose: { x: number, y: number } | null,
  selectionStrategy: PlantObservationSelectionStrategy,
) {
  if (selectionStrategy === 'harvest-primary') {
    return candidates[0] ?? null
  }

  return [...candidates].sort((leftCandidate, rightCandidate) => {
    const leftCost = observationCandidateCost(leftCandidate, {
      plantPosition: targetAsset.position,
      currentPose,
    })
    const rightCost = observationCandidateCost(rightCandidate, {
      plantPosition: targetAsset.position,
      currentPose,
    })

    if (leftCost.travelDistance !== rightCost.travelDistance) {
      return leftCost.travelDistance - rightCost.travelDistance
    }
    if (leftCost.centerBias !== rightCost.centerBias) {
      return leftCost.centerBias - rightCost.centerBias
    }
    if (leftCost.cropDistance !== rightCost.cropDistance) {
      return leftCost.cropDistance - rightCost.cropDistance
    }

    return leftCost.waypointId.localeCompare(rightCost.waypointId)
  })[0] ?? null
}

function buildFallbackObservationSelection(
  pose: RobotTargetPose,
  targetAsset: SemanticAsset | null,
  observationCandidates: RobotObservationGoalCandidate[] = [],
): PlantObservationSelection {
  const fallbackInspectWaypointId =
    observationCandidates[0]?.inspectWaypointId
    ?? targetAsset?.inspectWaypointId
    ?? null

  return {
    targetAsset,
    inspectWaypointId: fallbackInspectWaypointId,
    inspectWaypointIds:
      observationCandidates.length > 0
        ? observationCandidates.map((candidate) => candidate.inspectWaypointId)
        : targetAsset?.inspectWaypointId
          ? [targetAsset.inspectWaypointId]
          : [],
    inspectWaypointName:
      observationCandidates[0]?.inspectWaypointName
      ?? targetAsset?.inspectWaypointName
      ?? null,
    navigationPose: pose,
    displayPose: targetAsset?.approachPose ?? pose,
    approachPose: targetAsset?.approachPose ?? null,
    observationCandidates,
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

/**
 * 관측 후보 display 위치 자세을 현재 입력 기준으로 확정하는 함수다.
 */
export function resolveObservationCandidateDisplayPose(
  asset: SemanticAsset | null,
  navigationPose: { x: number, y: number } | null | undefined,
) {
  if (!asset || !navigationPose) {
    return null
  }

  const matchedCandidate = normalizeObservationCandidates(asset).find((candidate) => {
    const candidatePose = candidateNavigationPose(candidate)
    if (!candidatePose) {
      return false
    }

    return (
      Math.abs(candidatePose.x - navigationPose.x) <= OBSERVATION_CANDIDATE_MATCH_TOLERANCE_M
      && Math.abs(candidatePose.y - navigationPose.y) <= OBSERVATION_CANDIDATE_MATCH_TOLERANCE_M
    )
  })

  if (!matchedCandidate) {
    return null
  }

  return toRobotTargetPose(candidateDisplayPose(matchedCandidate))
}

/**
 * 작물 관측 selection을 현재 입력 기준으로 확정하는 함수다.
 */
export function resolvePlantObservationSelection(
  plantId: string,
  preferredScene: SemanticScene,
  fallbackScene: SemanticScene,
  fallbackPositionLabel: string,
  currentPose: { x: number, y: number } | null,
  selectionStrategy: PlantObservationSelectionStrategy = 'nearest',
): PlantObservationSelection | null {
  const preferredAsset = preferredScene.assets.find((asset) => asset.kind === 'plant' && asset.id === plantId)
  const fallbackAsset = fallbackScene.assets.find((asset) => asset.kind === 'plant' && asset.id === plantId)
  const targetAsset = preferredAsset ?? fallbackAsset ?? null
  const candidateSourceAsset =
    normalizeObservationCandidates(preferredAsset ?? null).length > 0
      ? preferredAsset
      : fallbackAsset ?? preferredAsset ?? null

  if (targetAsset && candidateSourceAsset) {
    const observationCandidates = normalizeObservationCandidates(candidateSourceAsset)
    const robotObservationCandidates = observationCandidates
      .map((candidate) => toRobotObservationGoalCandidate(candidate))
      .filter((candidate): candidate is RobotObservationGoalCandidate => candidate !== null)
    const selectedCandidate = selectObservationCandidate(
      targetAsset,
      observationCandidates,
      currentPose,
      selectionStrategy,
    )
    if (selectedCandidate) {
      const navigationPose = candidateNavigationPose(selectedCandidate)
      const displayPose = candidateDisplayPose(selectedCandidate)
      if (navigationPose && displayPose) {
        return {
          targetAsset,
          inspectWaypointId: selectedCandidate.inspectWaypointId ?? null,
          inspectWaypointIds: uniqueWaypointIds(observationCandidates),
          inspectWaypointName: selectedCandidate.inspectWaypointName ?? null,
          navigationPose: toRobotTargetPose(navigationPose),
          displayPose: toRobotTargetPose(displayPose),
          approachPose: selectedCandidate.approachPose
            ? toRobotTargetPose(selectedCandidate.approachPose)
            : null,
          observationCandidates: robotObservationCandidates,
        }
      }
    }

    const fallbackPose =
      targetAsset.navigationPose
      ?? targetAsset.approachPose
      ?? buildInspectionPoseFromScene(targetAsset.position, preferredScene, currentPose)
      ?? buildInspectionPoseFromScene(targetAsset.position, fallbackScene, currentPose)

    if (fallbackPose) {
      return buildFallbackObservationSelection(fallbackPose, targetAsset, robotObservationCandidates)
    }
  }

  const parsedPose = parsePoseLabel(fallbackPositionLabel)
  if (!parsedPose) {
    return null
  }

  const fallbackPose = (
    buildInspectionPoseFromScene(parsedPose, preferredScene, currentPose)
    ?? buildInspectionPoseFromScene(parsedPose, fallbackScene, currentPose)
  )

  return fallbackPose ? buildFallbackObservationSelection(fallbackPose, targetAsset) : null
}

function buildPlantPoseWithPreference(
  plantId: string,
  preferredScene: SemanticScene,
  fallbackScene: SemanticScene,
  fallbackPositionLabel: string,
  currentPose: { x: number, y: number } | null,
  posePreference: 'approach-first' | 'navigation-first',
): RobotTargetPose | null {
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

  return posePreference === 'navigation-first'
    ? observationSelection.navigationPose
    : observationSelection.approachPose ?? observationSelection.navigationPose
}

/**
 * 작물 target 위치 자세을 조합해 만드는 함수다.
 */
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

/**
 * 작물 점검 target 위치 자세을 조합해 만드는 함수다.
 */
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
