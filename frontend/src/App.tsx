import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AppShell from './app/AppShell'
import './styles.css'

/**
 * React Query client with sensible defaults for a gallery app:
 * - Moderate stale time to reduce refetches
 * - Reasonable retry logic for network errors
 * - No refetch on window focus (can be jarring for galleries)
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000, // 10 seconds before data is considered stale
      gcTime: 5 * 60_000, // Keep unused data in cache for 5 minutes
      retry: 2,
      retryDelay: (attemptIndex) => Math.min(1000 * Math.pow(2, attemptIndex), 10_000),
      refetchOnWindowFocus: false,
      refetchOnReconnect: 'always',
    },
    mutations: {
      retry: 2,
      retryDelay: (attemptIndex) => Math.min(1000 * Math.pow(2, attemptIndex), 5_000),
    },
  },
})

export default function AppRoot() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  )
}
