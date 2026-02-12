import { useQuery } from '@tanstack/react-query'
import { api } from './client'
import { usePollingEnabled } from './polling'
import type { SearchResult } from '../lib/types'

/** Query key for search results */
export const searchQueryKey = (q: string, path: string) => ['search', q, path] as const
const FALLBACK_REFETCH_INTERVAL = 20_000
const ROOT_SCOPE_PATH = '/'

export type CanonicalSearchRequest = {
  q: string
  path: string
}

export function normalizeSearchQuery(query: string): string {
  return query.trim().replace(/\s+/g, ' ')
}

export function normalizeSearchScopePath(path: string): string {
  const trimmed = path.trim()
  if (!trimmed || trimmed === ROOT_SCOPE_PATH) return ROOT_SCOPE_PATH
  return trimmed.startsWith(ROOT_SCOPE_PATH) ? trimmed : `${ROOT_SCOPE_PATH}${trimmed}`
}

export function buildCanonicalSearchRequest(query: string, path: string): CanonicalSearchRequest | null {
  const normalizedQuery = normalizeSearchQuery(query)
  if (!normalizedQuery) return null
  return {
    q: normalizedQuery,
    path: normalizeSearchScopePath(path),
  }
}

function parseSearchQueryKey(queryKey: readonly unknown[] | undefined): CanonicalSearchRequest | null {
  if (!Array.isArray(queryKey)) return null
  if (queryKey[0] !== 'search') return null
  if (typeof queryKey[1] !== 'string') return null
  if (typeof queryKey[2] !== 'string') return null
  return buildCanonicalSearchRequest(queryKey[1], queryKey[2])
}

export function shouldKeepSearchPlaceholderData(
  previousQueryKey: readonly unknown[] | undefined,
  nextRequest: CanonicalSearchRequest | null,
): boolean {
  if (!nextRequest) return false
  const previousRequest = parseSearchQueryKey(previousQueryKey)
  if (!previousRequest) return false
  // Preserve old rows only while staying in the same scoped search context.
  return previousRequest.path === nextRequest.path
}

/**
 * Hook to search for items by query string.
 * - Only runs when query is non-empty
 * - Caches results briefly (3 seconds)
 * - Keeps previous results while fetching new ones
 */
export function useSearch(q: string, path: string) {
  const pollingEnabled = usePollingEnabled()
  const request = buildCanonicalSearchRequest(q, path)
  const queryKey = searchQueryKey(request?.q ?? '', request?.path ?? normalizeSearchScopePath(path))
  return useQuery({
    enabled: request !== null,
    queryKey,
    queryFn: (): Promise<SearchResult> => {
      if (!request) return Promise.resolve({ items: [] })
      return api.search(request.q, request.path)
    },
    staleTime: 3_000, // 3 seconds
    gcTime: 60_000, // Keep in cache for 1 minute
    placeholderData: (prev, previousQuery) => {
      if (!shouldKeepSearchPlaceholderData(previousQuery?.queryKey, request)) return undefined
      return prev
    },
    retry: 1,
    refetchInterval: pollingEnabled ? FALLBACK_REFETCH_INTERVAL : false,
    refetchIntervalInBackground: pollingEnabled,
  })
}
