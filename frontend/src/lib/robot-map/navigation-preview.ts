import type { RobotPoseSnapshot, RobotTargetPose } from '@/lib/api/agribot'

export type NavigationPreviewPoint = {
  x: number
  y: number
}

type PoseLike = Pick<RobotPoseSnapshot | RobotTargetPose, 'x' | 'y'>

const PREVIEW_POINT_TOLERANCE_M = 0.02

function isFinitePoint(point: PoseLike | null | undefined): point is PoseLike {
  return (
    point !== null
    && point !== undefined
    && Number.isFinite(point.x)
    && Number.isFinite(point.y)
  )
}

function isNearPoint(left: NavigationPreviewPoint, right: NavigationPreviewPoint) {
  return (
    Math.abs(left.x - right.x) <= PREVIEW_POINT_TOLERANCE_M
    && Math.abs(left.y - right.y) <= PREVIEW_POINT_TOLERANCE_M
  )
}

export function buildNavigationPreviewPath(
  startPose: PoseLike | null | undefined,
  targets: Array<PoseLike | null | undefined>,
): NavigationPreviewPoint[] {
  const rawPoints = [startPose, ...targets]
    .filter(isFinitePoint)
    .map((point) => ({
      x: point.x,
      y: point.y,
    }))

  return rawPoints.reduce<NavigationPreviewPoint[]>((accumulator, point) => {
    const previousPoint = accumulator[accumulator.length - 1]
    if (previousPoint && isNearPoint(previousPoint, point)) {
      return accumulator
    }
    accumulator.push(point)
    return accumulator
  }, [])
}
