import { Navigate, createBrowserRouter } from 'react-router-dom'
import AppShell from '@/app/shell'
import { DashboardPage } from '@/pages/dashboard-page'
import { EnvironmentPage } from '@/pages/environment-page'
import { HarvestPage } from '@/pages/harvest-page'
import { MapControlPage } from '@/pages/map-control-page'
import { PlantsPage } from '@/pages/plants-page'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      {
        index: true,
        element: <DashboardPage />,
      },
      {
        path: 'robot',
        element: <MapControlPage />,
      },
      {
        path: 'map',
        element: <Navigate replace to="/robot" />,
      },
      {
        path: 'plants',
        element: <PlantsPage />,
      },
      {
        path: 'alerts',
        element: <Navigate replace to="/plants" />,
      },
      {
        path: 'iot',
        element: <EnvironmentPage />,
      },
      {
        path: 'environment',
        element: <Navigate replace to="/iot" />,
      },
      {
        path: 'harvest',
        element: <HarvestPage />,
      },
    ],
  },
])
