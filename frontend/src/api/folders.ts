import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import { usePollingEnabled } from './polling'
import type { FolderIndex } from '../lib/types'
import type { GetFolderOptions } from './client'

export const DEFAULT_FOLDER_GC_TIME_MS = 5 * 60_000
export const RECURSIVE_FOLDER_GC_TIME_MS = 60_000
type RecursiveFolderQueryKey = readonly ['folder', string, 'recursive']

/** Query key for folder data */
export const folderQueryKey = (
  path: string,
  options?: Pick<GetFolderOptions, 'recursive'>,
) => (
  options?.recursive
    ? [
      'folder',
      path,
      'recursive',
    ] as const
    : ['folder', path] as const
)

function parseRecursiveFolderQueryKey(queryKey: readonly unknown[]): RecursiveFolderQueryKey | null {
  if (queryKey[0] !== 'folder' || queryKey[2] !== 'recursive') return null
  if (typeof queryKey[1] !== 'string') return null
  return queryKey as RecursiveFolderQueryKey
}

export function isRecursiveFolderQueryKey(queryKey: readonly unknown[]): boolean {
  return parseRecursiveFolderQueryKey(queryKey) !== null
}

export function shouldRetainRecursiveFolderQuery(
  queryKey: readonly unknown[],
  currentPath: string,
  keepRoot = true,
): boolean {
  if (!isRecursiveFolderQueryKey(queryKey)) return true
  const recursiveKey = parseRecursiveFolderQueryKey(queryKey)
  if (recursiveKey == null) return false
  const [, keyPath] = recursiveKey
  if (keyPath === currentPath) return true
  if (keepRoot && keyPath === '/') return true
  return false
}

export function shouldRemoveRecursiveFolderQuery(
  queryKey: unknown,
  currentPath: string,
  keepRoot = true,
): boolean {
  if (!Array.isArray(queryKey)) return false
  if (queryKey[0] !== 'folder') return false
  return !shouldRetainRecursiveFolderQuery(queryKey, currentPath, keepRoot)
}

const FALLBACK_REFETCH_INTERVAL = 15_000

function fetchFolder(path: string, options?: GetFolderOptions): Promise<FolderIndex> {
  return api.getFolder(path, options)
}

type UseFolderOptions = GetFolderOptions & {
  enabled?: boolean
}

/**
 * Hook to fetch and cache folder contents.
 * - Caches for 10 seconds before considered stale
 * - Retries failed requests up to 2 times
 * - Returns previous data while refetching
 */
export function useFolder(path: string, recursive = false, options?: UseFolderOptions) {
  const pollingEnabled = usePollingEnabled()
  const folderOptions: GetFolderOptions = {
    recursive,
  }
  const recursiveQuery = !!folderOptions.recursive
  return useQuery({
    queryKey: folderQueryKey(path, folderOptions),
    queryFn: () => fetchFolder(path, folderOptions),
    enabled: options?.enabled ?? true,
    staleTime: 10_000, // 10 seconds before refetch
    gcTime: recursiveQuery ? RECURSIVE_FOLDER_GC_TIME_MS : DEFAULT_FOLDER_GC_TIME_MS,
    retry: 2,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 5000),
    refetchOnWindowFocus: false,
    refetchInterval: pollingEnabled ? FALLBACK_REFETCH_INTERVAL : false,
    refetchIntervalInBackground: pollingEnabled,
  })
}

type UseFolderCountOptions = {
  enabled?: boolean
}

export function useFolderCount(path: string, options?: UseFolderCountOptions) {
  const pollingEnabled = usePollingEnabled()
  return useQuery({
    queryKey: ['folder-count', path] as const,
    queryFn: () => api.getFolderCount(path),
    enabled: options?.enabled ?? true,
    staleTime: 10_000,
    gcTime: DEFAULT_FOLDER_GC_TIME_MS,
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
    const folderOptions: GetFolderOptions = { recursive }
    queryClient.prefetchQuery({
      queryKey: folderQueryKey(path, folderOptions),
      queryFn: () => fetchFolder(path, folderOptions),
      staleTime: 10_000,
      gcTime: recursive ? RECURSIVE_FOLDER_GC_TIME_MS : DEFAULT_FOLDER_GC_TIME_MS,
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
    queryClient.invalidateQueries({ queryKey: folderQueryKey(path, { recursive }) })
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
    const key = folderQueryKey(path, { recursive })
    const previous = queryClient.getQueryData<FolderIndex>(key)
    queryClient.setQueryData<FolderIndex | undefined>(key, updater)
    return () => queryClient.setQueryData(key, previous)
  }
}
