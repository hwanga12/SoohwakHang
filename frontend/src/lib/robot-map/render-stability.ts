/*
 * 이 모듈은 지도 렌더링 흔들림을 줄이는 보조 로직을 담는다.
 */
import { useRef } from 'react'
import type {
  RobotMapData,
  RobotPoseSnapshot,
  RobotTargetPose,
} from '@/lib/api/agribot'
import type {
  SemanticAsset,
  SemanticGuideLine,
  SemanticObservationCandidate,
  SemanticPose,
  SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'
import type { NavigationPreviewPoint } from '@/lib/robot-map/navigation-preview'

function areNullableValuesEqual<T>(
  left: T | null | undefined,
  right: T | null | undefined,
  compare: (nextLeft: T, nextRight: T) => boolean,
) {
  if (left === right) {
    return true
  }
  if (left == null || right == null) {
    return false
  }
  return compare(left, right)
}

function areSemanticPosesEqual(
  left: SemanticPose | null | undefined,
  right: SemanticPose | null | undefined,
) {
  return areNullableValuesEqual(left, right, (nextLeft, nextRight) => (
    nextLeft.x === nextRight.x
    && nextLeft.y === nextRight.y
    && nextLeft.z === nextRight.z
    && nextLeft.yaw === nextRight.yaw
    && nextLeft.frameId === nextRight.frameId
  ))
}

function areObservationCandidatesEqual(
  left: SemanticObservationCandidate[] | undefined,
  right: SemanticObservationCandidate[] | undefined,
) {
  if (left === right) {
    return true
  }
  if (!left || !right || left.length !== right.length) {
    return false
  }

  for (let index = 0; index < left.length; index += 1) {
    const previous = left[index]
    const next = right[index]
    if (
      previous.inspectWaypointId !== next.inspectWaypointId
      || previous.inspectWaypointName !== next.inspectWaypointName
      || !areSemanticPosesEqual(previous.navigationPose, next.navigationPose)
      || !areSemanticPosesEqual(previous.approachPose, next.approachPose)
    ) {
      return false
    }
  }

  return true
}

function areSemanticAssetsEqual(left: SemanticAsset, right: SemanticAsset) {
  return (
    left.id === right.id
    && left.linkedId === right.linkedId
    && left.kind === right.kind
    && left.label === right.label
    && left.shortLabel === right.shortLabel
    && left.zoneId === right.zoneId
    && left.description === right.description
    && left.status === right.status
    && left.inspectWaypointId === right.inspectWaypointId
    && left.inspectWaypointName === right.inspectWaypointName
    && left.position.x === right.position.x
    && left.position.y === right.position.y
    && areSemanticPosesEqual(left.navigationPose, right.navigationPose)
    && areSemanticPosesEqual(left.approachPose, right.approachPose)
    && areObservationCandidatesEqual(left.observationCandidates, right.observationCandidates)
  )
}

function areGuideLinesEqual(left: SemanticGuideLine[], right: SemanticGuideLine[]) {
  if (left === right) {
    return true
  }
  if (left.length !== right.length) {
    return false
  }

  for (let index = 0; index < left.length; index += 1) {
    const previous = left[index]
    const next = right[index]
    if (
      previous.id !== next.id
      || previous.axis !== next.axis
      || previous.label !== next.label
      || previous.value !== next.value
    ) {
      return false
    }
  }

  return true
}

/**
 * 로봇 위치 자세 동일이 서로 같은지 비교하는 함수다.
 */
export function areRobotPosesEqual(
  left: RobotTargetPose | RobotPoseSnapshot | null | undefined,
  right: RobotTargetPose | RobotPoseSnapshot | null | undefined,
) {
  return areNullableValuesEqual(left, right, (nextLeft, nextRight) => {
    const leftYaw = 'yaw' in nextLeft ? nextLeft.yaw : nextLeft.yawDeg
    const rightYaw = 'yaw' in nextRight ? nextRight.yaw : nextRight.yawDeg
    return nextLeft.x === nextRight.x && nextLeft.y === nextRight.y && leftYaw === rightYaw
  })
}

/**
 * 로봇 지도 동일이 서로 같은지 비교하는 함수다.
 */
export function areRobotMapsEqual(
  left: RobotMapData | undefined,
  right: RobotMapData | undefined,
) {
  return areNullableValuesEqual(left, right, (nextLeft, nextRight) => (
    nextLeft.mapId === nextRight.mapId
    && nextLeft.imageUrl === nextRight.imageUrl
    && nextLeft.width === nextRight.width
    && nextLeft.height === nextRight.height
    && nextLeft.resolution === nextRight.resolution
    && nextLeft.bounds.minX === nextRight.bounds.minX
    && nextLeft.bounds.maxX === nextRight.bounds.maxX
    && nextLeft.bounds.minY === nextRight.bounds.minY
    && nextLeft.bounds.maxY === nextRight.bounds.maxY
    && nextLeft.origin.x === nextRight.origin.x
    && nextLeft.origin.y === nextRight.origin.y
    && nextLeft.origin.z === nextRight.origin.z
    && nextLeft.origin.yaw === nextRight.origin.yaw
    && nextLeft.origin.frameId === nextRight.origin.frameId
  ))
}

/**
 * 미리보기 경로 동일이 서로 같은지 비교하는 함수다.
 */
export function arePreviewPathsEqual(
  left: NavigationPreviewPoint[] | null | undefined,
  right: NavigationPreviewPoint[] | null | undefined,
) {
  return areNullableValuesEqual(left, right, (nextLeft, nextRight) => {
    if (nextLeft.length !== nextRight.length) {
      return false
    }

    for (let index = 0; index < nextLeft.length; index += 1) {
      if (
        nextLeft[index].x !== nextRight[index].x
        || nextLeft[index].y !== nextRight[index].y
      ) {
        return false
      }
    }

    return true
  })
}

/**
 * 의미 기반 장면 동일이 서로 같은지 비교하는 함수다.
 */
export function areSemanticScenesEqual(left: SemanticScene, right: SemanticScene) {
  if (left === right) {
    return true
  }

  if (
    left.bounds.minX !== right.bounds.minX
    || left.bounds.maxX !== right.bounds.maxX
    || left.bounds.minY !== right.bounds.minY
    || left.bounds.maxY !== right.bounds.maxY
    || !areGuideLinesEqual(left.rowGuides, right.rowGuides)
    || !areGuideLinesEqual(left.laneGuides, right.laneGuides)
    || left.assets.length !== right.assets.length
  ) {
    return false
  }

  for (let index = 0; index < left.assets.length; index += 1) {
    if (!areSemanticAssetsEqual(left.assets[index], right.assets[index])) {
      return false
    }
  }

  return true
}

function useStableValue<T>(value: T, areEqual: (left: T, right: T) => boolean) {
  const stableRef = useRef(value)

  if (!areEqual(stableRef.current, value)) {
    stableRef.current = value
  }

  return stableRef.current
}

/**
 * stable 의미 기반 장면 상태와 부수효과를 묶어 재사용하는 훅이다.
 */
export function useStableSemanticScene(scene: SemanticScene) {
  return useStableValue(scene, areSemanticScenesEqual)
}

/**
 * stable 로봇 지도 상태와 부수효과를 묶어 재사용하는 훅이다.
 */
export function useStableRobotMap(map: RobotMapData | undefined) {
  return useStableValue(map, areRobotMapsEqual)
}

/**
 * stable 로봇 위치 자세 상태와 부수효과를 묶어 재사용하는 훅이다.
 */
export function useStableRobotPose<T extends RobotTargetPose | RobotPoseSnapshot | null | undefined>(pose: T) {
  return useStableValue(pose, areRobotPosesEqual) as T
}

/**
 * stable 미리보기 경로 상태와 부수효과를 묶어 재사용하는 훅이다.
 */
export function useStablePreviewPath(path: NavigationPreviewPoint[] | null | undefined) {
  return useStableValue(path, arePreviewPathsEqual)
}
