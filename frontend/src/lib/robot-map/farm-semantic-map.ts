/*
 * 이 모듈은 농장 의미 지도를 정의한다.
 */
/**
 * 의미 기반 자산 kind 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type SemanticAssetKind = 'plant' | 'sprinkler'
/**
 * 의미 기반 자산 상태를 화면과 로직에서 공통으로 쓰기 위한 타입이다.
 */
export type SemanticAssetStatus = 'normal' | 'target' | 'attention' | 'handled'

/**
 * 의미 기반 위치 자세 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type SemanticPose = {
  x: number
  y: number
  z: number
  yaw: number
  frameId: string
}

/**
 * 의미 기반 관측 후보 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type SemanticObservationCandidate = {
  inspectWaypointId?: string
  inspectWaypointName?: string
  navigationPose: SemanticPose
  approachPose?: SemanticPose
}

/**
 * 의미 기반 자산 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type SemanticAsset = {
  id: string
  linkedId?: string
  kind: SemanticAssetKind
  label: string
  shortLabel: string
  zoneId: string
  description: string
  position: {
    x: number
    y: number
  }
  navigationPose?: SemanticPose
  approachPose?: SemanticPose
  inspectWaypointId?: string
  inspectWaypointName?: string
  observationCandidates?: SemanticObservationCandidate[]
  status: SemanticAssetStatus
}

/**
 * 의미 기반 guide line 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type SemanticGuideLine = {
  id: string
  axis: 'x' | 'y'
  value: number
  label: string
}

/**
 * 의미 기반 장면 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
export type SemanticScene = {
  bounds: {
    minX: number
    maxX: number
    minY: number
    maxY: number
  }
  rowGuides: SemanticGuideLine[]
  laneGuides: SemanticGuideLine[]
  assets: SemanticAsset[]
}

const PLANT_XS = [-6, -2, 2, 6]
const PLANT_YS = [-6, -4, -2, 2, 4, 6]

function toTwoDigit(value: number) {
  return String(value).padStart(2, '0')
}

function buildPlantAssets(): SemanticAsset[] {
  let counter = 1
  const assets: SemanticAsset[] = []

  for (const yValue of PLANT_YS) {
    for (const xValue of PLANT_XS) {
      const plantId = `farm01_plant_${toTwoDigit(counter)}`
      const tomatoId = `${plantId}_tomato_01`
      const status: SemanticAssetStatus =
        plantId === 'farm01_plant_06'
          ? 'attention'
          : plantId === 'farm01_plant_03'
            ? 'target'
            : 'normal'

      assets.push({
        id: plantId,
        linkedId: tomatoId,
        kind: 'plant',
        label: `토마토 식물 ${toTwoDigit(counter)}`,
        shortLabel: toTwoDigit(counter),
        zoneId: 'farm_01',
        description:
          status === 'attention'
            ? '병해 검토 후보가 자주 발생하는 위치'
            : status === 'target'
              ? '수확 후보 토마토가 우선 표시된 위치'
              : '순찰 및 작물 관찰 대상 식물',
        position: {
          x: xValue,
          y: yValue,
        },
        status,
      })
      counter += 1
    }
  }

  return assets
}

function buildSprinklerAssets(): SemanticAsset[] {
  return PLANT_XS.map((xValue, index) => ({
    id: `sprinkler_${index}`,
    linkedId: 'farm_01_watering',
    kind: 'sprinkler',
    label: `${index + 1}번 급수 헤드`,
    shortLabel: `S${index + 1}`,
    zoneId: 'farm_01',
    description: '물주기나 영양제 주기를 직접 실행할 수 있는 급수 포인트',
    position: {
      x: xValue,
      y: 0,
    },
    status: index === 1 ? 'attention' : 'normal',
  }))
}

export const farmSemanticScene: SemanticScene = {
  bounds: {
    minX: -10,
    maxX: 10,
    minY: -10,
    maxY: 10,
  },
  rowGuides: PLANT_XS.map((xValue, index) => ({
    id: `row-${index + 1}`,
    axis: 'x',
    value: xValue,
    label: `${index + 1}번 이랑`,
  })),
  laneGuides: [
    { id: 'lane-bottom-1', axis: 'y', value: -8, label: '1번 고랑' },
    { id: 'lane-bottom-2', axis: 'y', value: -5, label: '2번 고랑' },
    { id: 'lane-mid', axis: 'y', value: 0, label: '중앙 고랑' },
    { id: 'lane-top-1', axis: 'y', value: 5, label: '3번 고랑' },
    { id: 'lane-top-2', axis: 'y', value: 8, label: '4번 고랑' },
  ],
  assets: [...buildPlantAssets(), ...buildSprinklerAssets()],
}

/**
 * 위치 자세 label을 해석해 내부 표현으로 바꾸는 함수다.
 */
export function parsePoseLabel(poseLabel: string) {
  const match = poseLabel.match(/x\s*(-?\d+(?:\.\d+)?)\s*\/\s*y\s*(-?\d+(?:\.\d+)?)/i)
  if (!match) {
    return null
  }

  const xValue = Number(match[1])
  const yValue = Number(match[2])

  if (!Number.isFinite(xValue) || !Number.isFinite(yValue)) {
    return null
  }

  return {
    x: xValue,
    y: yValue,
  }
}

/**
 * 의미 기반 target id을 현재 입력 기준으로 확정하는 함수다.
 */
export function resolveSemanticTargetId(targetLabel: string) {
  const tomatoMatch = targetLabel.match(/farm01_plant_\d{2}_tomato_\d{2}/)
  if (tomatoMatch) {
    return tomatoMatch[0].replace(/_tomato_\d{2}$/, '')
  }

  const plantMatch = targetLabel.match(/farm01_plant_\d{2}/)
  return plantMatch?.[0] ?? null
}
