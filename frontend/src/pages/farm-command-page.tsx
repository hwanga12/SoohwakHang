import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createGetSignal, createPostAction } from '@/app/dev-inspector'
import { AppIcon } from '@/components/app-icon'
import { DevSurface } from '@/components/dev-surface'
import { MockupImage } from '@/components/mockup-image'
import {
  RobotFacilityMap,
  summarizeSelectedAsset,
} from '@/components/robot-facility-map'
import {
  approveWateringRecommendation,
  dashboardFallback,
  environmentFallback,
  getDashboardPageData,
  getEnvironmentPageData,
  getHarvestPageData,
  getPlantsPageData,
  getRobotPageData,
  harvestFallback,
  plantsFallback,
  requestHarvestMission,
  robotFallback,
  sendRobotControlAction,
  sendRobotZoneMove,
  startFieldPatrolMission,
  triggerNutrientInjection,
} from '@/lib/api/agribot'
import {
  farmSemanticScene,
  resolveSemanticTargetId,
  type SemanticAssetStatus,
  type SemanticScene,
} from '@/lib/robot-map/farm-semantic-map'

const robotControlActions = [
  { id: 'pause', title: '일시정지', icon: 'pause_circle', nextState: '일시정지' },
  { id: 'resume', title: '재개', icon: 'play_circle', nextState: '재개중' },
  { id: 'home', title: '귀가', icon: 'route', nextState: '귀가중' },
] as const

type ActionRecordTone = 'accent' | 'danger' | 'healthy' | 'warning'

type AssetActionRecord = {
  label: string
  detail: string
  tone: ActionRecordTone
}

type PatrolActionRecord = {
  mode: 'diagnosis' | 'harvest'
  detail: string
}

type PlantModalDetail = {
  id: string
  targetId: string
  name: string
  zoneLabel: string
  positionLabel: string
  recommendedAction: string
  health: number
  status: string
}

function plantNeedsAttention(recommendedAction: string, status: string) {
  return recommendedAction.includes('병') || status.includes('재확인') || status.includes('병')
}

function previewImageForAsset(
  kind?: 'plant' | 'sprinkler',
  status?: 'normal' | 'target' | 'attention' | 'handled',
) {
  if (kind === 'sprinkler') {
    return '/mock-images/robot-camera-preview.png'
  }

  if (status === 'attention') {
    return '/mock-images/disease-closeup.png'
  }

  return '/mock-images/harvest-closeup.png'
}

function selectionTag(
  kind?: 'plant' | 'sprinkler',
  status?: 'normal' | 'target' | 'attention' | 'handled',
) {
  if (status === 'handled') {
    return {
      label: '조치 완료',
      tone: 'accent',
    } as const
  }

  if (status === 'attention') {
    return {
      label: '조치 필요',
      tone: 'danger',
    } as const
  }

  if (kind === 'sprinkler') {
    return {
      label: '급수 헤드',
      tone: 'healthy',
    } as const
  }

  return {
    label: '작물 확인',
    tone: 'warning',
  } as const
}

