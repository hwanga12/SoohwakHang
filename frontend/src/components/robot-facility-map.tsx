import {
  type CSSProperties,
  type MouseEvent,
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { AppIcon } from '@/components/app-icon'
import { env } from '@/config/env'
import {
  type RobotMapData,
  type RobotPoseSnapshot,
  type RobotTargetPose,
} from '@/lib/api/agribot'
import { areRobotPosesEqual } from '@/lib/robot-map/render-stability'
import { parsePgm, type ParsedPgm } from '@/lib/robot-map/pgm'
import {
  type SemanticAsset,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'
import { type NavigationPreviewPoint } from '@/lib/robot-map/navigation-preview'

type RobotFacilityMapProps = {
  map?: RobotMapData
  pose: RobotTargetPose | RobotPoseSnapshot
  scene: SemanticScene
  selectedAssetId: string | null
  targetAssetId: string | null
  pendingTarget?: RobotTargetPose | null
  pendingTargetMarker?: RobotTargetPose | null
  activeCommandTarget?: RobotTargetPose | null
  activeCommandTargetMarker?: RobotTargetPose | null
  pendingTargetLabel?: string
  activeCommandTargetLabel?: string
  previewPath?: NavigationPreviewPoint[] | null
  zoom: number
  onSelectAsset: (assetId: string) => void
  onSelectGuide?: (guideId: string) => void
  onSelectMapTarget?: (target: RobotTargetPose) => void
  onMapClickFeedback?: (message: string) => void
}

type OverlayPercent = {
  left: string
  top: string
}

type AssetRenderItem = {
  asset: SemanticAsset
  style: OverlayPercent
  isSelected: boolean
  isTarget: boolean
  label: string
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function countByKind(scene: SemanticScene, kind: SemanticAsset['kind']) {
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

function sceneToPercent(scene: SemanticScene, xValue: number, yValue: number) {
  const width = scene.bounds.maxX - scene.bounds.minX
  const height = scene.bounds.maxY - scene.bounds.minY

  return {
    left: `${clamp(((xValue - scene.bounds.minX) / width) * 100, 0, 100)}%`,
    top: `${clamp((1 - ((yValue - scene.bounds.minY) / height)) * 100, 0, 100)}%`,
  }
}

function worldToPercent(map: RobotMapData, xValue: number, yValue: number) {
  const pixelX = (xValue - map.origin.x) / map.resolution
  const pixelY = map.height - (yValue - map.origin.y) / map.resolution

  return {
    left: `${clamp((pixelX / map.width) * 100, 0, 100)}%`,
    top: `${clamp((pixelY / map.height) * 100, 0, 100)}%`,
  }
}

function toOverlayPercent(
  scene: SemanticScene,
  map: RobotMapData | undefined,
  xValue: number,
  yValue: number,
): OverlayPercent {
  return map ? worldToPercent(map, xValue, yValue) : sceneToPercent(scene, xValue, yValue)
}

function parsePercentValue(value: string) {
  const parsed = Number.parseFloat(value.replace('%', ''))
  return Number.isFinite(parsed) ? parsed : 0
}

function findNearestAssetByPointer(
  assetItems: AssetRenderItem[],
  {
    offsetX,
    offsetY,
    rectWidth,
    rectHeight,
  }: {
    offsetX: number
    offsetY: number
    rectWidth: number
    rectHeight: number
  },
): SemanticAsset | null {
  if (assetItems.length === 0 || rectWidth <= 0 || rectHeight <= 0) {
    return null
  }

  const selectionRadiusPx = clamp(Math.min(rectWidth, rectHeight) * 0.08, 28, 42)
  let nearestAsset: SemanticAsset | null = null
  let nearestDistance = Number.POSITIVE_INFINITY

  for (const item of assetItems) {
    const centerX = (parsePercentValue(item.style.left) / 100) * rectWidth
    const centerY = (parsePercentValue(item.style.top) / 100) * rectHeight
    const distance = Math.hypot(centerX - offsetX, centerY - offsetY)

    if (distance <= selectionRadiusPx && distance < nearestDistance) {
      nearestAsset = item.asset
      nearestDistance = distance
    }
  }

  return nearestAsset
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

function buttonLabelForAsset(asset: SemanticAsset, showFullLabel: boolean) {
  if (asset.kind !== 'plant') {
    return showFullLabel ? asset.label : asset.shortLabel
  }

  const numericLabel =
    asset.shortLabel.match(/\d+/)?.[0]
    ?? asset.label.match(/\d+/)?.[0]
    ?? asset.shortLabel
    ?? asset.label

  return numericLabel
}

const PlantGlyph = memo(function PlantGlyph({
  status,
}: {
  status: SemanticAsset['status']
}) {
  const badgeIcon = status === 'handled' ? 'task_alt' : null

  return (
    <span className={`robot-facility-map__tomato-glyph robot-facility-map__tomato-glyph--${status}`}>
      <span className="robot-facility-map__tomato-shadow" />
      <span className="robot-facility-map__tomato-body" />
      <span className="robot-facility-map__tomato-calyx" />
      <span className="robot-facility-map__tomato-leaf robot-facility-map__tomato-leaf--left" />
      <span className="robot-facility-map__tomato-leaf robot-facility-map__tomato-leaf--mid" />
      <span className="robot-facility-map__tomato-leaf robot-facility-map__tomato-leaf--right" />
      {status === 'attention' ? (
        <>
          <span className="robot-facility-map__tomato-bruise" />
          <span className="robot-facility-map__asset-alert-dot" />
        </>
      ) : null}
      {badgeIcon ? (
        <span className="robot-facility-map__asset-badge robot-facility-map__asset-badge--handled">
          <AppIcon filled={status === 'attention'} name={badgeIcon} />
        </span>
      ) : null}
    </span>
  )
})

const SprinklerGlyph = memo(function SprinklerGlyph({
  status,
}: {
  status: SemanticAsset['status']
}) {
  const badgeIcon = status === 'handled' ? 'task_alt' : null

  return (
    <span className={`robot-facility-map__sprinkler-glyph robot-facility-map__sprinkler-glyph--${status}`}>
      <span className="robot-facility-map__sprinkler-base" />
      <span className="robot-facility-map__sprinkler-neck" />
      <span className="robot-facility-map__sprinkler-head">
        <AppIcon name="water_drop" />
      </span>
      {status === 'attention' ? <span className="robot-facility-map__asset-alert-dot robot-facility-map__asset-alert-dot--sprinkler" /> : null}
      {badgeIcon ? (
        <span className="robot-facility-map__asset-badge robot-facility-map__asset-badge--sprinkler robot-facility-map__asset-badge--handled">
          <AppIcon filled={status === 'attention'} name={badgeIcon} />
        </span>
      ) : null}
    </span>
  )
})

const FieldRobotGlyph = memo(function FieldRobotGlyph() {
  return (
    <svg
      aria-hidden="true"
      className="robot-facility-map__robot-svg"
      viewBox="0 0 120 120"
    >
      <defs>
        <radialGradient id="farmRobotBodyGlow" cx="50%" cy="32%" r="72%">
          <stop offset="0%" stopColor="rgba(255, 252, 204, 0.96)" />
          <stop offset="62%" stopColor="rgba(255, 232, 133, 0.44)" />
          <stop offset="100%" stopColor="rgba(255, 232, 133, 0)" />
        </radialGradient>
        <linearGradient id="farmRobotShellRimGradient" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#f0a84b" />
          <stop offset="50%" stopColor="#d88432" />
          <stop offset="100%" stopColor="#b6681f" />
        </linearGradient>
        <linearGradient id="farmRobotShellGradient" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#fff8b8" />
          <stop offset="40%" stopColor="#ffe15b" />
          <stop offset="100%" stopColor="#f4ab3c" />
        </linearGradient>
        <linearGradient id="farmRobotTrackOuterGradient" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#95aff2" />
          <stop offset="100%" stopColor="#536fbf" />
        </linearGradient>
        <linearGradient id="farmRobotTrackInnerGradient" x1="0%" x2="0%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#4d61a5" />
          <stop offset="100%" stopColor="#354579" />
        </linearGradient>
        <linearGradient id="farmRobotGlossGradient" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="rgba(255, 255, 255, 0.9)" />
          <stop offset="55%" stopColor="rgba(255, 255, 255, 0.28)" />
          <stop offset="100%" stopColor="rgba(255, 255, 255, 0)" />
        </linearGradient>
      </defs>
      <ellipse className="robot-facility-map__robot-shadow" cx="60" cy="104" rx="36" ry="9" />
      <path className="robot-facility-map__robot-track" d="M15 18 C15 14 18 11 22 11 H37 L35 100 H22 C18 100 15 97 15 93 Z" fill="url(#farmRobotTrackOuterGradient)" />
      <path className="robot-facility-map__robot-track" d="M83 11 H98 C102 11 105 14 105 18 V93 C105 97 102 100 98 100 H85 Z" fill="url(#farmRobotTrackOuterGradient)" />
      <path className="robot-facility-map__robot-track-inner" d="M21 18 H33 L31 94 H21 Z" fill="url(#farmRobotTrackInnerGradient)" />
      <path className="robot-facility-map__robot-track-inner" d="M87 18 H99 V94 H89 Z" fill="url(#farmRobotTrackInnerGradient)" />
      <path className="robot-facility-map__robot-track-rib" d="M20 29 H34" />
      <path className="robot-facility-map__robot-track-rib" d="M20 40 H33" />
      <path className="robot-facility-map__robot-track-rib" d="M19 51 H33" />
      <path className="robot-facility-map__robot-track-rib" d="M19 62 H33" />
      <path className="robot-facility-map__robot-track-rib" d="M19 73 H32" />
      <path className="robot-facility-map__robot-track-rib" d="M19 84 H32" />
      <path className="robot-facility-map__robot-track-rib" d="M87 29 H100" />
      <path className="robot-facility-map__robot-track-rib" d="M87 40 H101" />
      <path className="robot-facility-map__robot-track-rib" d="M87 51 H101" />
      <path className="robot-facility-map__robot-track-rib" d="M88 62 H101" />
      <path className="robot-facility-map__robot-track-rib" d="M88 73 H101" />
      <path className="robot-facility-map__robot-track-rib" d="M88 84 H101" />
      <circle className="robot-facility-map__robot-track-roller" cx="28" cy="92" r="5.5" />
      <circle className="robot-facility-map__robot-track-roller" cx="92" cy="92" r="5.5" />
      <rect className="robot-facility-map__robot-shell-rim" fill="url(#farmRobotShellRimGradient)" height="90" rx="17" width="54" x="33" y="10" />
      <rect className="robot-facility-map__robot-shell" fill="url(#farmRobotShellGradient)" height="82" rx="14" width="46" x="37" y="14" />
      <rect className="robot-facility-map__robot-body-glow" fill="url(#farmRobotBodyGlow)" height="74" rx="12" width="38" x="41" y="17" />
      <path className="robot-facility-map__robot-shell-shadow" d="M41 73 C48 80 72 80 79 73 V88 C73 94 47 94 41 88Z" />
      <path className="robot-facility-map__robot-gloss robot-facility-map__robot-gloss--primary" d="M45 18 C53 14 66 14 78 20 C72 35 64 52 52 79 C45 62 41 40 45 18Z" fill="url(#farmRobotGlossGradient)" />
      <path className="robot-facility-map__robot-gloss robot-facility-map__robot-gloss--secondary" d="M60 17 C69 17 76 20 80 24 C73 35 66 49 59 65 C58 52 58 35 60 17Z" fill="url(#farmRobotGlossGradient)" />
      <path className="robot-facility-map__robot-front-mark" d="M48 30 L56 36 L48 42" />
      <path className="robot-facility-map__robot-front-mark" d="M72 30 L64 36 L72 42" />
      <path className="robot-facility-map__robot-shell-edge" d="M40 28 C47 24 73 24 80 28" />
      <path className="robot-facility-map__robot-shell-edge robot-facility-map__robot-shell-edge--bottom" d="M42 88 C50 92 70 92 78 88" />
    </svg>
  )
})

function headingDegreesForPose(pose: RobotTargetPose | RobotPoseSnapshot) {
  if ('yawDeg' in pose) {
    return pose.yawDeg ?? 0
  }

  return (pose.yaw * 180) / Math.PI
}

function rotationDegreesForPose(pose: RobotTargetPose | RobotPoseSnapshot) {
  // The SVG is drawn with the robot front facing upward, while map yaw 0 points to +X.
  return 90 - headingDegreesForPose(pose)
}

function areRobotFacilityMapPropsEqual(
  previous: RobotFacilityMapProps,
  next: RobotFacilityMapProps,
) {
  return (
    previous.zoom === next.zoom
    && previous.selectedAssetId === next.selectedAssetId
    && previous.targetAssetId === next.targetAssetId
    && previous.onSelectAsset === next.onSelectAsset
    && previous.onSelectGuide === next.onSelectGuide
    && previous.onSelectMapTarget === next.onSelectMapTarget
    && previous.onMapClickFeedback === next.onMapClickFeedback
    && previous.pendingTargetLabel === next.pendingTargetLabel
    && previous.activeCommandTargetLabel === next.activeCommandTargetLabel
    && previous.map === next.map
    && previous.scene === next.scene
    && previous.previewPath === next.previewPath
    && areRobotPosesEqual(previous.pose, next.pose)
    && areRobotPosesEqual(previous.pendingTarget, next.pendingTarget)
    && areRobotPosesEqual(previous.pendingTargetMarker, next.pendingTargetMarker)
    && areRobotPosesEqual(previous.activeCommandTarget, next.activeCommandTarget)
    && areRobotPosesEqual(previous.activeCommandTargetMarker, next.activeCommandTargetMarker)
  )
}

export const RobotFacilityMap = memo(function RobotFacilityMap({
  map,
  pose,
  scene,
  selectedAssetId,
  targetAssetId,
  pendingTarget = null,
  pendingTargetMarker = null,
  activeCommandTarget = null,
  activeCommandTargetMarker = null,
  pendingTargetLabel = '선택한 후보',
  activeCommandTargetLabel = '실행 중 목표',
  previewPath = null,
  zoom,
  onSelectAsset,
  onSelectGuide,
  onSelectMapTarget,
  onMapClickFeedback,
}: RobotFacilityMapProps) {
  const [showPlants, setShowPlants] = useState(true)
  const [showDevices, setShowDevices] = useState(true)
  const [showLabels, setShowLabels] = useState(false)
  const [isResizing, setIsResizing] = useState(false)
  const [parsedMap, setParsedMap] = useState<ParsedPgm | null>(null)
  const [mapLoadError, setMapLoadError] = useState<string | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const surfaceRef = useRef<HTMLDivElement | null>(null)
  const plantCount = useMemo(() => countByKind(scene, 'plant'), [scene])
  const sprinklerCount = useMemo(() => countByKind(scene, 'sprinkler'), [scene])
  const robotStyle: CSSProperties = useMemo(
    () => toOverlayPercent(scene, map, pose.x, pose.y),
    [map, pose.x, pose.y, scene],
  )
  const robotCoreStyle: CSSProperties = {
    transform: `translate(-50%, -50%) rotate(${rotationDegreesForPose(pose)}deg)`,
  }
  const showPendingTarget = pendingTarget !== null && !areRobotPosesEqual(pendingTarget, activeCommandTarget)
  const visiblePendingTarget = showPendingTarget ? pendingTarget : null
  const visiblePendingTargetMarker = showPendingTarget ? (pendingTargetMarker ?? pendingTarget) : null
  const visibleActiveCommandTargetMarker = activeCommandTargetMarker ?? activeCommandTarget

  useEffect(() => {
    let timeoutId = 0

    const handleResize = () => {
      setIsResizing(true)
      window.clearTimeout(timeoutId)
      timeoutId = window.setTimeout(() => {
        setIsResizing(false)
      }, 180)
    }

    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      window.clearTimeout(timeoutId)
    }
  }, [])

  const rowGuideItems = useMemo(
    () => scene.rowGuides.map((guide) => ({
      guide,
      style: {
        left: toOverlayPercent(
          scene,
          map,
          guide.value,
          map?.origin.y ?? scene.bounds.minY,
        ).left,
      } satisfies CSSProperties,
    })),
    [map, scene],
  )
  const assetItems = useMemo(
    () =>
      scene.assets
        .filter((asset) => {
          if (!map) {
            return true
          }
          if (asset.kind === 'plant' && !showPlants) {
            return false
          }
          if (asset.kind === 'sprinkler' && !showDevices) {
            return false
          }
          return true
        })
        .map((asset) => ({
          asset,
          style: toOverlayPercent(scene, map, asset.position.x, asset.position.y),
          isSelected: selectedAssetId === asset.id,
          isTarget: targetAssetId === asset.id,
          label:
            isResizing && selectedAssetId !== asset.id && targetAssetId !== asset.id
              ? ''
              : buttonLabelForAsset(asset, showLabels),
        })),
    [isResizing, map, scene, selectedAssetId, showDevices, showLabels, showPlants, targetAssetId],
  )
  const previewPathPolyline = useMemo(() => {
    if (!previewPath || previewPath.length < 2) {
      return ''
    }

    return previewPath
      .map((point) => {
        const overlayPoint = toOverlayPercent(scene, map, point.x, point.y)
        return `${parsePercentValue(overlayPoint.left)},${parsePercentValue(overlayPoint.top)}`
      })
      .join(' ')
  }, [map, previewPath, scene])

  useEffect(() => {
    if (!map) {
      setParsedMap(null)
      setMapLoadError(null)
      return
    }

    let cancelled = false
    const controller = new AbortController()
    const activeMap = map

    async function loadRawMap() {
      if (!activeMap.imageUrl) {
        setParsedMap(null)
        setMapLoadError('정적 지도 원본 경로가 아직 준비되지 않았습니다.')
        return
      }

      try {
        const response = await fetch(resolveMapImageUrl(activeMap.imageUrl), {
          signal: controller.signal,
          headers: {
            Accept: 'image/x-portable-graymap',
          },
        })
        if (!response.ok) {
          throw new Error(`지도 원본을 불러오지 못했습니다. (${response.status})`)
        }

        const buffer = await response.arrayBuffer()
        const nextParsedMap = parsePgm(buffer)
        if (cancelled) {
          return
        }
        setParsedMap(nextParsedMap)
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
  }, [map])

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

  function handleSurfaceClick(event: MouseEvent<HTMLDivElement>) {
    if (!surfaceRef.current) {
      return
    }

    const rect = surfaceRef.current.getBoundingClientRect()
    const offsetX = event.clientX - rect.left
    const offsetY = event.clientY - rect.top

    if (offsetX < 0 || offsetY < 0 || offsetX > rect.width || offsetY > rect.height) {
      return
    }

    const nearestAsset = findNearestAssetByPointer(assetItems, {
      offsetX,
      offsetY,
      rectWidth: rect.width,
      rectHeight: rect.height,
    })
    if (nearestAsset) {
      onSelectAsset(nearestAsset.id)
      return
    }

    if (!map || !onSelectMapTarget) {
      return
    }

    if (!parsedMap) {
      onMapClickFeedback?.('정적 지도를 불러오는 중입니다. 잠시 후 다시 눌러 주세요.')
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
    target.yaw = 'yaw' in pose ? pose.yaw : ((pose.yawDeg ?? 0) * Math.PI) / 180
    onSelectMapTarget(target)
  }

  return (
    <>
      <div className={`robot-facility-map${isResizing ? ' is-resizing' : ''}`} style={{ transform: `scale(${zoom})` }}>
        <div
          className={`robot-facility-map__surface${mapLoadError ? ' is-fallback' : ''}`}
          onClick={handleSurfaceClick}
          ref={surfaceRef}
        >
          {map ? (
            <canvas
              className="robot-facility-map__canvas"
              height={parsedMap?.height ?? map.height}
              ref={canvasRef}
              width={parsedMap?.width ?? map.width}
            />
          ) : null}

          {rowGuideItems.map(({ guide, style }) => {

            if (!onSelectGuide) {
              return <div aria-hidden="true" className="robot-facility-map__row-guide" key={guide.id} style={style} />
            }

            return (
              <button
                aria-label={guide.label}
                className="robot-facility-map__row-guide is-clickable"
                key={guide.id}
                onClick={(event) => {
                  event.stopPropagation()
                  onSelectGuide(guide.id)
                }}
                style={style}
                title={guide.label}
                type="button"
              />
            )
          })}

          {assetItems.map(({ asset, style, isSelected, isTarget, label }) => {
            return (
              <button
                className={`robot-facility-map__asset robot-facility-map__asset--${asset.kind}${
                  isSelected ? ' is-selected' : ''
                }${isTarget ? ' is-target' : ''}${asset.status === 'attention' ? ' is-attention' : ''}${
                  asset.status === 'handled' ? ' is-handled' : ''
                }`}
                key={asset.id}
                onClick={() => {
                  onSelectAsset(asset.id)
                }}
                style={style}
                type="button"
              >
                <span className="robot-facility-map__asset-icon">
                  {asset.kind === 'plant' ? (
                    <PlantGlyph status={asset.status} />
                  ) : (
                    <SprinklerGlyph status={asset.status} />
                  )}
                </span>
                {label ? <span className="robot-facility-map__asset-label">{label}</span> : null}
              </button>
            )
          })}

          {previewPathPolyline ? (
            <svg aria-hidden="true" className="robot-facility-map__path-overlay" viewBox="0 0 100 100" preserveAspectRatio="none">
              <polyline className="robot-facility-map__path-line" points={previewPathPolyline} />
            </svg>
          ) : null}

          {activeCommandTarget ? (() => {
            const activeMarker = visibleActiveCommandTargetMarker ?? activeCommandTarget
            return (
              <div
                className="robot-facility-map__target robot-facility-map__target--active"
                style={toOverlayPercent(
                  scene,
                  map,
                  activeMarker.x,
                  activeMarker.y,
                )}
              >
                <span className="robot-facility-map__target-dot" />
                <span className="robot-facility-map__target-label">{activeCommandTargetLabel}</span>
              </div>
            )
          })() : null}

          {visiblePendingTarget && visiblePendingTargetMarker ? (
            <div
              className="robot-facility-map__target robot-facility-map__target--pending"
              style={toOverlayPercent(
                scene,
                map,
                visiblePendingTargetMarker.x,
                visiblePendingTargetMarker.y,
              )}
            >
              <span className="robot-facility-map__target-dot" />
              <span className="robot-facility-map__target-label">{pendingTargetLabel}</span>
            </div>
          ) : null}

          <div className="robot-facility-map__robot" style={robotStyle}>
            <span className="robot-facility-map__robot-ping robot-facility-map__robot-ping--outer" />
            <span className="robot-facility-map__robot-core" style={robotCoreStyle}>
              <FieldRobotGlyph />
            </span>
          </div>

          {map && onSelectMapTarget ? (
            <div className="robot-facility-map__hint">
              <strong>이동 목표 지정</strong>
              <p>빈 지도는 좌표 직접 지정, 식물 아이콘은 작물 중심 대신 안전 관측 후보를 계산합니다.</p>
            </div>
          ) : null}

          {mapLoadError ? (
            <div className="robot-facility-map__status">
              <strong>정적 지도 원본을 아직 그리지 못했습니다.</strong>
              <p>{mapLoadError}</p>
            </div>
          ) : null}
        </div>

        {map ? (
          <>
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
          </>
        ) : null}
      </div>
    </>
  )
}, areRobotFacilityMapPropsEqual)

export function summarizeSelectedAsset(asset: SemanticAsset | null) {
  if (!asset) {
    return {
      title: '선택한 요소 없음',
      subtitle: '지도에서 식물이나 급수 포인트를 선택해 세부 정보를 확인합니다.',
      chips: ['semantic layer 대기'],
    }
  }

  const chips = [
    asset.kind === 'plant' ? '작물' : '급수 헤드',
    `zone ${asset.zoneId}`,
    `x ${asset.position.x.toFixed(1)} / y ${asset.position.y.toFixed(1)}`,
  ]

  if (asset.approachPose) {
    chips.push(`접근 x ${asset.approachPose.x.toFixed(2)} / y ${asset.approachPose.y.toFixed(2)}`)
  } else if (asset.navigationPose) {
    chips.push(`이동 x ${asset.navigationPose.x.toFixed(2)} / y ${asset.navigationPose.y.toFixed(2)}`)
  }

  if (asset.inspectWaypointName) {
    chips.push(asset.inspectWaypointName)
  }

  if (asset.status === 'attention') {
    chips.unshift('조치 필요')
  } else if (asset.status === 'target') {
    chips.unshift('수확 후보')
  }

  if (asset.linkedId) {
    chips.push(asset.linkedId)
  }

  return {
    title: asset.label,
    subtitle: asset.description,
    chips,
  }
}
