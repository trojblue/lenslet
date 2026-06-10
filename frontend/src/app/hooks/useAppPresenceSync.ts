import { useCallback, useMemo, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import type { ConnectionStatus } from '../../api/client'
import type {
  HealthMode,
  BrowseItemPayload,
  PresenceEvent,
  StarRating,
  TableLaunchStatusPayload,
} from '../../lib/types'
import {
  buildRecentSummary,
  buildRecentTouchesDisplay,
  usePresenceActivity,
  type RecentSummary,
  type RecentTouchDisplay,
} from '../presenceActivity'
import type { HealthIndexing } from './healthIndexing'
import { getConnectionLabel, useAppSyncEvents } from './useAppSyncEvents'
import { useAppHealthPolling } from './useAppHealthPolling'
import { usePresenceLeaseLifecycle } from './usePresenceLeaseLifecycle'
import { useRecentEditState } from './useRecentEditState'
import type { ItemCacheUpdatePayload } from '../model/appShellStateSync'

type UseAppPresenceSyncParams = {
  current: string
  currentGalleryId: string
  itemPaths: string[]
  items: BrowseItemPayload[]
  queryClient: QueryClient
  updateItemCaches: (payload: ItemCacheUpdatePayload) => void
  setLocalStarOverrides: Dispatch<SetStateAction<Record<string, StarRating>>>
}

type UseAppPresenceSyncResult = {
  connectionStatus: ConnectionStatus
  connectionLabel: string
  presence: PresenceEvent | undefined
  editingCount: number
  recentEditActive: boolean
  hasEdits: boolean
  lastEditedLabel: string
  persistenceEnabled: boolean
  healthMode: HealthMode | null
  refreshEnabled: boolean
  refreshDisabledReason: string | null
  indexing: HealthIndexing | null
  tableLaunchStatus: TableLaunchStatusPayload | null
  highlightedPaths: Map<string, string>
  onVisiblePathsChange: (paths: Set<string>) => void
  offViewSummary: RecentSummary | null
  recentTouchesDisplay: RecentTouchDisplay[]
  clearOffViewActivity: () => void
}

export function useAppPresenceSync({
  current,
  currentGalleryId,
  itemPaths,
  items,
  queryClient,
  updateItemCaches,
  setLocalStarOverrides,
}: UseAppPresenceSyncParams): UseAppPresenceSyncResult {
  const [presenceByGallery, setPresenceByGallery] = useState<Record<string, PresenceEvent>>({})
  const {
    offViewActivity,
    recentTouches,
    highlightedPaths,
    onVisiblePathsChange,
    markRecentActivity,
    markRecentTouch,
    clearOffViewActivity,
  } = usePresenceActivity(itemPaths)
  const {
    recentEditActive,
    hasEdits,
    lastEditedNow,
    lastEditedLabel,
    updateLastEdited,
    formatTimestampLabel,
  } = useRecentEditState()
  const {
    persistenceEnabled,
    healthMode,
    refreshEnabled,
    refreshDisabledReason,
    indexing,
    tableLaunchStatus,
  } = useAppHealthPolling()

  const applyPresenceCounts = useCallback((counts: PresenceEvent[]) => {
    if (!counts.length) return
    setPresenceByGallery((prev) => {
      let changed = false
      const next = { ...prev }
      for (const count of counts) {
        const existing = prev[count.gallery_id]
        if (existing && existing.viewing === count.viewing && existing.editing === count.editing) {
          continue
        }
        next[count.gallery_id] = count
        changed = true
      }
      return changed ? next : prev
    })
  }, [])

  const clearPresenceScope = useCallback((galleryId: string | null) => {
    if (!galleryId) return
    setPresenceByGallery((prev) => {
      if (!(galleryId in prev)) return prev
      const next = { ...prev }
      delete next[galleryId]
      return next
    })
  }, [])

  const connectionStatus = useAppSyncEvents({
    queryClient,
    updateItemCaches,
    setLocalStarOverrides,
    applyPresenceCounts,
    markRecentActivity,
    markRecentTouch,
    updateLastEdited,
  })

  usePresenceLeaseLifecycle({
    currentGalleryId,
    connectionStatus,
    applyPresenceCounts,
    clearPresenceScope,
  })

  const presence = presenceByGallery[current]
  const editingCount = presence?.editing ?? 0
  const connectionLabel = useMemo(() => getConnectionLabel(connectionStatus), [connectionStatus])

  const offViewSummary = useMemo(
    () => buildRecentSummary(offViewActivity, items),
    [offViewActivity, items],
  )
  const recentTouchesDisplay = useMemo(
    () => buildRecentTouchesDisplay(recentTouches, items, lastEditedNow, formatTimestampLabel),
    [items, lastEditedNow, recentTouches],
  )

  return {
    connectionStatus,
    connectionLabel,
    presence,
    editingCount,
    recentEditActive,
    hasEdits,
    lastEditedLabel,
    persistenceEnabled,
    healthMode,
    refreshEnabled,
    refreshDisabledReason,
    indexing,
    tableLaunchStatus,
    highlightedPaths,
    onVisiblePathsChange,
    offViewSummary,
    recentTouchesDisplay,
    clearOffViewActivity,
  }
}
