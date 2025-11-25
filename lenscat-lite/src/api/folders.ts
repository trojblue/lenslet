import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { FolderIndex } from '../lib/types'

/** Query key for folder data */
export const folderQueryKey = (path: string) => ['folder', path] as const

/**
 * Hook to fetch and cache folder contents.
 * - Caches for 10 seconds before considered stale
 * - Retries failed requests up to 2 times
 * - Returns previous data while refetching
 */
export function useFolder(path: string) {
  return useQuery({
    queryKey: folderQueryKey(path),
    queryFn: () => api.getFolder(path),
    staleTime: 10_000, // 10 seconds before refetch
    gcTime: 5 * 60_000, // Keep in cache for 5 minutes
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 5000),
    refetchOnWindowFocus: false,
  })
}

/**
 * Hook to prefetch a folder's contents.
 * Useful for prefetching when hovering over folder tree items.
 */
export function usePrefetchFolder() {
  const queryClient = useQueryClient()
  
  return (path: string) => {
    queryClient.prefetchQuery({
      queryKey: folderQueryKey(path),
      queryFn: () => api.getFolder(path),
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
  
  return (path: string) => {
    queryClient.invalidateQueries({ queryKey: folderQueryKey(path) })
  }
}

/**
 * Optimistically update folder cache.
 * Returns a rollback function.
 */
export function useOptimisticFolderUpdate() {
  const queryClient = useQueryClient()
  
  return (path: string, updater: (old: FolderIndex | undefined) => FolderIndex | undefined) => {
    const previous = queryClient.getQueryData<FolderIndex>(folderQueryKey(path))
    queryClient.setQueryData<FolderIndex | undefined>(folderQueryKey(path), updater)
    return () => queryClient.setQueryData(folderQueryKey(path), previous)
  }
}
