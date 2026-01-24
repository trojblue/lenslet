import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, makeIdempotencyKey } from './client'
import { usePollingEnabled } from './polling'
import { FetchError } from '../lib/fetcher'
import type { Sidecar, SidecarPatch } from '../lib/types'

/** Query key for sidecar data */
export const sidecarQueryKey = (path: string) => ['item', path] as const

type UpdateFields = Partial<Omit<Sidecar, 'v' | 'version' | 'updated_at' | 'updated_by'>>

export type SyncStatus = {
  state: 'idle' | 'syncing' | 'error'
  message?: string
}

export type ConflictEntry = {
  path: string
  current: Sidecar
  pending: SidecarPatch
  receivedAt: string
}

/** Default sidecar for new items */
const DEFAULT_SIDECAR: Sidecar = {
  v: 1,
  tags: [],
  notes: '',
  version: 1,
  updated_at: '',
  updated_by: 'web',
}

/** Pending patches keyed by path, waiting to be flushed. */
const pendingPatches = new Map<string, UpdateFields>()

/** In-flight flush operations keyed by path. */
const inflightByPath = new Map<string, Promise<void>>()

const conflictByPath = new Map<string, ConflictEntry>()
const conflictListeners = new Map<string, Set<(entry: ConflictEntry | null) => void>>()

const FALLBACK_SIDECAR_INTERVAL = 12_000

const syncListeners = new Set<(status: SyncStatus) => void>()
let syncState: SyncStatus = { state: 'idle' }
let syncError: string | null = null
let directInflight = 0

function notifySync(next: SyncStatus) {
  syncState = next
  for (const listener of syncListeners) {
    listener(next)
  }
}

function updateSyncState() {
  const hasConflict = conflictByPath.size > 0
  const pending = pendingPatches.size + inflightByPath.size + directInflight
  if (hasConflict) {
    notifySync({ state: 'error', message: 'Conflict detected' })
    return
  }
  if (syncError) {
    notifySync({ state: 'error', message: syncError })
    return
  }
  if (pending > 0) {
    notifySync({ state: 'syncing' })
    return
  }
  notifySync({ state: 'idle' })
}

function setSyncError(message: string) {
  syncError = message
  updateSyncState()
}

function clearSyncError() {
  if (!syncError) return
  syncError = null
  updateSyncState()
}

function bumpDirectInflight(delta: number) {
  directInflight = Math.max(0, directInflight + delta)
  updateSyncState()
}

function notifyConflict(path: string) {
  const listeners = conflictListeners.get(path)
  if (!listeners || !listeners.size) return
  const entry = conflictByPath.get(path) ?? null
  for (const listener of listeners) {
    listener(entry)
  }
}

export function getConflict(path: string): ConflictEntry | null {
  return conflictByPath.get(path) ?? null
}

export function clearConflict(path: string): void {
  if (!conflictByPath.delete(path)) return
  notifyConflict(path)
  updateSyncState()
}

function setConflict(path: string, entry: ConflictEntry): void {
  conflictByPath.set(path, entry)
  notifyConflict(path)
  updateSyncState()
}

export function subscribeConflict(path: string, listener: (entry: ConflictEntry | null) => void): () => void {
  const listeners = conflictListeners.get(path) ?? new Set()
  listeners.add(listener)
  conflictListeners.set(path, listeners)
  listener(conflictByPath.get(path) ?? null)
  return () => {
    const current = conflictListeners.get(path)
    if (!current) return
    current.delete(listener)
    if (!current.size) conflictListeners.delete(path)
  }
}

export function useSidecarConflict(path: string | null) {
  const [entry, setEntry] = useState<ConflictEntry | null>(() => (path ? getConflict(path) : null))

  useEffect(() => {
    if (!path) {
      setEntry(null)
      return
    }
    setEntry(getConflict(path))
    return subscribeConflict(path, setEntry)
  }, [path])

  return entry
}

export function subscribeSyncStatus(listener: (status: SyncStatus) => void): () => void {
  syncListeners.add(listener)
  listener(syncState)
  return () => {
    syncListeners.delete(listener)
  }
}

export function useSyncStatus() {
  const [status, setStatus] = useState<SyncStatus>(syncState)

  useEffect(() => {
    return subscribeSyncStatus(setStatus)
  }, [])

  return status
}

