import { createBrowserRouter } from 'react-router-dom'
import AppShell from '@/app/shell'
import { AlertsPage } from '@/pages/alerts-page'
import { DashboardPage } from '@/pages/dashboard-page'
import { EnvironmentPage } from '@/pages/environment-page'
import { HarvestPage } from '@/pages/harvest-page'
import { MapControlPage } from '@/pages/map-control-page'

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
        path: 'map',
        element: <MapControlPage />,
      },
      {
        path: 'alerts',
        element: <AlertsPage />,
      },
      {
        path: 'environment',
        element: <EnvironmentPage />,
      },
      {
        path: 'harvest',
        element: <HarvestPage />,
      },
    ],
  },
])
