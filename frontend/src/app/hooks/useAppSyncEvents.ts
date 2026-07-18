import { useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import {
  api,
  connectEvents,
  disconnectEvents,
  subscribeEvents,
  subscribeEventStatus,
  type ConnectionStatus,
  type SyncEvent,
} from '../../api/client'
import {
  labelPersistenceTracker,
  subscribeLabelPersistenceRefresh,
} from '../../api/labelPersistence'
import {
  sidecarQueryKey,
  subscribeAnnotationMutationResponses,
  updateConflictFromServer,
} from '../../api/items'
import type {
  AcceptedEventIdentity,
  LabelPersistenceState,
  PresenceEvent,
  Sidecar,
  StarRating,
} from '../../lib/types'
import {
  AnnotationReconciler,
  type ItemCacheUpdateOptions,
  type ItemCacheUpdatePayload,
} from '../model/appShellStateSync'
import type { RecentActivityKind } from '../presenceActivity'

const FIELD_SCHEMA_REFRESH_DEBOUNCE_MS = 250
const PERSISTENCE_REPAIR_RETRY_DELAYS_MS = [250, 500, 1000, 2000, 4000] as const

export function createFieldSchemaRefreshScheduler(
  refresh: () => void,
  delayMs = FIELD_SCHEMA_REFRESH_DEBOUNCE_MS,
): { schedule: () => void; cancel: () => void } {
  let timer: ReturnType<typeof globalThis.setTimeout> | null = null
  return {
    schedule: () => {
      if (timer !== null) globalThis.clearTimeout(timer)
      timer = globalThis.setTimeout(() => {
        timer = null
        refresh()
      }, delayMs)
    },
    cancel: () => {
      if (timer !== null) globalThis.clearTimeout(timer)
      timer = null
    },
  }
}

export function createBoundedRetryScheduler(
  retry: () => void,
  delays: readonly number[] = PERSISTENCE_REPAIR_RETRY_DELAYS_MS,
): { schedule: () => void; reset: () => void; cancel: () => void } {
  let attempt = 0
  let timer: ReturnType<typeof globalThis.setTimeout> | null = null
  const clear = () => {
    if (timer !== null) globalThis.clearTimeout(timer)
    timer = null
  }
  return {
    schedule: () => {
      if (timer !== null || attempt >= delays.length) return
      const delay = delays[attempt]
      attempt += 1
      timer = globalThis.setTimeout(() => {
        timer = null
        retry()
      }, delay)
    },
    reset: () => {
      clear()
      attempt = 0
    },
    cancel: () => {
      clear()
      attempt = delays.length
    },
  }
}

type UseAppSyncEventsParams = {
  queryClient: QueryClient
  updateItemCaches: (payload: ItemCacheUpdatePayload, options?: ItemCacheUpdateOptions) => void
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
  const updateItemCachesRef = useRef(updateItemCaches)
  updateItemCachesRef.current = updateItemCaches
  const reconcilerRef = useRef<{
    queryClient: QueryClient
    reconciler: AnnotationReconciler
  } | null>(null)
  if (!reconcilerRef.current || reconcilerRef.current.queryClient !== queryClient) {
    reconcilerRef.current = {
      queryClient,
      reconciler: new AnnotationReconciler(
        queryClient,
        (payload, options) => updateItemCachesRef.current(payload, options),
      ),
    }
  }

  useEffect(() => {
    const reconciler = reconcilerRef.current?.reconciler
    if (!reconciler) return
    const fieldSchemaRefresh = createFieldSchemaRefreshScheduler(() => {
      void queryClient.invalidateQueries({
        queryKey: ['folder-fields'],
        refetchType: 'active',
      })
    })
    let active = true
    let reconnectStateRequest = 0
    const persistenceRepairRetry = createBoundedRetryScheduler(() => {
      void refreshPersistenceStatus()
    })

    const applyPersistenceStatus = async (
      status: LabelPersistenceState,
      source: 'sync' | 'event',
    ) => {
      const repairs = labelPersistenceTracker.observeStatus(status, source)
      if (!repairs.length) return
      const invalidations = repairs.flatMap(({ path }) => [
        queryClient.invalidateQueries({
          queryKey: sidecarQueryKey(path),
          exact: true,
          refetchType: 'active',
        }, { throwOnError: true }),
        queryClient.invalidateQueries({
          queryKey: ['item-detail', path],
          exact: true,
          refetchType: 'active',
        }, { throwOnError: true }),
      ])
      await Promise.all([...invalidations, reconciler.reconcileAll()])
      if (active) labelPersistenceTracker.acknowledgeRepairs(repairs)
    }

    const refreshPersistenceStatus = async () => {
      reconnectStateRequest += 1
      const requestId = reconnectStateRequest
      try {
        const status = await api.getSyncState()
        if (!active || requestId !== reconnectStateRequest) return
        await applyPersistenceStatus(status, 'sync')
        persistenceRepairRetry.reset()
      } catch {
        if (active) persistenceRepairRetry.schedule()
      }
    }

    const mutationIdentity = (
      payload: { mutation_id?: string; path: string; version?: number; updated_at?: string },
      eventType: RecentActivityKind,
      eventId: number | null,
    ): string => payload.mutation_id
      || `${eventType}:event:${eventId ?? `${payload.path}:${payload.version ?? 0}:${payload.updated_at ?? ''}`}`

    const applyItemUpdate = (
      payload: {
        path: string
        tags?: string[]
        notes?: string
        star?: StarRating | null
        version?: number
        updated_at?: string
        updated_by?: string
        mutation_id?: string
        changed_fields?: string[]
        metrics?: Record<string, number | null>
        accepted_event?: AcceptedEventIdentity | null
        persistence?: 'pending' | 'saved'
        durable_watermark?: AcceptedEventIdentity
      },
      eventId: number | null,
    ) => {
      const accepted = reconciler.accept({
        mutationId: mutationIdentity(payload, 'item-updated', eventId),
        changedFields: payload.changed_fields ?? ['unknown'],
        item: {
          path: payload.path,
          star: payload.star ?? null,
          metrics: payload.metrics,
          notes: payload.notes ?? '',
        },
        replaceMutableMetrics: payload.metrics !== undefined,
      })
      if (!accepted) return
      if (payload.accepted_event && payload.durable_watermark) {
        labelPersistenceTracker.observeAccepted(
          payload.path,
          payload.accepted_event,
          payload.persistence ?? 'pending',
          payload.durable_watermark,
        )
      }
      const existing = queryClient.getQueryData<Sidecar>(sidecarQueryKey(payload.path))
      const sidecar: Sidecar = {
        ...existing,
        v: 1,
        tags: payload.tags ?? [],
        notes: payload.notes ?? '',
        star: payload.star ?? null,
        version: payload.version ?? 1,
        updated_at: payload.updated_at ?? '',
        updated_by: payload.updated_by ?? 'server',
      }
      queryClient.setQueryData(sidecarQueryKey(payload.path), sidecar)
      updateConflictFromServer(payload.path, sidecar)
      markRecentActivity(payload.path, 'item-updated', eventId)
      markRecentTouch(payload.path, 'item-updated', payload.updated_at)
      updateLastEdited(payload.updated_at)
      setLocalStarOverrides((prev) => {
        if (prev[payload.path] === undefined) return prev
        const next = { ...prev }
        delete next[payload.path]
        return next
      })
    }

    const offMutationResponses = subscribeAnnotationMutationResponses((mutation) => {
      applyItemUpdate({
        ...mutation.response.sidecar,
        path: mutation.path,
        mutation_id: mutation.response.mutation_id,
        changed_fields: mutation.changedFields,
      }, null)
    })

    connectEvents()
    const offEvents = subscribeEvents((evt: SyncEvent) => {
      if (evt.type === 'persistence') {
        void applyPersistenceStatus(evt.data, 'event').then(
          persistenceRepairRetry.reset,
          persistenceRepairRetry.schedule,
        )
        return
      }
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
        applyItemUpdate({ ...payload, path }, evt.id)
      } else if (evt.type === 'metrics-updated') {
        const payload = evt.data
        const accepted = reconciler.accept({
          mutationId: mutationIdentity(payload, 'metrics-updated', evt.id),
          changedFields: payload.changed_fields ?? ['unknown'],
          item: { path, metrics: payload.metrics },
          replaceMutableMetrics: true,
        })
        if (!accepted) return
        if (payload.accepted_event && payload.durable_watermark) {
          labelPersistenceTracker.observeAccepted(
            path,
            payload.accepted_event,
            payload.persistence ?? 'pending',
            payload.durable_watermark,
          )
        }
        fieldSchemaRefresh.schedule()
        markRecentActivity(path, 'metrics-updated', evt.id)
        markRecentTouch(path, 'metrics-updated', payload.updated_at)
        updateLastEdited(payload.updated_at)
      }
    })
    const offStatus = subscribeEventStatus((status) => {
      setConnectionStatus(status)
      if (status === 'live') void refreshPersistenceStatus()
    })
    const offPersistenceRefresh = subscribeLabelPersistenceRefresh(() => {
      void refreshPersistenceStatus()
    })
    return () => {
      active = false
      reconnectStateRequest += 1
      fieldSchemaRefresh.cancel()
      persistenceRepairRetry.cancel()
      offMutationResponses()
      offEvents()
      offStatus()
      offPersistenceRefresh()
      disconnectEvents()
    }
  }, [
    applyPresenceCounts,
    markRecentActivity,
    markRecentTouch,
    queryClient,
    setLocalStarOverrides,
    updateLastEdited,
  ])

  return connectionStatus
}
