import { useCallback, useEffect, useRef } from 'react'
import {
  api,
  dispatchPresenceLeave,
  type ConnectionStatus,
} from '../../api/client'
import type { PresenceEvent } from '../../lib/types'
import { FetchError } from '../../lib/fetcher'
import {
  PRESENCE_HEARTBEAT_MS,
  PRESENCE_MOVE_COALESCE_MS,
} from '../../lib/constants'

type PresenceScopeResponse = PresenceEvent & { lease_id: string }

type UsePresenceLeaseLifecycleParams = {
  currentGalleryId: string
  connectionStatus: ConnectionStatus
  applyPresenceCounts: (counts: PresenceEvent[]) => void
  clearPresenceScope: (galleryId: string | null) => void
}

function getPresenceErrorCode(error: unknown): string | null {
  if (!(error instanceof FetchError)) return null
  const body = error.body
  if (!body || typeof body !== 'object') return null
  const code = (body as Record<string, unknown>).error
  return typeof code === 'string' ? code : null
}

export function usePresenceLeaseLifecycle({
  currentGalleryId,
  connectionStatus,
  applyPresenceCounts,
  clearPresenceScope,
}: UsePresenceLeaseLifecycleParams): void {
  const presenceLeaseIdRef = useRef<string | null>(null)
  const activePresenceGalleryRef = useRef<string | null>(null)
  const pendingPresenceGalleryRef = useRef<string | null>(null)
  const presenceTransitionInFlightRef = useRef(false)
  const presenceMoveTimerRef = useRef<number | null>(null)
  const prevConnectionStatusRef = useRef<ConnectionStatus>('idle')

  const clearPresenceMoveTimer = useCallback(() => {
    if (presenceMoveTimerRef.current == null) return
    window.clearTimeout(presenceMoveTimerRef.current)
    presenceMoveTimerRef.current = null
  }, [])

  const applyJoinedPresence = useCallback((response: PresenceScopeResponse) => {
    presenceLeaseIdRef.current = response.lease_id
    activePresenceGalleryRef.current = response.gallery_id
    applyPresenceCounts([response])
  }, [applyPresenceCounts])

  const joinPresenceScope = useCallback(async (galleryId: string, forceNewLease = false) => {
    const preferredLease = forceNewLease ? undefined : (presenceLeaseIdRef.current ?? undefined)
    const join = (leaseId?: string) => api.joinPresence(galleryId, leaseId)
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
    dispatchPresenceLeave(galleryId, leaseId)
    if (clearLocal) {
      clearPresenceScope(galleryId)
    }
    clearPresenceSessionRefs()
  }, [clearPresenceScope, clearPresenceSessionRefs])

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
}
