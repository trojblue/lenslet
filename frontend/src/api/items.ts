import { useEffect, useState } from 'react'
import { useQuery, type QueryClient } from '@tanstack/react-query'
import { api, makeIdempotencyKey } from './client'
import { usePollingEnabled } from './polling'
import { FetchError } from '../lib/fetcher'
import type {
  BrowseItemPayload,
  Sidecar,
  SidecarMutationResponse,
  SidecarPatch,
  StarRating,
} from '../lib/types'
import {
  labelPersistenceTracker,
  requestLabelPersistenceRefresh,
} from './labelPersistence'

export const sidecarQueryKey = (path: string, scopeKey?: string) => (
  scopeKey ? ['item', path, scopeKey] as const : ['item', path] as const
)

export const itemDetailQueryKey = (path: string, scopeKey?: string) => (
  scopeKey ? ['item-detail', path, scopeKey] as const : ['item-detail', path] as const
)

export function setSidecarQueryDataForPath(
  queryClient: QueryClient,
  path: string,
  sidecar: Sidecar,
): void {
  const mergeSidecar = (current: Sidecar | undefined): Sidecar => ({
    ...current,
    ...sidecar,
    table_fields: sidecar.table_fields === undefined ? current?.table_fields : sidecar.table_fields,
  })
  const existing = queryClient.getQueriesData<Sidecar>({ queryKey: sidecarQueryKey(path) })
    .find((entry): entry is [readonly unknown[], Sidecar] => entry[1] !== undefined)?.[1]
  queryClient.setQueryData(sidecarQueryKey(path), mergeSidecar(existing))
  queryClient.setQueriesData<Sidecar>(
    { queryKey: sidecarQueryKey(path) },
    (current) => mergeSidecar(current),
  )
}

export function updateItemDetailQueryDataForPath(
  queryClient: QueryClient,
  path: string,
  updater: (current: BrowseItemPayload | undefined) => BrowseItemPayload | undefined,
): void {
  queryClient.setQueriesData<BrowseItemPayload>({ queryKey: itemDetailQueryKey(path) }, updater)
}

export type SyncStatus = {
  state: 'idle' | 'syncing' | 'saving' | 'error'
  message?: string
}

/**
 * Another writer changed an image's notes after the user started editing them.
 * `mine` is the user's text; it stays here until they keep or discard it.
 */
export type ConflictEntry = {
  path: string
  current: Sidecar
  mine: string
  receivedAt: string
}

export type AnnotationMutationResponse = {
  path: string
  response: SidecarMutationResponse
  changedFields: string[]
}

const annotationMutationListeners = new Set<(mutation: AnnotationMutationResponse) => void>()

export function subscribeAnnotationMutationResponses(
  listener: (mutation: AnnotationMutationResponse) => void,
): () => void {
  annotationMutationListeners.add(listener)
  return () => {
    annotationMutationListeners.delete(listener)
  }
}

function publishAnnotationMutationResponse(mutation: AnnotationMutationResponse): void {
  for (const listener of annotationMutationListeners) {
    listener(mutation)
  }
}

function observeMutationPersistence(path: string, response: SidecarMutationResponse): void {
  labelPersistenceTracker.observeMutation(path, response)
  if (!response.accepted_event && response.persistence === 'pending') {
    requestLabelPersistenceRefresh()
  }
}


/**
 * One user intent for one image. Edits describe what changed rather than a whole
 * record, so concurrent writers merge instead of overwriting each other:
 * - `star` is absolute (the latest rating wins);
 * - `notes` remembers the text the user started from, and conflicts only when
 *   another writer changed it since;
 * - tags are add/remove diffs that the server merges.
 */
export type AnnotationEdit = {
  star?: StarRating
  notes?: { from: string | null; to: string }
  addTags?: string[]
  removeTags?: string[]
}

type QueuedEdit = {
  edit: AnnotationEdit
  queuedAt: number
  attempts: number
  retryAt: number
  error: string | null
}

const MAX_CONCURRENT_SENDS = 6
const MAX_VERSION_RACES = 4
const RETRY_BASE_MS = 1_000
const RETRY_MAX_MS = 30_000

const queued = new Map<string, QueuedEdit>()
const sending = new Map<string, QueuedEdit>()
const failedPaths = new Map<string, string>()
let retryTimer: ReturnType<typeof setTimeout> | null = null

