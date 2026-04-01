/*
 * 이 모듈은 프론트엔드 환경 변수 읽기 규칙을 정의한다.
 */
/**
 * 대체값이 없을 때 기본값을 적용해 반환하는 함수다.
 */
const withFallback = (value: string | undefined, fallback: string) =>
  value?.trim() || fallback

export const env = {
  appName: withFallback(
    import.meta.env.VITE_APP_NAME,
    '수확해조 관제 센터',
  ),
  apiBaseUrl: withFallback(
    import.meta.env.VITE_API_BASE_URL,
    'http://localhost:8000/api/v1',
  ),
  wsUrl: withFallback(import.meta.env.VITE_WS_URL, 'ws://localhost:8000/ws/live'),
  mode: import.meta.env.MODE,
}
