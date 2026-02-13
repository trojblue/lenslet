import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { QueryClient } from '@tanstack/react-query'
import {
  api,
  connectEvents,
  disconnectEvents,
  dispatchPresenceLeave,
  getClientId,
  subscribeEvents,
  subscribeEventStatus,
} from '../../shared/api/client'
import type { ConnectionStatus, SyncEvent } from '../../shared/api/client'
import { sidecarQueryKey, updateConflictFromServer } from '../../shared/api/items'
import type { Item, PresenceEvent, Sidecar, StarRating } from '../../lib/types'
import { FetchError } from '../../lib/fetcher'
import { formatAbsoluteTime, formatRelativeTime, parseTimestampMs } from '../../lib/util'
import {
  LAST_EDIT_RELATIVE_MS,
  PRESENCE_HEARTBEAT_MS,
  PRESENCE_MOVE_COALESCE_MS,
  RECENT_EDIT_FLASH_MS,
} from '../../lib/constants'
import {
  buildRecentSummary,
  buildRecentTouchesDisplay,
  usePresenceActivity,
  type RecentSummary,
  type RecentTouchDisplay,
} from '../presenceActivity'
import {
  indexingEquals,
  nextIndexingPollDelayMs,
  normalizeHealthIndexing,
  shouldContinueIndexingPoll,
  type HealthIndexing,
} from './healthIndexing'
import {
  compareExportCapabilityEquals,
  DEFAULT_COMPARE_EXPORT_CAPABILITY,
  normalizeHealthCompareExport,
  type CompareExportCapability,
} from './healthCompareExport'

type ItemCacheUpdatePayload = {
  path: string
  star?: StarRating | null
  metrics?: Record<string, number | null> | null
  comments?: string | null
}

type UseAppPresenceSyncParams = {
  current: string
  currentGalleryId: string
  itemPaths: string[]
  items: Item[]
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
  indexing: HealthIndexing | null
  compareExportCapability: CompareExportCapability
  highlightedPaths: Map<string, string>
  onVisiblePathsChange: (paths: Set<string>) => void
  offViewSummary: RecentSummary | null
  recentTouchesDisplay: RecentTouchDisplay[]
  clearOffViewActivity: () => void
}

const HEALTH_POLL_RUNNING_MS = 1_200
const HEALTH_POLL_RETRY_MS = 3_000

