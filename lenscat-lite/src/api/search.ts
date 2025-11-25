import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import type { SearchResult } from '../lib/types'

/** Query key for search results */
export const searchQueryKey = (q: string, path: string) => ['search', q, path] as const

/**
 * Hook to search for items by query string.
 * - Only runs when query is non-empty
 * - Caches results briefly (3 seconds)
 * - Keeps previous results while fetching new ones
 */
export function useSearch(q: string, path: string) {
  return useQuery({
    enabled: !!q.trim(),
    queryKey: searchQueryKey(q, path),
    queryFn: (): Promise<SearchResult> => api.search(q, path),
    staleTime: 3_000, // 3 seconds
    gcTime: 60_000, // Keep in cache for 1 minute
    placeholderData: (prev) => prev, // Show previous results while loading
    retry: 1,
  })
}
