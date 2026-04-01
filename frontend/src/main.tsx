/*
 * 이 모듈은 프론트엔드 React 애플리케이션을 시작한다.
 */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { AppProviders } from './app/providers'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders>
      <App />
    </AppProviders>
  </StrictMode>,
)
