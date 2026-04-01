/*
 * 이 모듈은 프론트엔드 앱 골격에서 앱 내 탐색 메뉴와 이동 규칙을 정의한다.
 */
/**
 * 주행 item 구조를 코드 전반에서 같은 방식으로 다루기 위한 타입이다.
 */
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
    path: '/iot',
    label: '밭',
    caption: '물주기와 메모',
    description: '토양 수분, 물주기 승인, 영양 보충 메모만 가볍게 살핍니다.',
    icon: 'water_drop',
  },
  {
    path: '/harvest',
    label: '수확',
    caption: '배치와 적재',
    description: '수확 미션, 바구니 적재 상태, 품질 지표를 운영 관점으로 정리합니다.',
    icon: 'inventory_2',
  },
]
