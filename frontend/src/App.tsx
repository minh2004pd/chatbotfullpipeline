import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AuthGuard from '@/components/auth/AuthGuard'
import AppLayout from '@/components/layout/AppLayout'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
    mutations: {
      retry: 0,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGuard>
        <AppLayout />
      </AuthGuard>
    </QueryClientProvider>
  )
}
