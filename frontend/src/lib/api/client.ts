/*
 * 이 모듈은 백엔드 API 호출에 공통으로 쓰는 HTTP 클라이언트를 정의한다.
 */
import axios from 'axios'
import { env } from '@/config/env'

/**
 * API 클라이언트에 공통 설정을 적용해 재사용하는 클라이언트 인스턴스다.
 */
export const apiClient = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: 10_000,
  headers: {
    Accept: 'application/json',
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.request.use((config) => {
  config.headers = config.headers ?? {}
  config.headers['X-Requested-With'] = 'agribot-frontend'

  return config
})
