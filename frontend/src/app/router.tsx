import { Navigate, createBrowserRouter } from 'react-router-dom'
import { FarmCommandPage } from '@/pages/farm-command-page'

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