function getConnectionLabel(status: ConnectionStatus): string {
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

function getPresenceErrorCode(error: unknown): string | null {
  if (!(error instanceof FetchError)) return null
  const body = error.body
  if (!body || typeof body !== 'object') return null
  const code = (body as Record<string, unknown>).error
  return typeof code === 'string' ? code : null
}

function formatTimestampLabel(timestampMs: number, nowMs: number): string {
  if (nowMs - timestampMs < LAST_EDIT_RELATIVE_MS) {
    return formatRelativeTime(timestampMs, nowMs)
  }
  return formatAbsoluteTime(timestampMs)
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
  const presenceClientIdRef = useRef<string>(getClientId())
  const presenceLeaseIdRef = useRef<string | null>(null)
  const activePresenceGalleryRef = useRef<string | null>(null)
  const pendingPresenceGalleryRef = useRef<string | null>(null)
  const presenceTransitionInFlightRef = useRef(false)
  const presenceMoveTimerRef = useRef<number | null>(null)
  const prevConnectionStatusRef = useRef<ConnectionStatus>('idle')

  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('idle')
  const [presenceByGallery, setPresenceByGallery] = useState<Record<string, PresenceEvent>>({})
  const [lastEditedAt, setLastEditedAt] = useState<number | null>(null)
  const [recentEditAt, setRecentEditAt] = useState<number | null>(null)
  const [recentEditActive, setRecentEditActive] = useState(false)
  const [lastEditedNow, setLastEditedNow] = useState(() => Date.now())
  const [persistenceEnabled, setPersistenceEnabled] = useState(true)
  const [indexing, setIndexing] = useState<HealthIndexing | null>(null)
  const [compareExportCapability, setCompareExportCapability] = useState<CompareExportCapability>(
    DEFAULT_COMPARE_EXPORT_CAPABILITY,
  )

  useEffect(() => {
    if (recentEditAt == null) {
      setRecentEditActive(false)
      return
    }
    setRecentEditActive(true)
    const id = window.setTimeout(() => setRecentEditActive(false), RECENT_EDIT_FLASH_MS)
    return () => window.clearTimeout(id)
  }, [recentEditAt])

  useEffect(() => {
    if (lastEditedAt == null) return
    setLastEditedNow(Date.now())
    const id = window.setInterval(() => setLastEditedNow(Date.now()), 10_000)
    return () => window.clearInterval(id)
  }, [lastEditedAt])

  const {
    offViewActivity,
    recentTouches,
    highlightedPaths,
    onVisiblePathsChange,
    markRecentActivity,
    markRecentTouch,
    clearOffViewActivity,
  } = usePresenceActivity(itemPaths)

  const updateLastEdited = useCallback((updatedAt?: string | null) => {
    const now = Date.now()
    const parsed = parseTimestampMs(updatedAt)
    const candidate = parsed ?? now
    const safeCandidate = candidate > now ? now : candidate
    setLastEditedAt((prev) => {
      if (prev == null) return safeCandidate
      return prev > safeCandidate ? prev : safeCandidate
    })
    setRecentEditAt(now)
    setLastEditedNow(now)
  }, [])

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

  const clearPresenceMoveTimer = useCallback(() => {
    if (presenceMoveTimerRef.current == null) return
    window.clearTimeout(presenceMoveTimerRef.current)
    presenceMoveTimerRef.current = null
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

  const applyJoinedPresence = useCallback((response: PresenceEvent & { lease_id: string }) => {
    presenceLeaseIdRef.current = response.lease_id
    activePresenceGalleryRef.current = response.gallery_id
    applyPresenceCounts([response])
  }, [applyPresenceCounts])

  const joinPresenceScope = useCallback(async (galleryId: string, forceNewLease = false) => {
    const clientId = presenceClientIdRef.current
    const preferredLease = forceNewLease ? undefined : (presenceLeaseIdRef.current ?? undefined)
    const join = (leaseId?: string) => api.joinPresence(galleryId, leaseId, clientId)
    try {
      applyJoinedPresence(await join(preferredLease))
      return
    } catch (error) {
      if (!forceNewLease && getPresenceErrorCode(error) === 'invalid_lease') {
        applyJoinedPresence(await join(undefined))
        return
      }
      throw error
    }
  }, [applyJoinedPresence])

  const movePresenceScope = useCallback(async (fromGalleryId: string, toGalleryId: string) => {
    if (fromGalleryId === toGalleryId) {
      await joinPresenceScope(toGalleryId)
      return
    }

    const leaseId = presenceLeaseIdRef.current
    if (!leaseId) {
      await joinPresenceScope(toGalleryId, true)
      return
    }

    try {
      const response = await api.movePresence(
        fromGalleryId,
        toGalleryId,
        leaseId,
        presenceClientIdRef.current,
      )
      activePresenceGalleryRef.current = response.to_scope.gallery_id
      applyPresenceCounts([response.from_scope, response.to_scope])
      return
    } catch (error) {
      const code = getPresenceErrorCode(error)
      if (code === 'invalid_lease') {
        await joinPresenceScope(toGalleryId, true)
        return
      }
      if (code === 'scope_mismatch') {
        await joinPresenceScope(toGalleryId)
        return
      }
      throw error
    }
  }, [applyPresenceCounts, joinPresenceScope])

  const syncPresenceScope = useCallback(async (targetGalleryId: string) => {
    const activeGalleryId = activePresenceGalleryRef.current
    if (!activeGalleryId) {
      await joinPresenceScope(targetGalleryId, true)
      return
    }
    if (activeGalleryId === targetGalleryId) {
      await joinPresenceScope(targetGalleryId)
      return
    }
    await movePresenceScope(activeGalleryId, targetGalleryId)
  }, [joinPresenceScope, movePresenceScope])

  const flushPendingPresenceTransition = useCallback(async () => {
    if (presenceTransitionInFlightRef.current) return
    const targetGalleryId = pendingPresenceGalleryRef.current
    if (!targetGalleryId) return
    pendingPresenceGalleryRef.current = null
    presenceTransitionInFlightRef.current = true

    try {
      await syncPresenceScope(targetGalleryId)
    } catch {
      // Presence lifecycle calls are best-effort; keep UI responsive on failures.
    } finally {
      presenceTransitionInFlightRef.current = false
      const pending = pendingPresenceGalleryRef.current
      if (pending && pending !== activePresenceGalleryRef.current) {
        void flushPendingPresenceTransition()
      }
    }
  }, [syncPresenceScope])

  const schedulePresenceTransition = useCallback((targetGalleryId: string, immediate = false) => {
    pendingPresenceGalleryRef.current = targetGalleryId
    clearPresenceMoveTimer()
    if (immediate || activePresenceGalleryRef.current == null) {
      void flushPendingPresenceTransition()
      return
    }
    presenceMoveTimerRef.current = window.setTimeout(() => {
      presenceMoveTimerRef.current = null
      void flushPendingPresenceTransition()
    }, PRESENCE_MOVE_COALESCE_MS)
  }, [clearPresenceMoveTimer, flushPendingPresenceTransition])

  const clearPresenceSessionRefs = useCallback(() => {
    activePresenceGalleryRef.current = null
    presenceLeaseIdRef.current = null
    pendingPresenceGalleryRef.current = null
    clearPresenceMoveTimer()
  }, [clearPresenceMoveTimer])

  const signalPresenceLeave = useCallback((clearLocal: boolean) => {
    const galleryId = activePresenceGalleryRef.current
    const leaseId = presenceLeaseIdRef.current
    if (!galleryId || !leaseId) return
    dispatchPresenceLeave(galleryId, leaseId, presenceClientIdRef.current)
    if (clearLocal) {
      clearPresenceScope(galleryId)
    }
    clearPresenceSessionRefs()
  }, [clearPresenceScope, clearPresenceSessionRefs])

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
          comments: payload.notes ?? '',
        })
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

  useEffect(() => {
    const activeGalleryId = activePresenceGalleryRef.current
    if (activeGalleryId === currentGalleryId) return
    schedulePresenceTransition(currentGalleryId, activeGalleryId == null)
  }, [currentGalleryId, schedulePresenceTransition])

  useEffect(() => {
    const id = window.setInterval(() => {
      const activeGalleryId = activePresenceGalleryRef.current
      if (!activeGalleryId) return
      void joinPresenceScope(activeGalleryId)
    }, PRESENCE_HEARTBEAT_MS)
    return () => {
      window.clearInterval(id)
    }
  }, [joinPresenceScope])

  useEffect(() => {
    const previous = prevConnectionStatusRef.current
    prevConnectionStatusRef.current = connectionStatus
    if (connectionStatus === 'live' && previous !== 'live') {
      schedulePresenceTransition(currentGalleryId, true)
      return
    }
    if (connectionStatus === 'reconnecting' || connectionStatus === 'offline') {
      clearPresenceScope(activePresenceGalleryRef.current)
    }
  }, [clearPresenceScope, connectionStatus, currentGalleryId, schedulePresenceTransition])

  useEffect(() => {
    const onPageHide = () => signalPresenceLeave(true)
    const onBeforeUnload = () => signalPresenceLeave(true)
    const onPageShow = () => {
      schedulePresenceTransition(currentGalleryId, true)
    }
    window.addEventListener('pagehide', onPageHide)
    window.addEventListener('beforeunload', onBeforeUnload)
    window.addEventListener('pageshow', onPageShow)
    return () => {
      window.removeEventListener('pagehide', onPageHide)
      window.removeEventListener('beforeunload', onBeforeUnload)
      window.removeEventListener('pageshow', onPageShow)
      signalPresenceLeave(false)
    }
  }, [currentGalleryId, schedulePresenceTransition, signalPresenceLeave])

  useEffect(() => {
    let cancelled = false
    let timerId: number | null = null

    const clearPollTimer = () => {
      if (timerId == null) return
      window.clearTimeout(timerId)
      timerId = null
    }

    const schedulePoll = (ms: number) => {
      clearPollTimer()
      timerId = window.setTimeout(() => {
        void pollHealth()
      }, ms)
    }

    const pollHealth = async () => {
      try {
        const health = await api.getHealth()
        if (cancelled) return

        setPersistenceEnabled(health?.labels?.enabled ?? true)
        const nextIndexing = normalizeHealthIndexing(health?.indexing)
        setIndexing((prev) => (indexingEquals(prev, nextIndexing) ? prev : nextIndexing))
        const nextCompareExportCapability = normalizeHealthCompareExport(health?.compare_export)
        setCompareExportCapability((prev) => (
          compareExportCapabilityEquals(prev, nextCompareExportCapability)
            ? prev
            : nextCompareExportCapability
        ))

        if (shouldContinueIndexingPoll(nextIndexing)) {
          schedulePoll(nextIndexingPollDelayMs(nextIndexing, HEALTH_POLL_RUNNING_MS, HEALTH_POLL_RETRY_MS))
        }
      } catch {
        if (cancelled) return
        schedulePoll(HEALTH_POLL_RETRY_MS)
      }
    }

    void pollHealth()
    return () => {
      cancelled = true
      clearPollTimer()
    }
  }, [])

  const presence = presenceByGallery[current]
  const editingCount = presence?.editing ?? 0
  const hasEdits = lastEditedAt != null
  const connectionLabel = useMemo(() => getConnectionLabel(connectionStatus), [connectionStatus])
  const lastEditedLabel = useMemo(() => {
    if (!hasEdits || lastEditedAt == null) return 'No edits yet.'
    return formatTimestampLabel(lastEditedAt, lastEditedNow)
  }, [hasEdits, lastEditedAt, lastEditedNow])

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
    indexing,
    compareExportCapability,
    highlightedPaths,
    onVisiblePathsChange,
    offViewSummary,
    recentTouchesDisplay,
    clearOffViewActivity,
  }
}
