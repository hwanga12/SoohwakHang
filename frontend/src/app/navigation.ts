export type NavigationItem = {
  path: string
  label: string
  caption: string
  description: string
  icon: string
}

export const navigationItems: NavigationItem[] = [
  {
    path: '/',
    label: '대시보드',
    caption: '운영 요약',
    description: '순찰 상태, 병해 알림, 환경값을 운영 기준으로 압축해 보여줍니다.',
    icon: 'dashboard',
  },
  {
    path: '/robot',
    label: '로봇',
    caption: '지도와 제어',
    description: '온실 맵, 현재 waypoint, 미션 진행률과 제어 액션을 함께 둡니다.',
    icon: 'precision_manufacturing',
  },
  {
    path: '/plants',
    label: '작물',
    caption: '생육과 진단',
    description: '생육 상태, 수확 후보, 병해 의심 개체를 같은 흐름에서 검토합니다.',
    icon: 'potted_plant',
  },
  {
    path: '/alerts',
    label: '알림',
    caption: '병해와 설비 경고',
    description: '병해, 센서, 장치 경고를 한 화면에서 읽고 처리 상태를 정리합니다.',
    icon: 'notifications_active',
  },
  {
    path: '/iot',
    label: '설비',
    caption: '센서와 자동화',
    description: '센서 값, 장치 상태, 자동 제어 추천과 승인 흐름을 배치합니다.',
    icon: 'sensors',
  },
  {
    path: '/harvest',
    label: '수확',
    caption: '배치와 적재',
    description: '수확 미션, 바구니 적재 상태, 품질 지표를 운영 관점으로 정리합니다.',
    icon: 'inventory_2',
  },
]
