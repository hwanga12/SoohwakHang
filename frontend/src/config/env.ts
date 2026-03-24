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
