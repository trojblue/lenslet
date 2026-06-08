import { fetchJSON, fetchBlob } from '../lib/fetcher'
import { fileCache, thumbCache } from '../lib/blobCache'
import type { BrowseEndpoint } from '../lib/browseHotpath'
import {
  cancelBrowseRequests as cancelBudgetedBrowseRequests,
  getBrowseRequestBudgetSnapshot,
  runWithRequestBudget,
  resetBrowseRequestBudgetForTests,
} from './requestBudget'
import type {
  BrowseFolderPayload,
  BrowseFolderPathsPayload,
  Sidecar,
  SidecarPatch,
  RefreshResponse,
  BrowseSearchResultsPayload,
  ImageMetadataResponse,
  ExportComparisonRequest,
  ViewsPayload,
  HealthResponse,
  EmbeddingsResponse,
  EmbeddingSearchRequest,
  EmbeddingSearchResponse,
  PresenceEvent,
  ItemUpdatedEvent,
  MetricsUpdatedEvent,
  TableSourceColumnsPayload,
} from '../lib/types'
import { apiUrl } from './base'

const MAX_PREFETCH_SIZE = 40 * 1024 * 1024
const THUMB_PREFETCH_MAX_QUEUED = 256
export type FullFilePrefetchContext = 'viewer' | 'compare'

function isFullFilePrefetchContext(value: unknown): value is FullFilePrefetchContext {
  return value === 'viewer' || value === 'compare'
}

function thumbUrl(path: string): string {
  return apiUrl(`/thumb?path=${encodeURIComponent(path)}`)
}

function fileUrl(path: string): string {
  return apiUrl(`/file?path=${encodeURIComponent(path)}`)
}

const CLIENT_ID_SESSION_KEY = 'lenslet.client_id.session'
const LAST_EVENT_ID_KEY = 'lenslet.last_event_id'
const RECONNECT_BASE_MS = 1000
const RECONNECT_MAX_MS = 30_000
const RECONNECT_MAX_ATTEMPTS = 5
const FALLBACK_POLLING_ENABLED = true

let cachedClientId: string | null = null
let cachedLastEventId: number | null = null
let idempotencyCounter = 0

let reconnectTimer: number | null = null
let reconnectAttempt = 0
let reconnectEnabled = true
let pollingEnabled = false

function canUseEventSource(): boolean {
  return typeof window !== 'undefined' && typeof EventSource !== 'undefined'
}

function safeStorageGet(storage: Storage | null, key: string): string | null {
  if (!storage) return null
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

function safeStorageSet(storage: Storage | null, key: string, value: string): void {
  if (!storage) return
  try {
    storage.setItem(key, value)
  } catch {
    // Ignore persistence errors
  }
}

function safeStorageRemove(storage: Storage | null, key: string): void {
  if (!storage) return
  try {
    storage.removeItem(key)
  } catch {
    // Ignore persistence errors
  }
}

function buildFingerprintSeed(): string {
  if (typeof navigator === 'undefined') return 'server'
  const ua = navigator.userAgent || ''
  const lang = navigator.language || ''
  const platform = navigator.platform || ''
  const tz = typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone || '' : ''
  const screenInfo = typeof screen !== 'undefined'
    ? `${screen.width}x${screen.height}x${screen.colorDepth}`
    : ''
  return [ua, lang, platform, tz, screenInfo].join('|')
}

function hashFingerprint(seed: string): string {
  // Simple FNV-1a 32-bit hash for stable, non-crypto IDs.
  let hash = 0x811c9dc5
  for (let i = 0; i < seed.length; i += 1) {
    hash ^= seed.charCodeAt(i)
    hash = (hash * 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}

function generateClientId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `client_${Math.random().toString(36).slice(2, 10)}_${Date.now()}`
}

function cacheClientId(clientId: string): string {
  cachedClientId = clientId
  return clientId
}

function getWindowStorage(kind: 'local' | 'session'): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage
  } catch {
    return null
  }
}

