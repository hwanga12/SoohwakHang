/*
 * 이 모듈은 프론트엔드 앱 골격에서 전역 상태와 라이브러리 provider를 묶는다.
 */
import type { PropsWithChildren } from 'react'
import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DevInspectorProvider } from '@/app/dev-inspector'

/**
 * APP 전역 provider 화면 조각을 렌더링하는 컴포넌트다.
 */
export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 30 * 1000,
          },
        },
      }),
  )

  return (
    <QueryClientProvider client={queryClient}>
      <DevInspectorProvider>{children}</DevInspectorProvider>
    </QueryClientProvider>
  )
}
