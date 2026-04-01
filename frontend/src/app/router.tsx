/*
 * 이 모듈은 프론트엔드 앱 골격에서 프론트엔드 라우팅 구성을 정의.
 */
import { Navigate, createBrowserRouter } from 'react-router-dom'
import { FarmCommandPage } from '@/pages/farm-command-page'

/**
 * 앱에서 사용할 URL 경로와 페이지 연결 규칙을 정의한 브라우저 라우터다.
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <FarmCommandPage />,
  },
  {
    path: '*',
    element: <Navigate replace to="/" />,
  },
])
