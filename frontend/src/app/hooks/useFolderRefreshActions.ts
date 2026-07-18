import { useCallback, useState, type Dispatch, type SetStateAction } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import { api } from '../../api/client'
import { fileCache, thumbCache } from '../../lib/blobCache'
import { sanitizePath } from '../../lib/paths'
import { thumbnailObjectUrlCache } from '../../features/browse/model/thumbnailObjectUrlCache'

type UseFolderRefreshActionsParams = {
  current: string
  refreshEnabled: boolean
  queryClient: QueryClient
  refetch: () => Promise<unknown>
  invalidateFolderSessionSubtree: (path: string) => void
  setScopeSessionResetToken: Dispatch<SetStateAction<number>>
  onActionStart?: () => void
  onActionError?: (action: string, error: unknown) => void
}

type UseFolderRefreshActionsResult = {
  folderCountsVersion: number
  headerRefreshBusy: boolean
  refreshFolderPath: (path: string) => Promise<void>
  handlePullRefreshFolders: () => Promise<void>
  handleHeaderRefresh: () => Promise<void>
}

function normalizeRefreshPath(path: string): string {
  const safe = sanitizePath(path || '/')
  return safe === '' ? '/' : safe
}

function isCurrentInsideTarget(current: string, target: string): boolean {
  if (target === '/') return current.startsWith('/')
  return current === target || current.startsWith(`${target}/`)
}

export function useFolderRefreshActions({
  current,
  refreshEnabled,
  queryClient,
  refetch,
  invalidateFolderSessionSubtree,
  setScopeSessionResetToken,
  onActionStart,
  onActionError,
}: UseFolderRefreshActionsParams): UseFolderRefreshActionsResult {
  const [folderCountsVersion, setFolderCountsVersion] = useState(0)
  const [headerRefreshBusy, setHeaderRefreshBusy] = useState(false)

  const invalidateDerivedCounts = useCallback(() => {
    setFolderCountsVersion((prev) => prev + 1)
  }, [])

  const invalidateFolderSubtree = useCallback((target: string) => {
    const matches = (candidate: string) => {
      if (target === '/') return true
      return candidate === target || candidate.startsWith(`${target}/`)
    }

    queryClient.invalidateQueries({
      predicate: ({ queryKey }) => {
        if (!Array.isArray(queryKey)) return false
        if (queryKey[0] !== 'folder' && queryKey[0] !== 'folder-query' && queryKey[0] !== 'folder-facets') {
          return false
        }
        const keyPath = typeof queryKey[1] === 'string' ? queryKey[1] : ''
        return matches(keyPath)
      },
    })
  }, [queryClient])

  const refreshFolderPath = useCallback(async (path: string) => {
    if (!refreshEnabled) return
    const target = normalizeRefreshPath(path)
    await api.refreshFolder(target)
    invalidateFolderSubtree(target)
    invalidateDerivedCounts()
    invalidateFolderSessionSubtree(target)

    if (isCurrentInsideTarget(current, target)) {
      setScopeSessionResetToken((token) => token + 1)
      await refetch()
    }

    thumbCache.evictPrefix(target)
    thumbnailObjectUrlCache.evictPrefix(target)
    fileCache.evictPrefix(target)
  }, [
    current,
    invalidateDerivedCounts,
    invalidateFolderSessionSubtree,
    invalidateFolderSubtree,
    refetch,
    refreshEnabled,
    setScopeSessionResetToken,
  ])

  const handlePullRefreshFolders = useCallback(async () => {
    if (!refreshEnabled) return
    onActionStart?.()
    try {
      await refreshFolderPath(current)
    } catch (err) {
      onActionError?.('Refresh folder failed', err)
    }
  }, [current, onActionError, onActionStart, refreshEnabled, refreshFolderPath])

  const handleHeaderRefresh = useCallback(async () => {
    if (!refreshEnabled || headerRefreshBusy) return
    setHeaderRefreshBusy(true)
    onActionStart?.()
    try {
      await refreshFolderPath('/')
    } catch (err) {
      onActionError?.('Refresh root folder failed', err)
    } finally {
      setHeaderRefreshBusy(false)
    }
  }, [headerRefreshBusy, onActionError, onActionStart, refreshEnabled, refreshFolderPath])

  return {
    folderCountsVersion,
    headerRefreshBusy,
    refreshFolderPath,
    handlePullRefreshFolders,
    handleHeaderRefresh,
  }
}