export function ensureClientId(): string {
  if (cachedClientId) return cachedClientId
  const session = getWindowStorage('session')

  const sessionClientId = safeStorageGet(session, CLIENT_ID_SESSION_KEY)
  if (sessionClientId) {
    return cacheClientId(sessionClientId)
  }

  if (session) {
    const nextSessionClientId = generateClientId()
    safeStorageSet(session, CLIENT_ID_SESSION_KEY, nextSessionClientId)
    return cacheClientId(nextSessionClientId)
  }

  const fallback = `fp_${hashFingerprint(buildFingerprintSeed())}_${Math.random().toString(36).slice(2, 8)}`
  return cacheClientId(fallback)
}

export function makeIdempotencyKey(prefix = 'lenslet'): string {
  idempotencyCounter += 1
  const nonce = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `nonce_${Math.random().toString(36).slice(2, 10)}_${Date.now()}_${idempotencyCounter}`
  return `${prefix}:${ensureClientId()}:${nonce}`
}

function readLastEventId(): number | null {
  if (cachedLastEventId != null) return cachedLastEventId
  if (typeof window === 'undefined') return null
  const local = getWindowStorage('local')
  if (!local) return null
  try {
    const raw = local.getItem(LAST_EVENT_ID_KEY)
    if (!raw) return null
    const parsed = Number(raw)
    if (!Number.isFinite(parsed) || parsed <= 0) return null
    cachedLastEventId = parsed
    return parsed
  } catch {
    return null
  }
}

function writeLastEventId(next: number): void {
  if (!Number.isFinite(next) || next <= 0) return
  cachedLastEventId = next
  if (typeof window === 'undefined') return
  const local = getWindowStorage('local')
  if (!local) return
  try {
    local.setItem(LAST_EVENT_ID_KEY, String(next))
  } catch {
    // Ignore persistence errors
  }
}

function buildEventsUrl(): string {
  if (typeof window === 'undefined') return apiUrl('/events')
  const url = new URL(apiUrl('/events'), window.location.origin)
  const lastEventId = readLastEventId()
  if (lastEventId != null && Number.isFinite(lastEventId)) {
    url.searchParams.set('last_event_id', String(lastEventId))
  }
  return url.toString()
}

function parseEventData<T>(raw: string): T | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export type ConnectionStatus = 'idle' | 'connecting' | 'live' | 'reconnecting' | 'offline'
export type SyncEvent =
  | { type: 'item-updated'; id: number | null; data: ItemUpdatedEvent }
  | { type: 'metrics-updated'; id: number | null; data: MetricsUpdatedEvent }
  | { type: 'presence'; id: number | null; data: PresenceEvent }

export type PresenceSessionResponse = PresenceEvent & {
  client_id: string
  lease_id: string
}

export type PresenceMoveResponse = {
  client_id: string
  lease_id: string
  from_scope: PresenceEvent
  to_scope: PresenceEvent
}

export type PresenceLeaveResponse = PresenceSessionResponse & {
  removed: boolean
}

let eventSource: EventSource | null = null
let connectionStatus: ConnectionStatus = 'idle'
const eventListeners = new Set<(evt: SyncEvent) => void>()
const statusListeners = new Set<(status: ConnectionStatus) => void>()
const pollingListeners = new Set<(enabled: boolean) => void>()

function notifyStatus(next: ConnectionStatus) {
  connectionStatus = next
  for (const listener of statusListeners) {
    listener(next)
  }
}

function notifyPolling(next: boolean) {
  if (pollingEnabled === next) return
  pollingEnabled = next
  for (const listener of pollingListeners) {
    listener(next)
  }
}

function clearReconnectTimer() {
  if (reconnectTimer == null) return
  window.clearTimeout(reconnectTimer)
  reconnectTimer = null
}

function resetReconnect() {
  reconnectAttempt = 0
  clearReconnectTimer()
}

