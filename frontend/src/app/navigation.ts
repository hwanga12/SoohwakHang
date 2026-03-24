export type NavigationItem = {
  path: string
  label: string
  caption: string
  description: string
}

export const navigationItems: NavigationItem[] = [
  {
    path: '/',
    label: 'Dashboard',
    caption: '운영 요약',
    description: '로봇 상태, 실시간 알림, 환경값을 한 번에 확인합니다.',
  },
  {
    path: '/map',
    label: 'Map Control',
    caption: '지도와 제어',
    description: '비닐하우스 맵과 로봇 제어 액션을 배치합니다.',
  },
  {
    path: '/alerts',
    label: 'Alert Center',
    caption: '병해 및 장애',
    description: '알림 타임라인과 우선순위 대응 흐름을 구성합니다.',
  },
  {
    path: '/environment',
    label: 'Environment',
    caption: '센서와 자동화',
    description: '온실 센서 상태와 자동화 추천을 시각화합니다.',
  },
  {
    path: '/harvest',
    label: 'Harvest Board',
    caption: '수확 지표',
    description: '수확량, 적재 현황, 작업 계획을 정리합니다.',
  },
]