const conflictByPath = new Map<string, ConflictEntry>()
const conflictListeners = new Map<string, Set<(entry: ConflictEntry | null) => void>>()

const FALLBACK_SIDECAR_INTERVAL = 12_000

const syncListeners = new Set<(status: SyncStatus) => void>()
const inflightAgeListeners = new Set<(oldestStart: number | null) => void>()
let syncState: SyncStatus = { state: 'idle' }

function fileName(path: string): string {
  return path.split('/').pop() || path
}

function describePaths(paths: string[]): string {
  return paths.length === 1 ? fileName(paths[0]) : `${paths.length} images`
}

function notifySync(next: SyncStatus) {
  syncState = next
  for (const listener of syncListeners) {
    listener(next)
  }
  const oldest = getOldestInflightStart()
  for (const listener of inflightAgeListeners) {
    listener(oldest)
  }
}

// Status is derived from the queue itself, so one image's success can never
// hide another image's unsaved edit.
function updateSyncState() {
  if (conflictByPath.size > 0) {
    notifySync({ state: 'error', message: `conflicting notes on ${describePaths([...conflictByPath.keys()])}` })
    return
  }
  const retrying = [...queued.entries()].filter(([, entry]) => entry.error !== null)
  if (retrying.length > 0) {
    notifySync({ state: 'error', message: `${describePaths(retrying.map(([path]) => path))}, retrying` })
    return
  }
  if (failedPaths.size > 0) {
    const [, error] = failedPaths.entries().next().value as [string, string]
    notifySync({ state: 'error', message: `${describePaths([...failedPaths.keys()])}: ${error}` })
    return
  }
  if (queued.size + sending.size > 0) {
    notifySync({ state: 'syncing' })
    return
  }
  const persistence = labelPersistenceTracker.snapshot()
  if (persistence.state === 'failed') {
    notifySync({ state: 'error', message: persistence.error ?? 'Label storage is unavailable' })
    return
  }
  if (persistence.state === 'saving') {
    notifySync({ state: 'saving' })
    return
  }
  notifySync({ state: 'idle' })
}

labelPersistenceTracker.subscribe(() => updateSyncState())

function getOldestInflightStart(): number | null {
  let oldest: number | null = null
  for (const entry of [...queued.values(), ...sending.values()]) {
    oldest = oldest == null ? entry.queuedAt : Math.min(oldest, entry.queuedAt)
  }
  return oldest
}

