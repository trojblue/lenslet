import { useEffect, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import {
  connectEvents,
  disconnectEvents,
  subscribeEvents,
  subscribeEventStatus,
  type ConnectionStatus,
  type SyncEvent,
} from '../../api/client'
import { sidecarQueryKey, updateConflictFromServer } from '../../api/items'
import type { PresenceEvent, Sidecar, StarRating } from '../../lib/types'
import type { ItemCacheUpdatePayload } from '../model/appShellStateSync'
import type { RecentActivityKind } from '../presenceActivity'

type UseAppSyncEventsParams = {
  queryClient: QueryClient
  updateItemCaches: (payload: ItemCacheUpdatePayload) => void
  setLocalStarOverrides: Dispatch<SetStateAction<Record<string, StarRating>>>
  applyPresenceCounts: (counts: PresenceEvent[]) => void
  markRecentActivity: (path: string, eventType: RecentActivityKind, eventId: number | null) => void
  markRecentTouch: (path: string, eventType: RecentActivityKind, updatedAt?: string | null) => void
  updateLastEdited: (updatedAt?: string | null) => void
}

export function getConnectionLabel(status: ConnectionStatus): string {
  switch (status) {
    case 'live':
      return 'Live'
    case 'reconnecting':
      return 'Reconnecting…'
    case 'offline':
      return 'Offline'
    case 'connecting':
    case 'idle':
    default:
      return 'Connecting…'
  }
}

export function useAppSyncEvents({
  queryClient,
  updateItemCaches,
  setLocalStarOverrides,
  applyPresenceCounts,
  markRecentActivity,
  markRecentTouch,
  updateLastEdited,
}: UseAppSyncEventsParams): ConnectionStatus {
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')

  useEffect(() => {
    connectEvents()
    const offEvents = subscribeEvents((evt: SyncEvent) => {
      if (evt.type === 'presence') {
        const data = evt.data
        if (!data?.gallery_id) return
        applyPresenceCounts([data])
        return
      }

      const data = evt.data as { path?: string }
      if (!data?.path) return
      const path = data.path

      if (evt.type === 'item-updated') {
        const payload = evt.data
        const sidecar: Sidecar = {
          v: 1,
          tags: payload.tags ?? [],
          notes: payload.notes ?? '',
          star: payload.star ?? null,
          version: payload.version ?? 1,
          updated_at: payload.updated_at ?? '',
          updated_by: payload.updated_by ?? 'server',
        }
        queryClient.setQueryData(sidecarQueryKey(path), sidecar)
        updateItemCaches({
          path,
          star: payload.star ?? null,
          metrics: payload.metrics,
          notes: payload.notes ?? '',
        })
        void queryClient.resetQueries({ queryKey: ['folder-query'] })
        queryClient.invalidateQueries({ queryKey: ['folder-facets'] })
        updateConflictFromServer(path, sidecar)
        markRecentActivity(path, 'item-updated', evt.id)
        markRecentTouch(path, 'item-updated', payload.updated_at)
        updateLastEdited(payload.updated_at)
        setLocalStarOverrides((prev) => {
          if (prev[path] === undefined) return prev
          const next = { ...prev }
          delete next[path]
          return next
        })
      } else if (evt.type === 'metrics-updated') {
        const payload = evt.data
        updateItemCaches({ path, metrics: payload.metrics })
        void queryClient.resetQueries({ queryKey: ['folder-query'] })
        queryClient.invalidateQueries({ queryKey: ['folder-facets'] })
        markRecentActivity(path, 'metrics-updated', evt.id)
        markRecentTouch(path, 'metrics-updated', payload.updated_at)
        updateLastEdited(payload.updated_at)
      }
    })
    const offStatus = subscribeEventStatus(setConnectionStatus)
    return () => {
      offEvents()
      offStatus()
      disconnectEvents()
    }
  }, [
    applyPresenceCounts,
    markRecentActivity,
    markRecentTouch,
    queryClient,
    setLocalStarOverrides,
    updateItemCaches,
    updateLastEdited,
  ])

  return connectionStatus
}