export function FarmCommandPage() {
  const queryClient = useQueryClient()
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const [selectedPlantId, setSelectedPlantId] = useState<string | null>(null)
  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false)
  const [activityState, setActivityState] = useState<string | null>(null)
  const [uiMessage, setUiMessage] = useState<string | null>(null)
  const [actionRecords, setActionRecords] = useState<Record<string, AssetActionRecord>>({})
  const [lastPatrolAction, setLastPatrolAction] = useState<PatrolActionRecord | null>(null)

  const dashboardQuery = useQuery({
    queryKey: ['page', 'dashboard'],
    queryFn: getDashboardPageData,
    initialData: dashboardFallback,
    refetchInterval: 20_000,
  })
  const robotQuery = useQuery({
    queryKey: ['page', 'robot'],
    queryFn: getRobotPageData,
    initialData: robotFallback,
    refetchInterval: 1_000,
  })
  const plantsQuery = useQuery({
    queryKey: ['page', 'plants'],
    queryFn: getPlantsPageData,
    initialData: plantsFallback,
    refetchInterval: 20_000,
  })
  const environmentQuery = useQuery({
    queryKey: ['page', 'environment'],
    queryFn: getEnvironmentPageData,
    initialData: environmentFallback,
    refetchInterval: 15_000,
  })
  const harvestQuery = useQuery({
    queryKey: ['page', 'harvest'],
    queryFn: getHarvestPageData,
    initialData: harvestFallback,
    refetchInterval: 20_000,
  })

  const zoneMoveMutation = useMutation({
    mutationFn: sendRobotZoneMove,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
    },
  })
  const controlMutation = useMutation({
    mutationFn: sendRobotControlAction,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })
  const harvestMutation = useMutation({
    mutationFn: requestHarvestMission,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'plants'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'harvest'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })
  const patrolMutation = useMutation({
    mutationFn: startFieldPatrolMission,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'robot'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })
  const wateringMutation = useMutation({
    mutationFn: approveWateringRecommendation,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'environment'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })
  const nutrientMutation = useMutation({
    mutationFn: triggerNutrientInjection,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['page', 'environment'] })
      await queryClient.invalidateQueries({ queryKey: ['page', 'dashboard'] })
    },
  })

  const dashboard = dashboardQuery.data
  const robot = robotQuery.data
  const plants = plantsQuery.data
  const environment = environmentQuery.data
  const harvest = harvestQuery.data

  const mapSource = (path: string) => robot.debug.querySources[path] ?? 'fallback'
  const dashboardSource = (path: string) => dashboard.debug.querySources[path] ?? 'fallback'
  const plantsSource = (path: string) => plants.debug.querySources[path] ?? 'fallback'
  const fieldSource = (path: string) => environment.debug.querySources[path] ?? 'fallback'
  const harvestSource = (path: string) => harvest.debug.querySources[path] ?? 'fallback'

  const rememberAction = (
    assetId: string,
    label: string,
    detail: string,
    tone: ActionRecordTone = 'accent',
  ) => {
    setActionRecords((current) => ({
      ...current,
      [assetId]: {
        label,
        detail,
        tone,
      },
    }))
  }

  const robotPose = robot.pose
  const targetAssetId = resolveSemanticTargetId(robot.targetLabel)
  const plantLookup = useMemo(
    () => new Map(plants.plants.map((plant) => [plant.id, plant])),
    [plants.plants],
  )
  const attentionPlant =
    plants.plants.find((plant) => plantNeedsAttention(plant.recommendedAction, plant.status))
    ?? plants.plants[0]
  const harvestPlant =
    plants.plants.find((plant) => plant.status.includes('수확'))
    ?? plants.plants[0]
  const patrolZoneIds = robot.zonePresets.map((preset) => preset.id).filter(Boolean)

  const mapScene = useMemo<SemanticScene>(() => ({
    ...farmSemanticScene,
    assets: farmSemanticScene.assets.map((asset) => {
      const actionRecord = actionRecords[asset.id]

      if (asset.kind === 'plant') {
        const plant = plantLookup.get(asset.id)
        const attention = plant ? plantNeedsAttention(plant.recommendedAction, plant.status) : asset.status === 'attention'
        const harvestTarget = plant ? plant.status.includes('수확') : asset.status === 'target'
        const status: SemanticAssetStatus =
          actionRecord ? 'handled' : attention ? 'attention' : harvestTarget ? 'target' : 'normal'

        return {
          ...asset,
          linkedId: plant?.targetId ?? asset.linkedId,
          label: plant?.name ?? asset.label,
          shortLabel: plant?.name.replace('토마토 ', '') ?? asset.shortLabel,
          description: actionRecord
            ? actionRecord.detail
            : plant
              ? `${plant.status} · ${plant.recommendedAction}`
              : asset.description,
          status,
        }
      }

      const sprinklerIndex = Number(asset.id.replace('sprinkler_', ''))
      const status: SemanticAssetStatus = actionRecord ? 'handled' : 'normal'

      return {
        ...asset,
        label: `${sprinklerIndex}번 급수 헤드`,
        shortLabel: `H${sprinklerIndex}`,
        description: actionRecord
          ? actionRecord.detail
          : '고장 없이 정상 작동하는 급수 포인트입니다.',
        status,
      }
    }),
  }), [actionRecords, plantLookup])

  const selectedAsset = useMemo(
    () => mapScene.assets.find((asset) => asset.id === selectedAssetId) ?? null,
    [mapScene.assets, selectedAssetId],
  )
  const selectedSummary = summarizeSelectedAsset(selectedAsset)
  const selectedActionRecord = selectedAssetId ? actionRecords[selectedAssetId] ?? null : null
  const selectedPlantAsset = selectedAsset?.kind === 'plant' ? selectedAsset : null
  const selectedSprinklerAsset = selectedAsset?.kind === 'sprinkler' ? selectedAsset : null
  const selectedPlantDetail = useMemo<PlantModalDetail | null>(() => {
    const asset =
      selectedAsset?.kind === 'plant'
        ? selectedAsset
        : selectedPlantId
          ? mapScene.assets.find((item) => item.id === selectedPlantId && item.kind === 'plant') ?? null
          : null

    if (!asset || asset.kind !== 'plant') {
      if (!harvestPlant) {
        return null
      }

      return {
        id: harvestPlant.id,
        targetId: harvestPlant.targetId,
        name: harvestPlant.name,
        zoneLabel: harvestPlant.zoneLabel,
        positionLabel: harvestPlant.positionLabel,
        recommendedAction: harvestPlant.recommendedAction,
        health: harvestPlant.health,
        status: harvestPlant.status,
      }
    }

    const plant = plantLookup.get(asset.id)

    if (plant) {
      return {
        id: plant.id,
        targetId: plant.targetId,
        name: plant.name,
        zoneLabel: plant.zoneLabel,
        positionLabel: plant.positionLabel,
        recommendedAction: plant.recommendedAction,
        health: plant.health,
        status: plant.status,
      }
    }

    return {
      id: asset.id,
      targetId: asset.linkedId ?? `${asset.id}_fruit_01`,
      name: asset.label,
      zoneLabel: `zone ${asset.zoneId}`,
      positionLabel: `x ${asset.position.x.toFixed(1)} / y ${asset.position.y.toFixed(1)}`,
      recommendedAction: asset.status === 'target' ? '수확 요청 가능' : '개별 진단 권장',
      health: asset.status === 'attention' ? 62 : asset.status === 'target' ? 91 : 84,
      status: asset.status === 'attention' ? '재확인 필요' : asset.status === 'target' ? '수확 후보' : '관찰 중',
    }
  }, [harvestPlant, mapScene.assets, plantLookup, selectedAsset, selectedPlantId])

  useEffect(() => {
    if (selectedAssetId && mapScene.assets.some((asset) => asset.id === selectedAssetId)) {
      return
    }

    if (targetAssetId) {
      setSelectedAssetId(targetAssetId)
      return
    }

    if (attentionPlant) {
      setSelectedAssetId(attentionPlant.id)
    }
  }, [attentionPlant, mapScene.assets, selectedAssetId, targetAssetId])

  useEffect(() => {
    if (selectedAsset?.kind === 'plant') {
      setSelectedPlantId(selectedAsset.id)
      return
    }

    if (!selectedPlantId && harvestPlant) {
      setSelectedPlantId(harvestPlant.id)
      return
    }

    if (selectedPlantId && !plants.plants.some((plant) => plant.id === selectedPlantId)) {
      setSelectedPlantId(harvestPlant?.id ?? null)
    }
  }, [harvestPlant, plants.plants, selectedAsset, selectedPlantId])

  const weatherSummary = dashboard.environmentStats.length > 0
    ? dashboard.environmentStats.map((stat) => `${stat.label} ${stat.value}`).join(' · ')
    : '날씨 데이터 대기 중'

  const mildewAlertCount = plants.alerts.filter(
    (alert) => alert.id.includes('disease') || alert.title.includes('병'),
  ).length
  const mildewPercent = Math.round((mildewAlertCount / Math.max(plants.plants.length, 1)) * 100)
  const harvestableCount = plants.plants.filter((plant) => plant.status.includes('수확')).length
  const harvestablePercent = Math.round((harvestableCount / Math.max(plants.plants.length, 1)) * 100)
  const harvestProgressPercent = Math.round(
    Number.parseFloat(
      (harvest.metrics.find((metric) => metric.label.includes('성공'))?.value ?? '95%').replace(
        /[^\d.]/g,
        '',
      ),
    ),
  )
  const lastPlantAction =
    [...Object.entries(actionRecords)].reverse().find(([assetId]) => assetId.startsWith('farm01_plant_'))?.[1]
    ?? null
  const lastSprinklerAction =
    [...Object.entries(actionRecords)].reverse().find(([assetId]) => assetId.startsWith('sprinkler_'))?.[1]
    ?? null
  const sprinklerResultPercent = lastSprinklerAction || environment.history.length > 0 ? 100 : 0
  const selectedTag = selectionTag(selectedAsset?.kind, selectedAsset?.status)
  const currentActivity = activityState ?? robot.missionState

  const feedbackMessage = uiMessage
    ?? (
      zoneMoveMutation.isSuccess
        ? zoneMoveMutation.data.message
        : zoneMoveMutation.isError
          ? zoneMoveMutation.error.message
          : harvestMutation.isSuccess
            ? harvestMutation.data
            : harvestMutation.isError
              ? harvestMutation.error.message
              : patrolMutation.isSuccess
                ? patrolMutation.data
                : patrolMutation.isError
                  ? patrolMutation.error.message
              : wateringMutation.isSuccess
                ? wateringMutation.data
                : wateringMutation.isError
                  ? wateringMutation.error.message
                  : nutrientMutation.isSuccess
                    ? nutrientMutation.data
                    : nutrientMutation.isError
                      ? nutrientMutation.error.message
                      : controlMutation.isSuccess
                        ? controlMutation.data
                        : controlMutation.isError
                          ? controlMutation.error.message
                          : null
    )

  const selectedStatusItems = selectedAsset?.kind === 'plant' && selectedPlantDetail
    ? [
        { label: '상태', value: selectedPlantDetail.status },
        { label: '권장 조치', value: selectedPlantDetail.recommendedAction },
        { label: '건강도', value: `${selectedPlantDetail.health}%` },
        {
          label: '조치 상태',
          value:
            selectedActionRecord?.label
            ?? (selectedAsset.status === 'attention' ? '조치 필요함' : selectedAsset.status === 'target' ? '수확 후보' : '대기'),
        },
      ]
    : selectedAsset?.kind === 'sprinkler'
      ? [
          { label: '장치', value: selectedAsset.label },
          { label: '장치 상태', value: '정상 작동' },
          { label: '가능 작업', value: '물주기 / 영양제 주기' },
          {
            label: '작업 상태',
            value: selectedActionRecord?.label ?? '대기',
          },
        ]
      : []

  const handleGuideMove = (guideId: string) => {
    setUiMessage(null)
    setActivityState('이동중')

    const guideZoneMap: Record<string, string> = {
      'row-1': robot.zonePresets[0]?.id ?? 'farm_01_west',
      'row-2': robot.zonePresets[0]?.id ?? 'farm_01_west',
      'row-3': robot.zonePresets[1]?.id ?? 'farm_01_center',
      'row-4': robot.zonePresets[2]?.id ?? 'farm_01_east',
    }
    const zoneId = guideZoneMap[guideId]

    if (!zoneId) {
      return
    }

    zoneMoveMutation.mutate(zoneId)
  }

  const handleSelectAsset = (assetId: string) => {
    setSelectedAssetId(assetId)
    setUiMessage(null)

    if (assetId.startsWith('farm01_plant_')) {
      setSelectedPlantId(assetId)
      setIsAssetModalOpen(true)
      return
    }

    if (assetId.startsWith('sprinkler_')) {
      setIsAssetModalOpen(true)
      return
    }

    setIsAssetModalOpen(false)
  }

  const closeAssetModal = () => {
    setIsAssetModalOpen(false)
  }

  const handleStartPatrol = (mode: 'diagnosis' | 'harvest') => {
    const detail =
      mode === 'diagnosis'
        ? '밭 전체를 돌며 병 진단 패트롤을 시작했습니다.'
        : '밭 전체를 돌며 수확 패트롤을 시작했습니다.'

    setActivityState(mode === 'diagnosis' ? '패트롤 진단중' : '패트롤 수확중')
    setUiMessage(null)
    patrolMutation.mutate(
      {
        mode,
        zoneIds: patrolZoneIds,
      },
      {
        onSuccess: () => {
          setLastPatrolAction({
            mode,
            detail,
          })
          setUiMessage(detail)
        },
      },
    )
  }

  const handleDiagnose = () => {
    const targetPlant = selectedAsset?.kind === 'plant'
      ? selectedPlantDetail
      : attentionPlant

    if (!targetPlant) {
      return
    }

    setActivityState('진단중')
    setSelectedPlantId(targetPlant.id)
    setSelectedAssetId(targetPlant.id)
    rememberAction(
      targetPlant.id,
      '진단 완료',
      `${targetPlant.name} 조치가 필요해 보여 진단 경로를 등록했습니다.`,
      'accent',
    )
    setUiMessage(`${targetPlant.name} 진단 경로를 등록했습니다.`)
  }

  const handleHarvest = () => {
    const targetPlant = selectedAsset?.kind === 'plant'
      ? selectedPlantDetail
      : selectedPlantDetail

    if (!targetPlant) {
      return
    }

    setActivityState('수확중')
    setUiMessage(null)
    harvestMutation.mutate(
      {
        plantId: targetPlant.id,
        fruitId: targetPlant.targetId,
      },
      {
        onSuccess: () => {
          rememberAction(
            targetPlant.id,
            '수확 요청 완료',
            `${targetPlant.name} 수확 요청을 등록했습니다.`,
            'accent',
          )
          setUiMessage(`${targetPlant.name} 수확 요청을 등록했습니다.`)
        },
      },
    )
  }

  const handleWatering = () => {
    if (selectedAsset?.kind !== 'sprinkler') {
      return
    }

    setActivityState('급수중')
    setUiMessage(null)
    wateringMutation.mutate(undefined, {
      onSuccess: () => {
        rememberAction(
          selectedAsset.id,
          '물주기 완료',
          `${selectedAsset.label} 물주기 요청을 등록했습니다.`,
          'healthy',
        )
        setUiMessage(`${selectedAsset.label} 물주기 요청을 등록했습니다.`)
      },
    })
  }

  const handleNutrient = () => {
    if (selectedAsset?.kind !== 'sprinkler') {
      return
    }

    setActivityState('영양제 주기')
    setUiMessage(null)
    nutrientMutation.mutate(undefined, {
      onSuccess: () => {
        rememberAction(
          selectedAsset.id,
          '영양제 주기 완료',
          `${selectedAsset.label} 영양제 주기 요청을 등록했습니다.`,
          'accent',
        )
        setUiMessage(`${selectedAsset.label} 영양제 주기 요청을 등록했습니다.`)
      },
    })
  }

  const resultItems = [
    {
      icon: 'warning',
      tone: 'danger',
      text: lastPatrolAction?.mode === 'diagnosis'
        ? lastPatrolAction.detail
        : lastPlantAction?.label === '진단 완료'
        ? lastPlantAction.detail
        : `흰가루병 개체 ${mildewPercent}% 발견했습니다.`,
    },
    {
      icon: 'water_drop',
      tone: 'accent',
      text: lastSprinklerAction?.detail
        ?? `0번 스프링쿨러 ${sprinklerResultPercent}% 약재 분사 완료하였습니다.`,
    },
    {
      icon: 'potted_plant',
      tone: 'warning',
      text: lastPatrolAction?.mode === 'harvest'
        ? lastPatrolAction.detail
        : lastPlantAction?.label === '수확 요청 완료'
        ? lastPlantAction.detail
        : `수확 가능 개체 ${harvestablePercent}% 발견했습니다.`,
    },
    {
      icon: 'inventory_2',
      tone: 'accent',
      text: `${harvestProgressPercent}% 수확 완료하였습니다.`,
    },
  ] as const

  const selectedTaskTitle = selectedAsset ? `${selectedSummary.title} 작업` : '작업 대상을 선택하세요'
  const selectedTaskDescription = selectedAsset?.kind === 'plant'
    ? '식물 개별 작업은 맵 팝업에서 바로 실행합니다.'
    : selectedAsset?.kind === 'sprinkler'
      ? '급수 개별 작업도 맵 팝업에서 바로 실행합니다.'
      : '밭 전체 패트롤 또는 개별 객체 작업을 선택할 수 있습니다.'

  return (
    <div className="farm-layout-page">
      <DevSurface
        as="section"
        className="panel farm-map-shell"
        contract={{
          title: '밭 맵',
          queries: [
            createGetSignal('로봇 상태', mapSource('/robot/status'), '/robot/status'),
            createGetSignal('로봇 위치', mapSource('/robot/pose'), '/robot/pose'),
            createGetSignal('날씨 메모', dashboardSource('/environment/latest'), '/environment/latest'),
          ],
          actions: [
            createPostAction('이랑 이동', ['/robot/commands']),
          ],
        }}
      >
        <div className="farm-map-header">
          <div>
            <span className="section-eyebrow">맵</span>
            <h2 className="section-title">밭 위치 보기</h2>
            <p className="section-description">
              이랑 라벨을 누르면 이동하고, 식물과 급수 헤드를 누르면 해당 작업 버튼만 오른쪽에 나타납니다.
            </p>
            <div className="farm-map-tip-row">
              <span className="chip">이랑 클릭 이동</span>
              <span className="chip">식물 선택 시 진단·수확</span>
              <span className="chip">급수 헤드 선택 시 물주기·영양제</span>
            </div>
          </div>
          <div className="farm-weather-card">
            <span className="panel-kicker">날씨</span>
            <strong>{weatherSummary}</strong>
          </div>
        </div>

        <div className="map-board farm-map-board">
          <div className="camera-peek">
            <span className="camera-live-pill">
              <span className="live-dot" />
              이미지 확인
            </span>
            <div className="camera-frame">
              <MockupImage
                alt="선택 객체 이미지"
                className="camera-frame-media"
                height="100%"
                src={previewImageForAsset(selectedAsset?.kind, selectedAsset?.status)}
              />
            </div>
          </div>

          <RobotFacilityMap
            onSelectAsset={handleSelectAsset}
            onSelectGuide={handleGuideMove}
            pose={robotPose}
            scene={mapScene}
            selectedAssetId={selectedAssetId}
            targetAssetId={targetAssetId}
            zoom={1}
          />
        </div>

        <div className="farm-map-footer">
          <article className="farm-info-card">
            <div className="split-row">
              <div>
                <span className="panel-kicker">객체 확인</span>
                <h3 className="list-title">{selectedSummary.title}</h3>
              </div>
              <span className={`table-tag table-tag--${selectedTag.tone}`}>{selectedTag.label}</span>
            </div>
            <p>{selectedSummary.subtitle}</p>
            <div className="farm-status-list">
              {selectedStatusItems.map((item) => (
                <div className="farm-status-item" key={item.label}>
                  <span className="detail-label">{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
            <div className="chip-row">
              {selectedSummary.chips.map((chip) => (
                <span className="chip" key={chip}>
                  {chip}
                </span>
              ))}
            </div>
          </article>

          <article className="farm-info-card">
            <div className="section-head">
              <div>
                <span className="panel-kicker">로봇 상태</span>
                <h3 className="list-title">{dashboard.location}</h3>
              </div>
            </div>
            <div className="farm-status-list">
              <div className="farm-status-item">
                <span className="detail-label">현재 위치</span>
                <strong>{robot.zoneLabel}</strong>
              </div>
              <div className="farm-status-item">
                <span className="detail-label">좌표</span>
                <strong>{robot.poseLabel}</strong>
              </div>
              <div className="farm-status-item">
                <span className="detail-label">배터리</span>
                <strong>{dashboard.battery}</strong>
              </div>
              <div className="farm-status-item">
                <span className="detail-label">활동상태</span>
                <strong>{currentActivity}</strong>
              </div>
            </div>
          </article>
        </div>
      </DevSurface>

      <DevSurface
        as="aside"
        className="panel farm-dashboard-shell"
        contract={{
          title: '오른쪽 대시보드',
          queries: [
            createGetSignal('작물 목록', plantsSource('/plants'), '/plants'),
            createGetSignal('밭 상태', fieldSource('/environment/latest'), '/environment/latest'),
            createGetSignal('수확 통계', harvestSource('/harvests/stats'), '/harvests/stats'),
            createGetSignal('로봇 상태', mapSource('/robot/status'), '/robot/status'),
          ],
          actions: [
            createPostAction('수확 요청', ['/missions/harvest']),
            createPostAction('전체 진단 패트롤', ['/missions/patrol/start', '/robot/commands'], 'any'),
            createPostAction('전체 수확 패트롤', ['/missions/patrol/start', '/robot/commands'], 'any'),
            createPostAction('물 주기', ['/actuations/recommendations/reco-water-001/approve', '/actuations/watering'], 'any'),
            createPostAction('영양제 주기', ['/actuations/nutrients']),
            createPostAction('일시정지', ['/missions/patrol/stop', '/robot/commands'], 'any'),
            createPostAction('재개', ['/robot/commands']),
            createPostAction('귀가', ['/missions/return-home', '/robot/commands'], 'any'),
          ],
        }}
      >
        <div className="section-head">
          <div>
            <span className="section-eyebrow">대시보드</span>
            <h2 className="section-title">오른쪽 조작판</h2>
            <p className="section-description">선택한 대상에 맞는 작업만 보여 주고, 결과와 로봇 조작만 남겼습니다.</p>
          </div>
          <span className="live-pill">
            {[dashboard.source, robot.source, plants.source, environment.source, harvest.source].some(
              (source) => source === 'live',
            )
              ? '실시간 연결'
              : '샘플 보드'}
          </span>
        </div>

        <section className="farm-section-card">
          <div className="section-head">
            <div>
              <span className="panel-kicker">농사</span>
              <h3 className="list-title">{selectedTaskTitle}</h3>
              <p className="farm-helper-copy">{selectedTaskDescription}</p>
            </div>
          </div>

          <div className="farm-action-groups">
            <div className="farm-action-group">
              <span className="detail-label">밭 전체 패트롤</span>
              <div className="farm-action-row">
                <button
                  className="action-button"
                  disabled={patrolMutation.isPending}
                  onClick={() => {
                    handleStartPatrol('diagnosis')
                  }}
                  type="button"
                >
                  {patrolMutation.isPending && currentActivity === '패트롤 진단중' ? '진단 패트롤 시작 중...' : '패트롤로 병 진단'}
                </button>
                <button
                  className="action-button action-button--warning"
                  disabled={patrolMutation.isPending}
                  onClick={() => {
                    handleStartPatrol('harvest')
                  }}
                  type="button"
                >
                  {patrolMutation.isPending && currentActivity === '패트롤 수확중' ? '수확 패트롤 시작 중...' : '패트롤로 전체 수확'}
                </button>
              </div>
            </div>

            {selectedAsset ? (
              <div className="farm-empty-state">
                <AppIcon name={selectedAsset.kind === 'plant' ? 'potted_plant' : 'water_drop'} />
                <p>
                  {selectedAsset.kind === 'plant'
                    ? '식물을 누르면 이미지와 함께 `진단하기`, `수확하기` 팝업이 열립니다.'
                    : '급수 헤드를 누르면 이미지와 함께 `물주기`, `영양제 주기` 팝업이 열립니다.'}
                </p>
              </div>
            ) : (
              <div className="farm-empty-state">
                <AppIcon name="my_location" />
                <p>맵에서 대상을 먼저 고르면 개별 작업이 나타나고, 패트롤 버튼은 밭 전체를 순회합니다.</p>
              </div>
            )}
          </div>
        </section>

        <section className="farm-section-card">
          <div className="section-head">
            <div>
              <span className="panel-kicker">결과</span>
              <h3 className="list-title">작업 요약</h3>
            </div>
          </div>
          <div className="farm-result-list">
            {resultItems.map((item) => (
              <article className={`farm-result-item farm-result-item--${item.tone}`} key={item.text}>
                <div className="farm-result-icon">
                  <AppIcon filled={item.tone === 'danger'} name={item.icon} />
                </div>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="farm-section-card">
          <div className="section-head">
            <div>
              <span className="panel-kicker">로봇 조작</span>
              <h3 className="list-title">일시정지, 재개, 귀가</h3>
            </div>
          </div>
          <div className="farm-action-row farm-action-row--robot">
            {robotControlActions.map((action) => (
              <button
                className="action-button action-button--soft"
                disabled={controlMutation.isPending}
                key={action.id}
                onClick={() => {
                  setUiMessage(null)
                  setActivityState(action.nextState)
                  controlMutation.mutate(action.id)
                }}
                type="button"
              >
                <AppIcon name={action.icon} />
                {action.title}
              </button>
            ))}
          </div>
          {feedbackMessage ? <p className="muted">{feedbackMessage}</p> : null}
        </section>
      </DevSurface>

      {isAssetModalOpen && selectedPlantAsset && selectedPlantDetail ? (
        <div
          className="farm-plant-modal"
          onClick={() => {
            closeAssetModal()
          }}
          role="presentation"
        >
          <div
            className="farm-plant-modal__card"
            onClick={(event) => {
              event.stopPropagation()
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="farm-plant-modal-title"
          >
            <button
              aria-label="식물 팝업 닫기"
              className="farm-plant-modal__close"
              onClick={() => {
                closeAssetModal()
              }}
              type="button"
            >
              <AppIcon name="remove" />
            </button>

            <div className="farm-plant-modal__media">
              <MockupImage
                alt={`${selectedPlantDetail.name} 확인 이미지`}
                className="farm-plant-modal__image"
                height="100%"
                src={previewImageForAsset('plant', selectedPlantAsset.status)}
              />
            </div>

            <div className="farm-plant-modal__body">
              <div className="split-row">
                <div>
                  <span className="panel-kicker">작물 확인</span>
                  <h3 className="list-title" id="farm-plant-modal-title">{selectedPlantDetail.name}</h3>
                </div>
                <span className={`table-tag table-tag--${selectedTag.tone}`}>{selectedTag.label}</span>
              </div>

              <p className="farm-helper-copy">{selectedPlantDetail.status} · {selectedPlantDetail.recommendedAction}</p>

              <div className="chip-row">
                <span className="chip">{selectedPlantDetail.zoneLabel}</span>
                <span className="chip">{selectedPlantDetail.positionLabel}</span>
                <span className="chip">건강도 {selectedPlantDetail.health}%</span>
              </div>

              <div className="farm-plant-modal__actions">
                <button
                  className="action-button"
                  onClick={() => {
                    handleDiagnose()
                    closeAssetModal()
                  }}
                  type="button"
                >
                  진단하기
                </button>
                <button
                  className="action-button action-button--warning"
                  disabled={harvestMutation.isPending}
                  onClick={() => {
                    handleHarvest()
                    closeAssetModal()
                  }}
                  type="button"
                >
                  {harvestMutation.isPending ? '수확 중...' : '수확하기'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {isAssetModalOpen && selectedSprinklerAsset ? (
        <div
          className="farm-plant-modal"
          onClick={() => {
            closeAssetModal()
          }}
          role="presentation"
        >
          <div
            className="farm-plant-modal__card"
            onClick={(event) => {
              event.stopPropagation()
            }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="farm-sprinkler-modal-title"
          >
            <button
              aria-label="급수 팝업 닫기"
              className="farm-plant-modal__close"
              onClick={() => {
                closeAssetModal()
              }}
              type="button"
            >
              <AppIcon name="remove" />
            </button>

            <div className="farm-plant-modal__media">
              <MockupImage
                alt={`${selectedSprinklerAsset.label} 확인 이미지`}
                className="farm-plant-modal__image"
                height="100%"
                src={previewImageForAsset('sprinkler', selectedSprinklerAsset.status)}
              />
            </div>

            <div className="farm-plant-modal__body">
              <div className="split-row">
                <div>
                  <span className="panel-kicker">급수 확인</span>
                  <h3 className="list-title" id="farm-sprinkler-modal-title">{selectedSprinklerAsset.label}</h3>
                </div>
                <span className={`table-tag table-tag--${selectedTag.tone}`}>{selectedTag.label}</span>
              </div>

              <p className="farm-helper-copy">정상 작동 중 · 물주기와 영양제 주기를 바로 실행할 수 있습니다.</p>

              <div className="chip-row">
                <span className="chip">zone {selectedSprinklerAsset.zoneId}</span>
                <span className="chip">x {selectedSprinklerAsset.position.x.toFixed(1)} / y {selectedSprinklerAsset.position.y.toFixed(1)}</span>
                <span className="chip">{selectedActionRecord?.label ?? '작업 대기'}</span>
              </div>

              <div className="farm-plant-modal__actions">
                <button
                  className="action-button action-button--soft"
                  disabled={wateringMutation.isPending}
                  onClick={() => {
                    handleWatering()
                    closeAssetModal()
                  }}
                  type="button"
                >
                  {wateringMutation.isPending ? '물 주는 중...' : '물주기'}
                </button>
                <button
                  className="action-button"
                  disabled={nutrientMutation.isPending}
                  onClick={() => {
                    handleNutrient()
                    closeAssetModal()
                  }}
                  type="button"
                >
                  {nutrientMutation.isPending ? '영양제 주는 중...' : '영양제 주기'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
