import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import { usePollingEnabled } from './polling'
import type { FolderIndex } from '../lib/types'

/** Query key for folder data */
export const folderQueryKey = (path: string, recursive = false) => (
  recursive ? ['folder', path, 'recursive'] as const : ['folder', path] as const
)
const FALLBACK_REFETCH_INTERVAL = 15_000

function fetchFolder(path: string, recursive = false): Promise<FolderIndex> {
  return api.getFolder(path, undefined, recursive)
}

/**
 * Hook to fetch and cache folder contents.
 * - Caches for 10 seconds before considered stale
 * - Retries failed requests up to 2 times
 * - Returns previous data while refetching
 */
export function useFolder(path: string, recursive = false) {
  const pollingEnabled = usePollingEnabled()
  return useQuery({
    queryKey: folderQueryKey(path, recursive),
    queryFn: () => fetchFolder(path, recursive),
    staleTime: 10_000, // 10 seconds before refetch
    gcTime: 5 * 60_000, // Keep in cache for 5 minutes
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 5000),
    refetchOnWindowFocus: false,
    refetchInterval: pollingEnabled ? FALLBACK_REFETCH_INTERVAL : false,
    refetchIntervalInBackground: pollingEnabled,
  })
}

/**
 * Hook to prefetch a folder's contents.
 * Useful for prefetching when hovering over folder tree items.
 */
export function usePrefetchFolder() {
  const queryClient = useQueryClient()
  
  return (path: string, recursive = false) => {
    queryClient.prefetchQuery({
      queryKey: folderQueryKey(path, recursive),
      queryFn: () => fetchFolder(path, recursive),
      staleTime: 10_000,
    })
  }
}

/**
 * Hook to invalidate folder cache.
 * Call after mutations that affect folder contents.
 */
export function useInvalidateFolder() {
  const queryClient = useQueryClient()
  
  return (path: string, recursive = false) => {
    queryClient.invalidateQueries({ queryKey: folderQueryKey(path, recursive) })
  }
}

/**
 * Optimistically update folder cache.
 * Returns a rollback function.
 */
export function useOptimisticFolderUpdate() {
  const queryClient = useQueryClient()
  
  return (
    path: string,
    updater: (old: FolderIndex | undefined) => FolderIndex | undefined,
    recursive = false
  ) => {
    const key = folderQueryKey(path, recursive)
    const previous = queryClient.getQueryData<FolderIndex>(key)
    queryClient.setQueryData<FolderIndex | undefined>(key, updater)
    return () => queryClient.setQueryData(key, previous)
  }
}
