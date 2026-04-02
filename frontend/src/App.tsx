/*
 * 이 모듈은 최상위 앱 컴포넌트에서 라우터를 연결한다.
 */
import { RouterProvider } from 'react-router-dom'
import { router } from '@/app/router'

function App() {
  return <RouterProvider router={router} />
}

export default App
