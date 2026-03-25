import type { CSSProperties } from 'react'
import { AppIcon } from '@/components/app-icon'
import {
  type SemanticAsset,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'

type RobotFacilityMapProps = {
  pose: {
    x: number
    y: number
    yawDeg?: number
  }
  scene: SemanticScene
  selectedAssetId: string | null
  targetAssetId: string | null
  zoom: number
  onSelectAsset: (assetId: string) => void
  onSelectGuide?: (guideId: string) => void
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

function assetFlag(asset: SemanticAsset) {
  if (asset.status === 'attention') {
    return {
      label: '조치 필요',
      tone: 'danger',
    } as const
  }

  if (asset.status === 'handled') {
    return {
      label: '조치 완료',
      tone: 'accent',
    } as const
  }

  if (asset.status === 'target') {
    return {
      label: '수확 후보',
      tone: 'warning',
    } as const
  }

  return null
}

function PlantGlyph({
  status,
}: {
  status: SemanticAsset['status']
}) {
  const badgeIcon = status === 'attention' ? 'warning' : status === 'handled' ? 'task_alt' : null

  return (
    <span className={`robot-facility-map__tomato-glyph robot-facility-map__tomato-glyph--${status}`}>
      <span className="robot-facility-map__tomato-shadow" />
      <span className="robot-facility-map__tomato-body" />
      <span className="robot-facility-map__tomato-shine" />
      <span className="robot-facility-map__tomato-calyx" />
      <span className="robot-facility-map__tomato-leaf robot-facility-map__tomato-leaf--left" />
      <span className="robot-facility-map__tomato-leaf robot-facility-map__tomato-leaf--mid" />
      <span className="robot-facility-map__tomato-leaf robot-facility-map__tomato-leaf--right" />
      {status === 'target' ? <span className="robot-facility-map__tomato-sparkle" /> : null}
      {status === 'attention' ? (
        <>
          <span className="robot-facility-map__tomato-bruise" />
          <span className="robot-facility-map__tomato-mold robot-facility-map__tomato-mold--top" />
          <span className="robot-facility-map__tomato-mold robot-facility-map__tomato-mold--bottom" />
        </>
      ) : null}
      {badgeIcon ? (
        <span className="robot-facility-map__asset-badge">
          <AppIcon filled={status === 'attention'} name={badgeIcon} />
        </span>
      ) : null}
    </span>
  )
}

function SprinklerGlyph({
  status,
}: {
  status: SemanticAsset['status']
}) {
  const badgeIcon = status === 'attention' ? 'warning' : status === 'handled' ? 'task_alt' : null

  return (
    <span className={`robot-facility-map__sprinkler-glyph robot-facility-map__sprinkler-glyph--${status}`}>
      <span className="robot-facility-map__sprinkler-base" />
      <span className="robot-facility-map__sprinkler-neck" />
      <span className="robot-facility-map__sprinkler-head">
        <AppIcon name="water_drop" />
      </span>
      {badgeIcon ? (
        <span className="robot-facility-map__asset-badge robot-facility-map__asset-badge--sprinkler">
          <AppIcon filled={status === 'attention'} name={badgeIcon} />
        </span>
      ) : null}
    </span>
  )
}

function FieldRobotGlyph() {
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
        <linearGradient id="farmRobotPanelGradient" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#5d5dce" />
          <stop offset="100%" stopColor="#2a397b" />
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
      <path className="robot-facility-map__robot-shell-edge" d="M40 28 C47 24 73 24 80 28" />
      <path className="robot-facility-map__robot-shell-edge robot-facility-map__robot-shell-edge--bottom" d="M42 88 C50 92 70 92 78 88" />
      <path className="robot-facility-map__robot-arm" d="M82 72 L92 80" />
      <path className="robot-facility-map__robot-arm-tip" d="M91 80 L97 77 M91 80 L96 85" />
    </svg>
  )
}

export function RobotFacilityMap({
  pose,
  scene,
  selectedAssetId,
  targetAssetId,
  zoom,
  onSelectAsset,
  onSelectGuide,
}: RobotFacilityMapProps) {
  const robotStyle: CSSProperties = toPercent(scene, pose.x, pose.y)
  const robotCoreStyle: CSSProperties = {
    transform: `translate(-50%, -50%) rotate(${pose.yawDeg ?? 0}deg)`,
  }

  return (
    <div className="robot-facility-map" style={{ transform: `scale(${zoom})` }}>
      <div className="robot-facility-map__surface">
        <div className="robot-facility-map__boundary" />
        {scene.rowGuides.map((guide) => {
          const className = `robot-facility-map__row-guide${onSelectGuide ? ' is-clickable' : ''}`
          const style = { left: toPercent(scene, guide.value, 0).left }

          if (!onSelectGuide) {
            return (
              <div className={className} key={guide.id} style={style}>
                <span>{guide.label}</span>
              </div>
            )
          }

          return (
            <button
              className={className}
              key={guide.id}
              onClick={() => {
                onSelectGuide(guide.id)
              }}
              style={style}
              type="button"
            >
              <span>{guide.label}</span>
            </button>
          )
        })}
        {scene.laneGuides.map((guide) => (
          <div
            className={`robot-facility-map__lane-guide${guide.id === 'lane-mid' ? ' robot-facility-map__lane-guide--primary' : ''
              }`}
            key={guide.id}
            style={{ top: toPercent(scene, 0, guide.value).top }}
          >
            <span>{guide.label}</span>
          </div>
        ))}

        {scene.assets.map((asset) => {
          const isSelected = selectedAssetId === asset.id
          const isTarget = targetAssetId === asset.id
          const style = toPercent(scene, asset.position.x, asset.position.y)
          const flag = assetFlag(asset)

          return (
            <button
              className={`robot-facility-map__asset robot-facility-map__asset--${asset.kind}${isSelected ? ' is-selected' : ''
                }${isTarget ? ' is-target' : ''}${asset.status === 'attention' ? ' is-attention' : ''
                }${asset.status === 'handled' ? ' is-handled' : ''}`}
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
              <span className="robot-facility-map__asset-label">
                {isSelected || isTarget ? asset.label : asset.shortLabel}
              </span>
              {flag ? (
                <span className={`robot-facility-map__asset-flag robot-facility-map__asset-flag--${flag.tone}`}>
                  {flag.label}
                </span>
              ) : null}
            </button>
          )
        })}

        <div className="robot-facility-map__robot" style={robotStyle}>
          <span className="robot-facility-map__robot-ping robot-facility-map__robot-ping--outer" />
          <span className="robot-facility-map__robot-ping robot-facility-map__robot-ping--inner" />
          <span className="robot-facility-map__robot-origin">
            <span className="robot-facility-map__robot-origin-dot" />
          </span>
          <span className="robot-facility-map__robot-ring" />
          <span className="robot-facility-map__robot-core" style={robotCoreStyle}>
            <FieldRobotGlyph />
          </span>
          <span className="robot-facility-map__robot-label">AGR-02</span>
        </div>
      </div>
    </div>
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
    asset.kind === 'plant' ? '작물' : '급수 헤드',
    `zone ${asset.zoneId}`,
    `x ${asset.position.x.toFixed(1)} / y ${asset.position.y.toFixed(1)}`,
  ]

  if (asset.status === 'attention') {
    chips.unshift('조치 필요')
  } else if (asset.status === 'handled') {
    chips.unshift('조치 완료')
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