/** True while any annotation edit is queued, being sent, or awaiting retry. */
export function hasUnsavedAnnotations(): boolean {
  return queued.size > 0 || sending.size > 0 || conflictByPath.size > 0
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

/** Server truth moved; a conflict resolves itself once the server holds the user's text. */
export function updateConflictFromServer(path: string, current: Sidecar): void {
  const existing = conflictByPath.get(path)
  if (!existing) return
  if ((current.notes ?? '') === existing.mine) {
    clearConflict(path)
    return
  }
  conflictByPath.set(path, { ...existing, current })
  notifyConflict(path)
  updateSyncState()
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

export function subscribeOldestInflightStart(listener: (oldestStart: number | null) => void): () => void {
  inflightAgeListeners.add(listener)
  listener(getOldestInflightStart())
  return () => {
    inflightAgeListeners.delete(listener)
  }
}

export function useOldestInflightAgeMs(): number | null {
  const [oldestStart, setOldestStart] = useState<number | null>(() => getOldestInflightStart())
  const [ageMs, setAgeMs] = useState<number | null>(() => (
    oldestStart == null ? null : Date.now() - oldestStart
  ))

  useEffect(() => {
    return subscribeOldestInflightStart(setOldestStart)
  }, [])

  useEffect(() => {
    if (oldestStart == null) {
      setAgeMs(null)
      return
    }
    setAgeMs(Date.now() - oldestStart)
    const id = window.setInterval(() => {
      setAgeMs(Date.now() - oldestStart)
    }, 1000)
    return () => window.clearInterval(id)
  }, [oldestStart])

  return ageMs
}

export function useSidecar(path: string, enabled = true, scopeKey?: string) {
  const pollingEnabled = usePollingEnabled()
  return useQuery({
    queryKey: sidecarQueryKey(path, scopeKey),
    queryFn: () => api.getSidecar(path),
    enabled: !!path && enabled,
    staleTime: 30_000, // Sidecar data doesn't change often
    gcTime: 5 * 60_000,
    retry: 2,
    refetchInterval: enabled && pollingEnabled ? FALLBACK_SIDECAR_INTERVAL : false,
    refetchIntervalInBackground: enabled && pollingEnabled,
  })
}

export function useItemDetail(path: string, enabled = true, scopeKey?: string) {
  return useQuery({
    queryKey: itemDetailQueryKey(path, scopeKey),
    queryFn: () => api.getItemDetail(path),
    enabled: !!path && enabled,
    staleTime: 30_000,
    gcTime: 5 * 60_000,
    retry: 2,
  })
}

function uniqueTags(values: readonly string[] | undefined): string[] {
  return [...new Set((values ?? []).map((tag) => tag.trim()).filter(Boolean))]
}

/** Compose `later` on top of `earlier` as if both had been applied in order. */
export function mergeAnnotationEdits(earlier: AnnotationEdit, later: AnnotationEdit): AnnotationEdit {
  const merged: AnnotationEdit = {}
  if (later.star !== undefined) merged.star = later.star
  else if (earlier.star !== undefined) merged.star = earlier.star
  if (earlier.notes || later.notes) {
    merged.notes = {
      from: earlier.notes ? earlier.notes.from : later.notes!.from,
      to: later.notes ? later.notes.to : earlier.notes!.to,
    }
  }
  const laterAdd = new Set(uniqueTags(later.addTags))
  const laterRemove = new Set(uniqueTags(later.removeTags))
  const add = [...uniqueTags(earlier.addTags).filter((tag) => !laterRemove.has(tag)), ...laterAdd]
  const remove = [...uniqueTags(earlier.removeTags).filter((tag) => !laterAdd.has(tag)), ...laterRemove]
  if (add.length) merged.addTags = uniqueTags(add)
  if (remove.length) merged.removeTags = uniqueTags(remove)
  return merged
}

/** Diff an edited tag list against the tags the user started from. */
export function tagEditBetween(from: readonly string[], to: readonly string[]): AnnotationEdit {
  const before = new Set(uniqueTags(from))
  const after = new Set(uniqueTags(to))
  const edit: AnnotationEdit = {}
  const addTags = [...after].filter((tag) => !before.has(tag))
  const removeTags = [...before].filter((tag) => !after.has(tag))
  if (addTags.length) edit.addTags = addTags
  if (removeTags.length) edit.removeTags = removeTags
  return edit
}

function isEmptyEdit(edit: AnnotationEdit): boolean {
  return edit.star === undefined && !edit.notes && !edit.addTags?.length && !edit.removeTags?.length
}

function toPatch(edit: AnnotationEdit): SidecarPatch {
  const patch: SidecarPatch = {}
  if (edit.star !== undefined) patch.set_star = edit.star
  if (edit.notes) patch.set_notes = edit.notes.to
  if (edit.addTags?.length) patch.add_tags = edit.addTags
  if (edit.removeTags?.length) patch.remove_tags = edit.removeTags
  return patch
}

function changedFieldsForEdit(edit: AnnotationEdit): string[] {
  const changed: string[] = []
  if (edit.star !== undefined) changed.push('star')
  if (edit.notes) changed.push('notes')
  if (edit.addTags?.length || edit.removeTags?.length) changed.push('tags')
  return changed
}

/** Publish server truth for a path through the same channel as accepted writes. */
function publishServerSidecar(path: string, sidecar: Sidecar, changedFields: string[]): void {
  publishAnnotationMutationResponse({
    path,
    changedFields,
    response: {
      sidecar,
      mutation_id: makeIdempotencyKey('server-truth'),
      accepted_event: null,
      persistence: 'saved',
      durable_watermark: { boot_epoch: 'client-truth', event_id: 0 },
    },
  })
}

function isRetryable(error: unknown): boolean {
  if (!(error instanceof FetchError)) return true
  return error.status === 0 || error.status === 408 || error.status === 409 || error.status === 429 || error.status >= 500
}

function errorMessage(error: unknown): string {
  if (error instanceof FetchError && error.status === 404) return 'image no longer exists'
  if (error instanceof FetchError && error.status === 403) return 'not allowed to edit labels'
  return error instanceof Error && error.message ? error.message : 'failed to save'
}

class VersionRaceError extends Error {}

// Read the current record, peel off a notes edit another writer has overtaken,
// then write with If-Match so nothing can land between the read and the write.
async function sendEdit(path: string, edit: AnnotationEdit): Promise<void> {
  let pending = edit
  for (let race = 0; race < MAX_VERSION_RACES; race += 1) {
    const current = await api.getSidecar(path)
    if (pending.notes) {
      const serverNotes = current.notes ?? ''
      const { from, to } = pending.notes
      if (serverNotes === to || (from !== null && serverNotes !== from)) {
        if (serverNotes !== to) {
          setConflict(path, { path, current, mine: to, receivedAt: new Date().toISOString() })
          publishServerSidecar(path, current, ['notes'])
        }
        const { notes: _overtaken, ...rest } = pending
        pending = rest
      }
    }
    if (isEmptyEdit(pending)) return
    try {
      const response = await api.patchSidecar(
        path,
        { ...toPatch(pending), base_version: current.version },
        { idempotencyKey: makeIdempotencyKey('patch'), ifMatch: current.version },
      )
      observeMutationPersistence(path, response)
      publishAnnotationMutationResponse({ path, response, changedFields: changedFieldsForEdit(pending) })
      return
    } catch (error) {
      if (error instanceof FetchError && error.status === 409) continue
      throw error
    }
  }
  throw new VersionRaceError('the image kept changing while saving')
}

function scheduleSends(): void {
  if (retryTimer !== null) {
    clearTimeout(retryTimer)
    retryTimer = null
  }
  const now = Date.now()
  let nextRetryAt = Number.POSITIVE_INFINITY
  for (const [path, entry] of queued) {
    if (sending.has(path)) continue
    if (entry.retryAt > now) {
      nextRetryAt = Math.min(nextRetryAt, entry.retryAt)
      continue
    }
    if (sending.size >= MAX_CONCURRENT_SENDS) break
    startSend(path, entry)
  }
  if (Number.isFinite(nextRetryAt)) {
    retryTimer = setTimeout(scheduleSends, nextRetryAt - now)
  }
  updateSyncState()
}

function startSend(path: string, entry: QueuedEdit): void {
  queued.delete(path)
  sending.set(path, entry)
  void sendEdit(path, entry.edit).then(
    () => {
      failedPaths.delete(path)
    },
    (error: unknown) => {
      if (isRetryable(error)) {
        // Keep the edit, ahead of anything queued meanwhile, and retry with backoff.
        const later = queued.get(path)
        const attempts = entry.attempts + 1
        queued.set(path, {
          edit: later ? mergeAnnotationEdits(entry.edit, later.edit) : entry.edit,
          queuedAt: entry.queuedAt,
          attempts,
          retryAt: Date.now() + Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** (attempts - 1)),
          error: errorMessage(error),
        })
        return
      }
      // The server will never accept this edit: say so, and restore server truth.
      failedPaths.set(path, errorMessage(error))
      void api.getSidecar(path).then(
        (current) => publishServerSidecar(path, current, changedFieldsForEdit(entry.edit)),
        () => undefined,
      )
    },
  ).finally(() => {
    sending.delete(path)
    scheduleSends()
  })
}

/**
 * The single write path for annotations. Edits for one image coalesce, are sent
 * one at a time per image, and stay queued (retrying with backoff) until the
 * server accepts them or rejects them permanently.
 */
export function enqueueAnnotationEdit(path: string, edit: AnnotationEdit): void {
  if (isEmptyEdit(edit)) return
  const existing = queued.get(path)
  queued.set(path, existing
    ? { ...existing, edit: mergeAnnotationEdits(existing.edit, edit), retryAt: 0 }
    : { edit, queuedAt: Date.now(), attempts: 0, retryAt: 0, error: null })
  scheduleSends()
}

export function enqueueAnnotationEdits(paths: readonly string[], edit: AnnotationEdit): void {
  for (const path of paths) enqueueAnnotationEdit(path, edit)
}

/** Retry everything now, e.g. when connectivity returns. */
export function retryAnnotationEdits(): void {
  for (const entry of queued.values()) entry.retryAt = 0
  scheduleSends()
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', retryAnnotationEdits)
}

/** Test hook: forget all queue state. */
export function resetAnnotationQueueForTests(): void {
  if (retryTimer !== null) clearTimeout(retryTimer)
  retryTimer = null
  queued.clear()
  sending.clear()
  failedPaths.clear()
  conflictByPath.clear()
  updateSyncState()
}
