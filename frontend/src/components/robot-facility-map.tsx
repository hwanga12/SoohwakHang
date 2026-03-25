import { useMemo, useState } from 'react'
import { AppIcon } from '@/components/app-icon'
import {
  type SemanticAsset,
  type SemanticAssetKind,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'

type RobotFacilityMapProps = {
  pose: {
    x: number
    y: number
  }
  scene: SemanticScene
  selectedAssetId: string | null
  targetAssetId: string | null
  zoom: number
  onSelectAsset: (assetId: string) => void
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function toPercent(scene: SemanticScene, xValue: number, yValue: number) {
  const width = scene.bounds.maxX - scene.bounds.minX
  const height = scene.bounds.maxY - scene.bounds.minY

  return {
    left: `${clamp(((xValue - scene.bounds.minX) / width) * 100, 0, 100)}%`,
    top: `${clamp((1 - ((yValue - scene.bounds.minY) / height)) * 100, 0, 100)}%`,
  }
}

function countByKind(scene: SemanticScene, kind: SemanticAssetKind) {
  return scene.assets.filter((asset) => asset.kind === kind).length
}

export function RobotFacilityMap({
  pose,
  scene,
  selectedAssetId,
  targetAssetId,
  zoom,
  onSelectAsset,
}: RobotFacilityMapProps) {
  const [showPlants, setShowPlants] = useState(true)
  const [showDevices, setShowDevices] = useState(true)
  const [showLabels, setShowLabels] = useState(false)
  const plantCount = useMemo(() => countByKind(scene, 'plant'), [scene])
  const sprinklerCount = useMemo(() => countByKind(scene, 'sprinkler'), [scene])

  return (
    <>
      <div className="robot-facility-map" style={{ transform: `scale(${zoom})` }}>
        <div className="robot-facility-map__surface">
          <div className="robot-facility-map__boundary" />
          {scene.rowGuides.map((guide) => (
            <div
              className="robot-facility-map__row-guide"
              key={guide.id}
              style={{ left: toPercent(scene, guide.value, 0).left }}
            >
              <span>{guide.label}</span>
            </div>
          ))}
          {scene.laneGuides.map((guide) => (
            <div
              className={`robot-facility-map__lane-guide${
                guide.id === 'lane-mid' ? ' robot-facility-map__lane-guide--primary' : ''
              }`}
              key={guide.id}
              style={{ top: toPercent(scene, 0, guide.value).top }}
            >
              <span>{guide.label}</span>
            </div>
          ))}

          {scene.assets.map((asset) => {
            if (asset.kind === 'plant' && !showPlants) {
              return null
            }
            if (asset.kind === 'sprinkler' && !showDevices) {
              return null
            }

            const isSelected = selectedAssetId === asset.id
            const isTarget = targetAssetId === asset.id
            const style = toPercent(scene, asset.position.x, asset.position.y)

            return (
              <button
                className={`robot-facility-map__asset robot-facility-map__asset--${asset.kind}${
                  isSelected ? ' is-selected' : ''
                }${isTarget ? ' is-target' : ''}${
                  asset.status === 'attention' ? ' is-attention' : ''
                }`}
                key={asset.id}
                onClick={() => {
                  onSelectAsset(asset.id)
                }}
                style={style}
                type="button"
              >
                <span className="robot-facility-map__asset-icon">
                  <AppIcon name={asset.kind === 'plant' ? 'potted_plant' : 'water_drop'} />
                </span>
                <span className="robot-facility-map__asset-label">
                  {showLabels || isSelected || isTarget ? asset.label : asset.shortLabel}
                </span>
              </button>
            )
          })}

          <div className="robot-facility-map__robot" style={toPercent(scene, pose.x, pose.y)}>
            <span className="robot-facility-map__robot-ring" />
            <span className="robot-facility-map__robot-core">
              <AppIcon filled name="navigation" />
            </span>
          </div>
        </div>
      </div>

      <div className="robot-facility-map__legend">
        <span className="robot-facility-map__legend-chip">식물 {plantCount}주</span>
        <span className="robot-facility-map__legend-chip">급수 포인트 {sprinklerCount}개</span>
        <span className="robot-facility-map__legend-chip">좌표계 map 기준 배치</span>
      </div>

      <div className="robot-facility-map__toggles">
        <button
          className={`ghost-chip${showPlants ? ' ghost-chip--active' : ''}`}
          onClick={() => {
            setShowPlants((current) => !current)
          }}
          type="button"
        >
          식물
        </button>
        <button
          className={`ghost-chip${showDevices ? ' ghost-chip--active' : ''}`}
          onClick={() => {
            setShowDevices((current) => !current)
          }}
          type="button"
        >
          급수
        </button>
        <button
          className={`ghost-chip${showLabels ? ' ghost-chip--active' : ''}`}
          onClick={() => {
            setShowLabels((current) => !current)
          }}
          type="button"
        >
          라벨
        </button>
      </div>
    </>
  )
}

export function summarizeSelectedAsset(asset: SemanticAsset | null) {
  if (!asset) {
    return {
      title: '선택한 요소 없음',
      subtitle: '지도에서 식물이나 급수 포인트를 선택해 세부 정보를 확인합니다.',
      chips: ['semantic layer 대기'],
    }
  }

  const chips = [
    asset.kind === 'plant' ? '작물' : '설비',
    `zone ${asset.zoneId}`,
    `x ${asset.position.x.toFixed(1)} / y ${asset.position.y.toFixed(1)}`,
  ]

  if (asset.linkedId) {
    chips.push(asset.linkedId)
  }

  return {
    title: asset.label,
    subtitle: asset.description,
    chips,
  }
}
