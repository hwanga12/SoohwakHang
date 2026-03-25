import { AppIcon } from '@/components/app-icon'
import {
  type SemanticAsset,
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
        <linearGradient id="farmRobotTopGradient" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#ffe9a8" />
          <stop offset="100%" stopColor="#f3c96a" />
        </linearGradient>
        <linearGradient id="farmRobotFrontGradient" x1="0%" x2="0%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#f4c45f" />
          <stop offset="100%" stopColor="#d79843" />
        </linearGradient>
        <linearGradient id="farmRobotSideGradient" x1="0%" x2="0%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#e7b456" />
          <stop offset="100%" stopColor="#c68635" />
        </linearGradient>
        <linearGradient id="farmRobotTrackGradient" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#6687bb" />
          <stop offset="100%" stopColor="#425d91" />
        </linearGradient>
        <linearGradient id="farmRobotScreenGradient" x1="0%" x2="100%" y1="0%" y2="100%">
          <stop offset="0%" stopColor="#2f1642" />
          <stop offset="55%" stopColor="#322d6f" />
          <stop offset="100%" stopColor="#0f2438" />
        </linearGradient>
        <radialGradient id="farmRobotScreenGlow" cx="50%" cy="45%" r="70%">
          <stop offset="0%" stopColor="rgba(238, 122, 255, 0.85)" />
          <stop offset="100%" stopColor="rgba(90, 165, 255, 0)" />
        </radialGradient>
      </defs>
      <ellipse className="robot-facility-map__robot-shadow" cx="58" cy="102" rx="38" ry="9" />
      <path className="robot-facility-map__robot-track" d="M17 46 C19 37 27 32 38 34 L47 36 L47 88 L29 92 C21 91 16 84 16 74 Z" fill="url(#farmRobotTrackGradient)" />
      <path className="robot-facility-map__robot-track" d="M75 39 L85 33 C94 31 102 35 105 43 L106 75 C105 84 99 91 91 92 L75 89 Z" fill="url(#farmRobotTrackGradient)" />
      <circle className="robot-facility-map__robot-track-roller" cx="29" cy="49" r="5.8" />
      <circle className="robot-facility-map__robot-track-roller" cx="30" cy="65" r="5.8" />
      <circle className="robot-facility-map__robot-track-roller" cx="30" cy="81" r="5.8" />
      <circle className="robot-facility-map__robot-track-roller" cx="89" cy="47" r="5.8" />
      <circle className="robot-facility-map__robot-track-roller" cx="91" cy="63" r="5.8" />
      <circle className="robot-facility-map__robot-track-roller" cx="92" cy="79" r="5.8" />
      <polygon className="robot-facility-map__robot-body-top" fill="url(#farmRobotTopGradient)" points="42,18 82,26 68,39 28,31" />
      <polygon className="robot-facility-map__robot-body-front" fill="url(#farmRobotFrontGradient)" points="28,31 68,39 68,81 28,71" />
      <polygon className="robot-facility-map__robot-body-side" fill="url(#farmRobotSideGradient)" points="68,39 82,26 84,66 68,81" />
      <polygon className="robot-facility-map__robot-screen" fill="url(#farmRobotScreenGradient)" points="34,38 62,44 62,71 34,65" />
      <ellipse className="robot-facility-map__robot-screen-glow" cx="48" cy="54" rx="14" ry="12" fill="url(#farmRobotScreenGlow)" />
      <path className="robot-facility-map__robot-screen-eye" d="M41 50 C44 46 47 46 49 49" />
      <path className="robot-facility-map__robot-screen-eye" d="M49 58 C52 55 56 55 58 58" />
      <circle className="robot-facility-map__robot-screen-blush" cx="40" cy="58" r="2.3" />
      <circle className="robot-facility-map__robot-screen-blush" cx="57" cy="63" r="2.3" />
      <path className="robot-facility-map__robot-screen-smile" d="M44 63 C47 66 52 66 55 62" />
      <path className="robot-facility-map__robot-top-highlight" d="M46 23 L74 29" />
      <path className="robot-facility-map__robot-antenna" d="M61 20 L65 9" />
      <circle className="robot-facility-map__robot-antenna-top" cx="66" cy="8" r="4.2" />
      <path className="robot-facility-map__robot-leaf-badge" d="M51 23 C56 17 63 17 67 23 C61 28 54 28 51 23Z" />
      <circle className="robot-facility-map__robot-camera" cx="74" cy="44" r="4.6" />
      <path className="robot-facility-map__robot-arm" d="M84 67 L98 72 L102 78" />
      <path className="robot-facility-map__robot-arm-tip" d="M101 77 L106 74 M101 77 L104 83" />
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

        <div className="robot-facility-map__robot" style={toPercent(scene, pose.x, pose.y)}>
          <span className="robot-facility-map__robot-ring" />
          <span className="robot-facility-map__robot-core">
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
