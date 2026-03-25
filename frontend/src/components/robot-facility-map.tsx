import { type MouseEvent, useEffect, useMemo, useRef, useState } from 'react'
import { AppIcon } from '@/components/app-icon'
import { env } from '@/config/env'
import { parsePgm, type ParsedPgm } from '@/lib/robot-map/pgm'
import {
  type RobotMapData,
  type RobotTargetPose,
} from '@/lib/api/agribot'
import {
  type SemanticAsset,
  type SemanticAssetKind,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'

type RobotFacilityMapProps = {
  map: RobotMapData
  pose: RobotTargetPose
  scene: SemanticScene
  selectedAssetId: string | null
  targetAssetId: string | null
  pendingTarget: RobotTargetPose | null
  activeCommandTarget: RobotTargetPose | null
  zoom: number
  onSelectAsset: (assetId: string) => void
  onSelectMapTarget: (target: RobotTargetPose) => void
  onMapClickFeedback?: (message: string) => void
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function countByKind(scene: SemanticScene, kind: SemanticAssetKind) {
  return scene.assets.filter((asset) => asset.kind === kind).length
}

function resolveMapImageUrl(imageUrl: string) {
  if (!imageUrl) {
    return ''
  }
  if (/^https?:\/\//i.test(imageUrl)) {
    return imageUrl
  }

  const apiBase = new URL(env.apiBaseUrl)
  return new URL(imageUrl, `${apiBase.origin}/`).toString()
}

function worldToPercent(map: RobotMapData, xValue: number, yValue: number) {
  const pixelX = (xValue - map.origin.x) / map.resolution
  const pixelY = map.height - (yValue - map.origin.y) / map.resolution

  return {
    left: `${clamp((pixelX / map.width) * 100, 0, 100)}%`,
    top: `${clamp((pixelY / map.height) * 100, 0, 100)}%`,
  }
}

function pixelToWorld(map: RobotMapData, pixelX: number, pixelY: number): RobotTargetPose {
  return {
    x: map.origin.x + pixelX * map.resolution,
    y: map.origin.y + (map.height - pixelY) * map.resolution,
    z: 0,
    yaw: 0,
    frameId: 'map',
  }
}

function occupancyMessage(value: number) {
  if (value < 120) {
    return '벽이나 장애물 영역은 이동 목표로 지정할 수 없습니다.'
  }
  if (value < 220) {
    return '미확인 셀은 시연용 이동 목표로 쓰지 않는 편이 안전합니다.'
  }
  return ''
}

export function RobotFacilityMap({
  map,
  pose,
  scene,
  selectedAssetId,
  targetAssetId,
  pendingTarget,
  activeCommandTarget,
  zoom,
  onSelectAsset,
  onSelectMapTarget,
  onMapClickFeedback,
}: RobotFacilityMapProps) {
  const [showPlants, setShowPlants] = useState(true)
  const [showDevices, setShowDevices] = useState(true)
  const [showLabels, setShowLabels] = useState(false)
  const [parsedMap, setParsedMap] = useState<ParsedPgm | null>(null)
  const [mapLoadError, setMapLoadError] = useState<string | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const surfaceRef = useRef<HTMLDivElement | null>(null)
  const plantCount = useMemo(() => countByKind(scene, 'plant'), [scene])
  const sprinklerCount = useMemo(() => countByKind(scene, 'sprinkler'), [scene])

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    async function loadRawMap() {
      if (!map.imageUrl) {
        setParsedMap(null)
        setMapLoadError('정적 지도 원본 경로가 아직 준비되지 않았습니다.')
        return
      }

      try {
        const response = await fetch(resolveMapImageUrl(map.imageUrl), {
          signal: controller.signal,
          headers: {
            Accept: 'image/x-portable-graymap',
          },
        })
        if (!response.ok) {
          throw new Error(`지도 원본을 불러오지 못했습니다. (${response.status})`)
        }

        const buffer = await response.arrayBuffer()
        const parsed = parsePgm(buffer)
        if (cancelled) {
          return
        }
        setParsedMap(parsed)
        setMapLoadError(null)
      } catch (error) {
        if (controller.signal.aborted || cancelled) {
          return
        }
        setParsedMap(null)
        setMapLoadError(
          error instanceof Error
            ? error.message
            : '정적 지도 원본을 읽지 못했습니다.',
        )
      }
    }

    void loadRawMap()

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [map.imageUrl])

  useEffect(() => {
    if (!canvasRef.current || !parsedMap) {
      return
    }

    const context = canvasRef.current.getContext('2d')
    if (!context) {
      return
    }

    const imageData = context.createImageData(parsedMap.width, parsedMap.height)
    for (let index = 0; index < parsedMap.pixels.length; index += 1) {
      const pixel = parsedMap.pixels[index]
      const offset = index * 4
      imageData.data[offset] = pixel
      imageData.data[offset + 1] = pixel
      imageData.data[offset + 2] = pixel
      imageData.data[offset + 3] = 255
    }

    context.putImageData(imageData, 0, 0)
  }, [parsedMap])

  function handleMapClick(event: MouseEvent<HTMLDivElement>) {
    if (!surfaceRef.current || !parsedMap) {
      onMapClickFeedback?.('정적 지도를 불러오는 중입니다. 잠시 후 다시 눌러 주세요.')
      return
    }

    const rect = surfaceRef.current.getBoundingClientRect()
    const offsetX = event.clientX - rect.left
    const offsetY = event.clientY - rect.top

    if (offsetX < 0 || offsetY < 0 || offsetX > rect.width || offsetY > rect.height) {
      return
    }

    const pixelX = clamp(Math.round((offsetX / rect.width) * parsedMap.width), 0, parsedMap.width - 1)
    const pixelY = clamp(Math.round((offsetY / rect.height) * parsedMap.height), 0, parsedMap.height - 1)
    const occupancy = parsedMap.pixels[pixelY * parsedMap.width + pixelX] ?? 0
    const blockedMessage = occupancyMessage(occupancy)

    if (blockedMessage) {
      onMapClickFeedback?.(blockedMessage)
      return
    }

    const target = pixelToWorld(map, pixelX, pixelY)
    target.yaw = pose.yaw
    onSelectMapTarget(target)
  }

  return (
    <>
      <div className="robot-facility-map" style={{ transform: `scale(${zoom})` }}>
        <div
          className={`robot-facility-map__surface${mapLoadError ? ' is-fallback' : ''}`}
          onClick={handleMapClick}
          ref={surfaceRef}
        >
          <canvas
            className="robot-facility-map__canvas"
            height={parsedMap?.height ?? map.height}
            ref={canvasRef}
            width={parsedMap?.width ?? map.width}
          />
          <div className="robot-facility-map__boundary" />

          {scene.rowGuides.map((guide) => (
            <div
              className="robot-facility-map__row-guide"
              key={guide.id}
              style={{ left: worldToPercent(map, guide.value, map.origin.y).left }}
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
              style={{ top: worldToPercent(map, map.origin.x, guide.value).top }}
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
            const style = worldToPercent(map, asset.position.x, asset.position.y)

            return (
              <button
                className={`robot-facility-map__asset robot-facility-map__asset--${asset.kind}${
                  isSelected ? ' is-selected' : ''
                }${isTarget ? ' is-target' : ''}${
                  asset.status === 'attention' ? ' is-attention' : ''
                }`}
                key={asset.id}
                onClick={(event) => {
                  event.stopPropagation()
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

          {activeCommandTarget ? (
            <div
              className="robot-facility-map__target robot-facility-map__target--active"
              style={worldToPercent(map, activeCommandTarget.x, activeCommandTarget.y)}
            >
              <span className="robot-facility-map__target-dot" />
              <span className="robot-facility-map__target-label">요청 목표</span>
            </div>
          ) : null}

          {pendingTarget ? (
            <div
              className="robot-facility-map__target robot-facility-map__target--pending"
              style={worldToPercent(map, pendingTarget.x, pendingTarget.y)}
            >
              <span className="robot-facility-map__target-dot" />
              <span className="robot-facility-map__target-label">선택 좌표</span>
            </div>
          ) : null}

          <div
            className="robot-facility-map__robot"
            style={{
              ...worldToPercent(map, pose.x, pose.y),
              transform: `translate(-50%, -50%) rotate(${pose.yaw}rad)`,
            }}
          >
            <span className="robot-facility-map__robot-ring" />
            <span className="robot-facility-map__robot-core">
              <AppIcon filled name="navigation" />
            </span>
          </div>

          <div className="robot-facility-map__hint">
            <strong>이동 목표 지정</strong>
            <p>빈 지도 영역을 클릭하면 시연용 목표 좌표가 잡힙니다. 식물과 급수 포인트는 클릭해도 선택만 됩니다.</p>
          </div>

          {mapLoadError ? (
            <div className="robot-facility-map__status">
              <strong>정적 지도 원본을 아직 그리지 못했습니다.</strong>
              <p>{mapLoadError}</p>
            </div>
          ) : null}
        </div>

        <div className="robot-facility-map__legend">
          <span className="robot-facility-map__legend-chip">식물 {plantCount}주</span>
          <span className="robot-facility-map__legend-chip">급수 포인트 {sprinklerCount}개</span>
          <span className="robot-facility-map__legend-chip">occupancy map + semantic overlay</span>
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