function scheduleReconnect(): void {
  if (!reconnectEnabled || reconnectTimer != null) return
  reconnectAttempt += 1
  const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt - 1), RECONNECT_MAX_MS)
  if (reconnectAttempt >= RECONNECT_MAX_ATTEMPTS) {
    notifyStatus('offline')
    if (FALLBACK_POLLING_ENABLED) {
      notifyPolling(true)
    }
  } else {
    notifyStatus('reconnecting')
  }
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = null
    openEventSource()
  }, delay)
}

function openEventSource(): void {
  if (!reconnectEnabled || !canUseEventSource()) return
  if (eventSource && eventSource.readyState === EventSource.CLOSED) {
    eventSource.close()
    eventSource = null
  }
  if (eventSource) return
  if (reconnectAttempt > 0) {
    notifyStatus('reconnecting')
  } else {
    notifyStatus('connecting')
  }
  const es = new EventSource(buildEventsUrl())
  eventSource = es

  const handle = (type: SyncEvent['type']) => (evt: MessageEvent) => {
    const data = parseEventData(evt.data)
    if (!data) return
    const rawId = evt.lastEventId ? Number(evt.lastEventId) : null
    const id = rawId != null && Number.isFinite(rawId) ? rawId : null
    if (id != null) {
      writeLastEventId(id)
    }
    for (const listener of eventListeners) {
      listener({ type, id, data } as SyncEvent)
    }
  }

  es.addEventListener('item-updated', handle('item-updated'))
  es.addEventListener('metrics-updated', handle('metrics-updated'))
  es.addEventListener('presence', handle('presence'))

  es.onopen = () => {
    resetReconnect()
    notifyPolling(false)
    notifyStatus('live')
  }
  es.onerror = () => {
    if (eventSource !== es) return
    es.close()
    eventSource = null
    scheduleReconnect()
  }
}

export function connectEvents(): void {
  reconnectEnabled = true
  if (!canUseEventSource()) return
  clearReconnectTimer()
  openEventSource()
}

export function disconnectEvents(): void {
  reconnectEnabled = false
  clearReconnectTimer()
  reconnectAttempt = 0
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  notifyPolling(false)
  notifyStatus('offline')
}

export function subscribeEvents(listener: (evt: SyncEvent) => void): () => void {
  eventListeners.add(listener)
  return () => {
    eventListeners.delete(listener)
  }
}

export function subscribeEventStatus(listener: (status: ConnectionStatus) => void): () => void {
  statusListeners.add(listener)
  listener(connectionStatus)
  return () => {
    statusListeners.delete(listener)
  }
}

export function subscribePollingStatus(listener: (enabled: boolean) => void): () => void {
  pollingListeners.add(listener)
  listener(pollingEnabled)
  return () => {
    pollingListeners.delete(listener)
  }
}

export function getPollingStatus(): boolean {
  return pollingEnabled
}

export function getEventStatus(): ConnectionStatus {
  return connectionStatus
}

export function __resetClientStateForTests(): void {
  cachedClientId = null
  cachedLastEventId = null
  idempotencyCounter = 0
  clearReconnectTimer()
  reconnectAttempt = 0
  reconnectEnabled = true
  notifyPolling(false)
  eventListeners.clear()
  statusListeners.clear()
  pollingListeners.clear()
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  connectionStatus = 'idle'
  resetBrowseRequestBudgetForTests()
}

export function cancelBrowseRequests(endpoints?: readonly BrowseEndpoint[]): void {
  cancelBudgetedBrowseRequests(endpoints)
}

function postPresenceKeepalive(path: string, payload: unknown): boolean {
  const body = JSON.stringify(payload)
  const url = apiUrl(path)

  if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
    try {
      const queued = navigator.sendBeacon(url, new Blob([body], { type: 'application/json' }))
      if (queued) return true
    } catch {
      // Ignore beacon failures and try keepalive fetch fallback.
    }
  }

  if (typeof fetch !== 'function') return false
  try {
    void fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    })
    return true
  } catch {
    return false
  }
}

export function dispatchPresenceLeave(galleryId: string, leaseId: string): boolean {
  return postPresenceKeepalive('/presence/leave', {
    gallery_id: galleryId,
    lease_id: leaseId,
  })
}

