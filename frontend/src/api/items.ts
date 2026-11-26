import { useEffect, useState } from 'react'
import { useQuery, type QueryClient } from '@tanstack/react-query'
import { api, makeIdempotencyKey } from './client'
import { usePollingEnabled } from './polling'
import { FetchError } from '../lib/fetcher'
import type {
  AcceptedEventIdentity,
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
 * - `appendNotes` adds a paragraph to whatever notes each image already has;
 * - tags are add/remove diffs that the server merges.
 */
export type AnnotationEdit = {
  star?: StarRating
  notes?: { from: string; to: string }
  appendNotes?: string
  addTags?: string[]
  removeTags?: string[]
}

/**
 * A PATCH the server may already have applied. Until its result is known to be
 * on disk it is only ever resent byte-for-byte under the same Idempotency-Key,
 * so the server replays it instead of applying it twice.
 */
type SentRequest = {
  edit: AnnotationEdit
  patch: SidecarPatch
  ifMatch: number
  key: string
}

type QueuedEdit = {
  /** Sent earlier with no settled answer; resent, in order, before `edit`. */
  unconfirmed: SentRequest[]
  /** Not yet sent. */
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
const sending = new Map<string, SendJob>()
const failedPaths = new Map<string, string>()
/** Accepted but not yet on disk, by Idempotency-Key, in send order. */
const awaitingDurability = new Map<string, { path: string; request: SentRequest; accepted: AcceptedEventIdentity }>()
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

labelPersistenceTracker.subscribe(() => {
  settleDurability()
  updateSyncState()
})

function getOldestInflightStart(): number | null {
  let oldest: number | null = null
  for (const entry of [...queued.values(), ...sending.values()]) {
    oldest = oldest == null ? entry.queuedAt : Math.min(oldest, entry.queuedAt)
  }
  return oldest
}

/**
 * The rating the user last gave `path` that the server has not answered yet.
 * It is shown over any server state that arrives meanwhile.
 */
export function pendingAnnotationStar(path: string): StarRating | undefined {
  const job = sending.get(path)
  const later = queued.get(path)
  const edits = [
    ...(job ? [...job.unconfirmed.map((request) => request.edit), job.edit] : []),
    ...(later ? [...later.unconfirmed.map((request) => request.edit), later.edit] : []),
  ]
  let star: StarRating | undefined
  for (const edit of edits) if (edit.star !== undefined) star = edit.star
  return star
}

/** True while any annotation edit is queued, being sent, awaiting retry, or not yet on disk. */
export function hasUnsavedAnnotations(): boolean {
  return queued.size > 0 || sending.size > 0 || awaitingDurability.size > 0 || conflictByPath.size > 0
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
  const appended = [earlier.appendNotes, later.appendNotes].filter(Boolean).join('\n')
  if (appended) merged.appendNotes = appended
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

const NO_EDIT: AnnotationEdit = {}

function isEmptyEdit(edit: AnnotationEdit): boolean {
  return edit.star === undefined && !edit.notes && !edit.appendNotes
    && !edit.addTags?.length && !edit.removeTags?.length
}

function appendParagraph(notes: string, paragraph: string): string {
  return notes ? `${notes}\n${paragraph}` : paragraph
}

// Notes are written as whole text; an append is resolved against the record just read.
function toPatch(edit: AnnotationEdit, current: Sidecar): SidecarPatch {
  const patch: SidecarPatch = {}
  if (edit.star !== undefined) patch.set_star = edit.star
  const notes = edit.notes ? edit.notes.to : current.notes ?? ''
  if (edit.notes || edit.appendNotes) {
    patch.set_notes = edit.appendNotes ? appendParagraph(notes, edit.appendNotes) : notes
  }
  if (edit.addTags?.length) patch.add_tags = edit.addTags
  if (edit.removeTags?.length) patch.remove_tags = edit.removeTags
  return patch
}

function changedFieldsForEdit(edit: AnnotationEdit): string[] {
  const changed: string[] = []
  if (edit.star !== undefined) changed.push('star')
  if (edit.notes || edit.appendNotes) changed.push('notes')
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

/** The only answer that proves a write was not applied: its base version had moved. */
function isVersionConflict(error: unknown): boolean {
  if (!(error instanceof FetchError) || error.status !== 409) return false
  const body = error.body as { error?: unknown } | null | undefined
  return body?.error === 'version_conflict'
}

function errorMessage(error: unknown): string {
  if (error instanceof FetchError && error.status === 404) return 'image no longer exists'
  if (error instanceof FetchError && error.status === 403) return 'not allowed to edit labels'
  return error instanceof Error && error.message ? error.message : 'failed to save'
}

class VersionRaceError extends Error {}

/** Older writes for the path came back (a lost server epoch); they must go first. */
class RequeueBehindError extends Error {}

/** What a send has not yet settled; read back by the caller when the send fails. */
type SendJob = {
  unconfirmed: SentRequest[]
  edit: AnnotationEdit
  queuedAt: number
}

function submit(path: string, request: SentRequest): Promise<SidecarMutationResponse> {
  return api.patchSidecar(path, request.patch, {
    idempotencyKey: request.key,
    ifMatch: request.ifMatch,
  })
}

// Publish an answer only once the request is no longer counted as unanswered.
function settle(path: string, request: SentRequest, response: SidecarMutationResponse): void {
  observeMutationPersistence(path, response)
  publishAnnotationMutationResponse({ path, response, changedFields: changedFieldsForEdit(request.edit) })
  if (response.accepted_event && response.persistence === 'pending') {
    awaitingDurability.set(request.key, { path, request, accepted: response.accepted_event })
  }
}

// Resend what may already be applied; a version conflict proves it (and every
// later write for this path) was not, so those fold back into the open edit.
async function confirmUnconfirmed(path: string, job: SendJob): Promise<void> {
  while (job.unconfirmed.length > 0) {
    try {
      const request = job.unconfirmed[0]
      const response = await submit(path, request)
      job.unconfirmed.shift()
      settle(path, request, response)
    } catch (error) {
      if (!isVersionConflict(error)) throw error
      job.edit = [...job.unconfirmed, { edit: job.edit }].reduce<AnnotationEdit>(
        (merged, next) => mergeAnnotationEdits(merged, next.edit),
        NO_EDIT,
      )
      job.unconfirmed = []
    }
  }
}

// Read the current record, peel off a notes edit another writer has overtaken,
// then write with If-Match so nothing can land between the read and the write.
async function sendEdit(path: string, job: SendJob): Promise<void> {
  await confirmUnconfirmed(path, job)
  for (let race = 0; race < MAX_VERSION_RACES; race += 1) {
    if (queued.get(path)?.unconfirmed.length) throw new RequeueBehindError()
    if (isEmptyEdit(job.edit)) return
    const current = await api.getSidecar(path)
    let pending = job.edit
    if (pending.notes) {
      const serverNotes = current.notes ?? ''
      const { from, to } = pending.notes
      if (serverNotes === to || serverNotes !== from) {
        if (serverNotes !== to) {
          setConflict(path, { path, current, mine: to, receivedAt: new Date().toISOString() })
          publishServerSidecar(path, current, ['notes'])
        }
        const { notes: _overtaken, ...rest } = pending
        pending = rest
      }
    }
    job.edit = pending
    if (isEmptyEdit(pending)) return
    const request: SentRequest = {
      edit: pending,
      patch: { ...toPatch(pending, current), base_version: current.version },
      ifMatch: current.version,
      key: makeIdempotencyKey('patch'),
    }
    job.unconfirmed = [request]
    job.edit = NO_EDIT
    try {
      const response = await submit(path, request)
      job.unconfirmed = []
      settle(path, request, response)
      return
    } catch (error) {
      if (!isVersionConflict(error)) throw error
      job.unconfirmed = []
      job.edit = pending
    }
  }
  throw new VersionRaceError('the image kept changing while saving')
}

// A server that restarted before saving lost these writes; send them again.
function settleDurability(): void {
  let requeued = false
  for (const [key, awaiting] of awaitingDurability) {
    const state = labelPersistenceTracker.durabilityOf(awaiting.accepted)
    if (state === 'pending') continue
    awaitingDurability.delete(key)
    if (state === 'durable') continue
    const entry = queued.get(awaiting.path)
    queued.set(awaiting.path, entry
      ? { ...entry, unconfirmed: [...entry.unconfirmed, awaiting.request], retryAt: 0 }
      : { unconfirmed: [awaiting.request], edit: NO_EDIT, queuedAt: Date.now(), attempts: 0, retryAt: 0, error: null })
    requeued = true
  }
  if (requeued) scheduleSends()
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
  const job: SendJob = { unconfirmed: [...entry.unconfirmed], edit: entry.edit, queuedAt: entry.queuedAt }
  sending.set(path, job)
  void sendEdit(path, job).then(
    () => {
      failedPaths.delete(path)
    },
    (error: unknown) => {
      if (error instanceof RequeueBehindError || isRetryable(error)) {
        // Keep the work, behind any lost older writes and ahead of anything
        // queued meanwhile; retry with backoff unless it only had to wait.
        const later = queued.get(path)
        const behind = error instanceof RequeueBehindError
        const attempts = behind ? entry.attempts : entry.attempts + 1
        queued.set(path, {
          unconfirmed: [...(later?.unconfirmed ?? []), ...job.unconfirmed],
          edit: later ? mergeAnnotationEdits(job.edit, later.edit) : job.edit,
          queuedAt: entry.queuedAt,
          attempts,
          retryAt: behind ? 0 : Date.now() + Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** (attempts - 1)),
          error: behind ? null : errorMessage(error),
        })
        return
      }
      // The server will never accept this edit: say so, and restore server truth.
      failedPaths.set(path, errorMessage(error))
      const refused = [...entry.unconfirmed.map((request) => request.edit), entry.edit]
        .reduce(mergeAnnotationEdits, NO_EDIT)
      void api.getSidecar(path).then(
        (current) => publishServerSidecar(path, current, changedFieldsForEdit(refused)),
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
    : { unconfirmed: [], edit, queuedAt: Date.now(), attempts: 0, retryAt: 0, error: null })
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
  awaitingDurability.clear()
  failedPaths.clear()
  conflictByPath.clear()
  updateSyncState()
}