function buildPatch(fields: UpdateFields): SidecarPatch {
  const patch: SidecarPatch = {}
  if (Object.prototype.hasOwnProperty.call(fields, 'star')) {
    patch.set_star = fields.star ?? null
  }
  if (Object.prototype.hasOwnProperty.call(fields, 'notes')) {
    patch.set_notes = fields.notes ?? ''
  }
  if (Object.prototype.hasOwnProperty.call(fields, 'tags')) {
    patch.set_tags = Array.isArray(fields.tags) ? fields.tags : []
  }
  return patch
}

function hasPatchFields(patch: SidecarPatch): boolean {
  return (
    patch.set_star !== undefined ||
    patch.set_notes !== undefined ||
    patch.set_tags !== undefined ||
    (patch.add_tags?.length ?? 0) > 0 ||
    (patch.remove_tags?.length ?? 0) > 0
  )
}

function normalizeTags(values: string[] | null | undefined): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const raw of values ?? []) {
    if (typeof raw !== 'string') continue
    const val = raw.trim()
    if (!val || seen.has(val)) continue
    seen.add(val)
    out.push(val)
  }
  return out
}

function tagsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false
  }
  return true
}

function isPatchSatisfied(patch: SidecarPatch, current: Sidecar): boolean {
  if (patch.set_star !== undefined && (current.star ?? null) !== patch.set_star) {
    return false
  }
  if (patch.set_notes !== undefined && (current.notes ?? '') !== (patch.set_notes ?? '')) {
    return false
  }
  if (patch.set_tags !== undefined) {
    const wanted = normalizeTags(patch.set_tags)
    const existing = normalizeTags(current.tags)
    return tagsEqual(wanted, existing)
  }
  const existing = normalizeTags(current.tags)
  for (const tag of normalizeTags(patch.add_tags)) {
    if (!existing.includes(tag)) return false
  }
  for (const tag of normalizeTags(patch.remove_tags)) {
    if (existing.includes(tag)) return false
  }
  return true
}

function captureConflict(path: string, patch: SidecarPatch, err: unknown): boolean {
  if (err instanceof FetchError && err.status === 409) {
    const body = err.body as { current?: Sidecar } | null
    if (body?.current) {
      setConflict(path, {
        path,
        current: body.current,
        pending: patch,
        receivedAt: new Date().toISOString(),
      })
      return true
    }
  }
  return false
}

export function updateConflictFromServer(path: string, current: Sidecar): void {
  const existing = conflictByPath.get(path)
  if (!existing) return
  if (isPatchSatisfied(existing.pending, current)) {
    clearConflict(path)
    return
  }
  conflictByPath.set(path, { ...existing, current })
  notifyConflict(path)
  updateSyncState()
}

/**
 * Hook to fetch sidecar metadata for an item.
 */
export function useSidecar(path: string) {
  const pollingEnabled = usePollingEnabled()
  return useQuery({
    queryKey: sidecarQueryKey(path),
    queryFn: () => api.getSidecar(path),
    enabled: !!path,
    staleTime: 30_000, // Sidecar data doesn't change often
    gcTime: 5 * 60_000,
    retry: 2,
    refetchInterval: pollingEnabled ? FALLBACK_SIDECAR_INTERVAL : false,
    refetchIntervalInBackground: pollingEnabled,
  })
}

/**
 * Hook to update sidecar metadata with patch semantics.
 * Optimistically updates the cache on success.
 */
export function useUpdateSidecar(path: string) {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({ patch, baseVersion, idempotencyKey }: { patch: UpdateFields; baseVersion: number; idempotencyKey?: string }) => {
      const body = buildPatch(patch)
      if (!hasPatchFields(body)) {
        return qc.getQueryData<Sidecar>(sidecarQueryKey(path)) ?? DEFAULT_SIDECAR
      }
      const payload = { ...body, base_version: baseVersion }
      try {
        return await api.patchSidecar(path, payload, {
          idempotencyKey: idempotencyKey ?? makeIdempotencyKey('patch'),
          ifMatch: baseVersion,
        })
      } catch (err) {
        captureConflict(path, body, err)
        throw err
      }
    },
    retry: (attempt, err) => {
      if (err instanceof FetchError && err.status === 409) return false
      return attempt < 2
    },
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 4000),
    onMutate: () => {
      clearSyncError()
      bumpDirectInflight(1)
    },
    onSuccess: (data) => {
      clearConflict(path)
      qc.setQueryData(sidecarQueryKey(path), data)
    },
    onError: (err) => {
      if (err instanceof FetchError && err.status === 409) return
      if (err instanceof FetchError) {
        setSyncError(err.message)
      } else {
        setSyncError('Failed to save')
      }
    },
    onSettled: () => {
      bumpDirectInflight(-1)
    },
  })
}