function postPresenceJSON<TResponse>(path: string, payload: unknown): Promise<TResponse> {
  return fetchJSON<TResponse>(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).promise
}

export type GetFolderOptions = {
  recursive?: boolean
  countOnly?: boolean
  offset?: number
  limit?: number
}

export function buildFolderQuery(path: string, options?: GetFolderOptions): string {
  const params = new URLSearchParams({ path })
  if (options?.recursive) params.set('recursive', '1')
  if (options?.countOnly) params.set('count_only', '1')
  if (options?.offset !== undefined) params.set('offset', String(options.offset))
  if (options?.limit !== undefined) params.set('limit', String(options.limit))
  return params.toString()
}

function folderPayloadCount(folder: BrowseFolderPayload): number {
  return folder.total_items ?? folder.items.length
}

export const api = {
  getFolder: (path: string, options?: GetFolderOptions): Promise<BrowseFolderPayload> => {
    return runWithRequestBudget('folders', () =>
      fetchJSON<BrowseFolderPayload>(apiUrl(`/folders?${buildFolderQuery(path, options)}`)),
    ).promise
  },

  getFolderCount: (path: string): Promise<number> => {
    return runWithRequestBudget('folders', () =>
      fetchJSON<BrowseFolderPayload>(
        apiUrl(`/folders?${buildFolderQuery(path, { recursive: true, countOnly: true })}`),
      ),
    ).promise.then(folderPayloadCount)
  },

  getFolderPaths: (): Promise<BrowseFolderPathsPayload> => {
    return fetchJSON<BrowseFolderPathsPayload>(apiUrl('/folders/paths')).promise
  },

  search: (q: string, path: string): Promise<BrowseSearchResultsPayload> => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (path) params.set('path', path)
    return fetchJSON<BrowseSearchResultsPayload>(apiUrl(`/search?${params}`)).promise
  },

  getEmbeddings: (): Promise<EmbeddingsResponse> => {
    return fetchJSON<EmbeddingsResponse>(apiUrl('/embeddings')).promise
  },

  searchEmbeddings: (body: EmbeddingSearchRequest): Promise<EmbeddingSearchResponse> => {
    return fetchJSON<EmbeddingSearchResponse>(apiUrl('/embeddings/search'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).promise
  },

  refreshFolder: (path: string): Promise<RefreshResponse> => {
    const params = new URLSearchParams({ path })
    return fetchJSON<RefreshResponse>(apiUrl(`/refresh?${params}`), {
      method: 'POST',
    }).promise
  },

  getSidecar: (path: string): Promise<Sidecar> => {
    return fetchJSON<Sidecar>(apiUrl(`/item?path=${encodeURIComponent(path)}`)).promise
  },

  // Patch writes use If-Match plus idempotency keys so retries do not double-apply edits.
  patchSidecar: (
    path: string,
    body: SidecarPatch,
    opts?: { idempotencyKey?: string; ifMatch?: number }
  ): Promise<Sidecar> => {
    const idempotencyKey = opts?.idempotencyKey ?? makeIdempotencyKey('patch')
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    }
    if (opts?.ifMatch != null) headers['If-Match'] = String(opts.ifMatch)
    return fetchJSON<Sidecar>(apiUrl(`/item?path=${encodeURIComponent(path)}`), {
      method: 'PATCH',
      headers,
      body: JSON.stringify(body),
    }).promise
  },

  getMetadata: (path: string): Promise<ImageMetadataResponse> => {
    return fetchJSON<ImageMetadataResponse>(apiUrl(`/metadata?path=${encodeURIComponent(path)}`)).promise
  },

  putSidecar: (path: string, body: Sidecar): Promise<Sidecar> => {
    return fetchJSON<Sidecar>(apiUrl(`/item?path=${encodeURIComponent(path)}`), {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    }).promise
  },

  getHealth: (): Promise<HealthResponse> => {
    return fetchJSON<HealthResponse>(apiUrl('/health')).promise
  },

  getTableSourceColumns: (): Promise<TableSourceColumnsPayload> => {
    return fetchJSON<TableSourceColumnsPayload>(apiUrl('/table/source-columns')).promise
  },

  switchTableSourceColumn: (sourceColumn: string): Promise<TableSourceColumnsPayload> => {
    return fetchJSON<TableSourceColumnsPayload>(apiUrl('/table/source-column'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_column: sourceColumn }),
    }).promise
  },

  joinPresence: (galleryId: string, leaseId?: string): Promise<PresenceSessionResponse> => {
    return postPresenceJSON<PresenceSessionResponse>('/presence/join', {
      gallery_id: galleryId,
      lease_id: leaseId,
    })
  },

  movePresence: (
    fromGalleryId: string,
    toGalleryId: string,
    leaseId: string,
  ): Promise<PresenceMoveResponse> => {
    return postPresenceJSON<PresenceMoveResponse>('/presence/move', {
      from_gallery_id: fromGalleryId,
      to_gallery_id: toGalleryId,
      lease_id: leaseId,
    })
  },

  leavePresence: (galleryId: string, leaseId: string): Promise<PresenceLeaveResponse> => {
    return postPresenceJSON<PresenceLeaveResponse>('/presence/leave', {
      gallery_id: galleryId,
      lease_id: leaseId,
    })
  },

  getThumb: (path: string): Promise<Blob> => {
    return thumbCache.getOrFetch(path, () =>
      runWithRequestBudget('thumb', () =>
        fetchBlob(thumbUrl(path)),
      )
    )
  },

  // Uncached hover fetches stay outside fileCache so hover cancellation cannot
  // abort viewer/compare loads sharing that cache's in-flight request.
  getHoverPreview: (path: string): { promise: Promise<Blob>; abort?: () => void } => {
    const cached = fileCache.get(path)
    if (cached) return { promise: Promise.resolve(cached) }
    return runWithRequestBudget('file', () =>
      fetchBlob(fileUrl(path)),
    )
  },

  prefetchThumb: (path: string): void => {
    const budget = getBrowseRequestBudgetSnapshot()
    if (budget.queued.thumb >= THUMB_PREFETCH_MAX_QUEUED) return
    thumbCache.prefetch(path, () =>
      runWithRequestBudget('thumb', () =>
        fetchBlob(thumbUrl(path)),
      )
    )
  },

  getFile: (path: string): Promise<Blob> => {
    return fileCache.getOrFetch(path, () =>
      runWithRequestBudget('file', () =>
        fetchBlob(fileUrl(path)),
      )
    )
  },

  exportComparison: (body: ExportComparisonRequest): Promise<Blob> => {
    return fetchBlob(apiUrl('/export-comparison'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).promise
  },

  // Full-file prefetch is restricted to viewer/compare contexts and capped at
  // 40MB so scroll/hover behavior cannot fill the shared cache with huge originals.
  prefetchFile: async (path: string, context: FullFilePrefetchContext): Promise<void> => {
    if (!isFullFilePrefetchContext(context)) return
    // Skip if already cached or in-flight
    if (fileCache.has(path) || fileCache.isInflight(path)) return

    try {
      const blob = await runWithRequestBudget('file', () =>
        fetchBlob(fileUrl(path), {
          headers: { 'x-lenslet-prefetch': context },
        }),
      ).promise
      if (blob.size <= MAX_PREFETCH_SIZE) {
        fileCache.set(path, blob)
      }
    } catch {
      // Silently ignore prefetch errors
    }
  },

  cancelPrefetch: (path: string): void => {
    fileCache.cancelPrefetch(path)
  },

  getViews: (): Promise<ViewsPayload> => {
    return fetchJSON<ViewsPayload>(apiUrl('/views')).promise
  },

  saveViews: (payload: ViewsPayload): Promise<ViewsPayload> => {
    return fetchJSON<ViewsPayload>(apiUrl('/views'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).promise
  },
}