/** Concurrency limit for bulk operations */
const BULK_CONCURRENCY = 6

/**
 * Update multiple sidecars with the same partial data.
 * Uses a worker pool to limit concurrent requests.
 */
export async function bulkUpdateSidecars(
  paths: string[],
  fields: UpdateFields
): Promise<void> {
  if (!paths.length) return

  let idx = 0
  const errors: Array<{ path: string; error: unknown }> = []

  const worker = async (): Promise<void> => {
    while (idx < paths.length) {
      const currentIdx = idx++
      const p = paths[currentIdx]
      try {
        await queueSidecarUpdate(p, fields)
      } catch (error) {
        errors.push({ path: p, error })
        // Log but don't stop other updates
        console.error(`[bulkUpdateSidecars] Failed for ${p}:`, error)
      }
    }
  }

  // Start workers
  const workers = Array.from(
    { length: Math.min(BULK_CONCURRENCY, paths.length) },
    () => worker()
  )
  await Promise.all(workers)

  // If all failed, throw
  if (errors.length === paths.length) {
    throw new Error(`All ${paths.length} sidecar updates failed`)
  }
}

/**
 * Queue a sidecar update for a path. Coalesces rapid updates.
 * Returns a promise that resolves when the update is persisted.
 */
export async function queueSidecarUpdate(
  path: string,
  patch: UpdateFields
): Promise<void> {
  // Merge with any pending patch for this path
  const existing = pendingPatches.get(path) || {}
  pendingPatches.set(path, { ...existing, ...patch })
  clearSyncError()
  updateSyncState()

  // If already flushing, the existing flush will pick up this patch
  const existingFlush = inflightByPath.get(path)
  if (existingFlush) return existingFlush

  const flush = (async (): Promise<void> => {
    try {
      // Keep flushing while there are pending patches
      while (pendingPatches.has(path)) {
        const toSend = pendingPatches.get(path)
        if (!toSend) break

        const body = buildPatch(toSend)
        if (!hasPatchFields(body)) {
          if (pendingPatches.get(path) === toSend) {
            pendingPatches.delete(path)
          }
          continue
        }

        let baseVersion = 1
        try {
          const base = await api.getSidecar(path)
          baseVersion = base.version ?? 1
        } catch {
          baseVersion = 1
        }

        const payload = { ...body, base_version: baseVersion }

        try {
          await api.patchSidecar(path, payload, {
            idempotencyKey: makeIdempotencyKey('patch'),
            ifMatch: baseVersion,
          })
          clearConflict(path)
          if (pendingPatches.get(path) === toSend) {
            pendingPatches.delete(path)
          }
        } catch (err) {
          const isConflict = captureConflict(path, body, err)
          if (isConflict) {
            const latest = pendingPatches.get(path)
            if (latest && latest !== toSend) {
              const latestPatch = buildPatch(latest)
              if (hasPatchFields(latestPatch)) {
                const entry = conflictByPath.get(path)
                if (entry) {
                  conflictByPath.set(path, { ...entry, pending: latestPatch })
                  notifyConflict(path)
                }
              }
            }
            pendingPatches.delete(path)
          } else {
            if (err instanceof FetchError) {
              setSyncError(err.message)
            } else {
              setSyncError('Failed to save')
            }
          }
          throw err
        }
      }
    } finally {
      inflightByPath.delete(path)
      updateSyncState()
    }
  })()

  inflightByPath.set(path, flush)
  updateSyncState()
  return flush
}

/**
 * Check if there are pending updates for a path.
 */
export function hasPendingUpdate(path: string): boolean {
  return pendingPatches.has(path) || inflightByPath.has(path)
}
