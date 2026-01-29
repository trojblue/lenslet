import { fetchJSON, fetchBlob } from '../lib/fetcher'
import { fileCache, thumbCache } from '../lib/blobCache'
import type {
  FolderIndex,
  Sidecar,
  SidecarPatch,
  FileOpResponse,
  RefreshResponse,
  SearchResult,
  ImageMetadataResponse,
  ViewsPayload,
  HealthResponse,
  EmbeddingsResponse,
  EmbeddingSearchRequest,
  EmbeddingSearchResponse,
  PresenceEvent,
  ItemUpdatedEvent,
  MetricsUpdatedEvent,
} from '../lib/types'
import { BASE } from './base'

/** Maximum file size to cache in prefetch (40MB) */
const MAX_PREFETCH_SIZE = 40 * 1024 * 1024

const CLIENT_ID_KEY = 'lenslet.client_id'
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

export function getClientId(): string {
  if (cachedClientId) return cachedClientId
  const local = typeof window !== 'undefined' ? window.localStorage : null
  const session = typeof window !== 'undefined' ? window.sessionStorage : null

  const existing = safeStorageGet(local, CLIENT_ID_KEY) || safeStorageGet(session, CLIENT_ID_SESSION_KEY)
  if (existing) {
    cachedClientId = existing
    return existing
  }

  const generated = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `client_${Math.random().toString(36).slice(2, 10)}_${Date.now()}`

  if (local) {
    safeStorageSet(local, CLIENT_ID_KEY, generated)
    cachedClientId = generated
    return generated
  }

  if (session) {
    safeStorageSet(session, CLIENT_ID_SESSION_KEY, generated)
    cachedClientId = generated
    return generated
  }

  const fallback = `fp_${hashFingerprint(buildFingerprintSeed())}`
  cachedClientId = fallback
  return fallback
}

export function makeIdempotencyKey(prefix = 'lenslet'): string {
  idempotencyCounter += 1
  const nonce = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `nonce_${Math.random().toString(36).slice(2, 10)}_${Date.now()}_${idempotencyCounter}`
  return `${prefix}:${getClientId()}:${nonce}`
}

function readLastEventId(): number | null {
  if (cachedLastEventId != null) return cachedLastEventId
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(LAST_EVENT_ID_KEY)
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
  try {
    window.localStorage.setItem(LAST_EVENT_ID_KEY, String(next))
  } catch {
    // Ignore persistence errors
  }
}

function buildEventsUrl(): string {
  if (typeof window === 'undefined') return `${BASE}/events`
  const url = new URL(`${BASE}/events`, window.location.origin)
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

/**
 * API client for the lenslet backend.
 * All methods return promises and handle caching where appropriate.
 */
export const api = {
  /**
   * Fetch folder contents by path.
   * @param path - Folder path
   * @param page - Optional page number for pagination
   */
  getFolder: (path: string, page?: number): Promise<FolderIndex> => {
    const params = new URLSearchParams({ path })
    if (page != null) params.set('page', String(page))
    return fetchJSON<FolderIndex>(`${BASE}/folders?${params}`).promise
  },

  /**
   * Search for items by query string.
   * @param q - Search query
   * @param path - Base path to search within
   */
  search: (q: string, path: string): Promise<SearchResult> => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    if (path) params.set('path', path)
    return fetchJSON<SearchResult>(`${BASE}/search?${params}`).promise
  },

  /**
   * List available embeddings and any rejected columns.
   */
  getEmbeddings: (): Promise<EmbeddingsResponse> => {
    return fetchJSON<EmbeddingsResponse>(`${BASE}/embeddings`).promise
  },

  /**
   * Run a similarity search for an embedding.
   */
  searchEmbeddings: (body: EmbeddingSearchRequest): Promise<EmbeddingSearchResponse> => {
    return fetchJSON<EmbeddingSearchResponse>(`${BASE}/embeddings/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).promise
  },

  /**
   * Manually refresh a folder subtree on the backend.
   */
  refreshFolder: (path: string): Promise<RefreshResponse> => {
    const params = new URLSearchParams({ path })
    return fetchJSON<RefreshResponse>(`${BASE}/refresh?${params}`, {
      method: 'POST',
    }).promise
  },

  /**
   * Fetch sidecar metadata for an item.
   */
  getSidecar: (path: string): Promise<Sidecar> => {
    return fetchJSON<Sidecar>(`${BASE}/item?path=${encodeURIComponent(path)}`).promise
  },

  /**
   * Patch sidecar metadata with optimistic concurrency + idempotency.
   */
  patchSidecar: (
    path: string,
    body: SidecarPatch,
    opts?: { idempotencyKey?: string; ifMatch?: number }
  ): Promise<Sidecar> => {
    const idempotencyKey = opts?.idempotencyKey ?? makeIdempotencyKey('patch')
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
      'x-client-id': getClientId(),
      'x-updated-by': 'web',
    }
    if (opts?.ifMatch != null) headers['If-Match'] = String(opts.ifMatch)
    return fetchJSON<Sidecar>(`${BASE}/item?path=${encodeURIComponent(path)}`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify(body),
    }).promise
  },

  /**
   * Fetch heavy image metadata (PNG text chunks, etc) on-demand.
   */
  getMetadata: (path: string): Promise<ImageMetadataResponse> => {
    return fetchJSON<ImageMetadataResponse>(`${BASE}/metadata?path=${encodeURIComponent(path)}`).promise
  },

  /**
   * Update sidecar metadata for an item.
   */
  putSidecar: (path: string, body: Sidecar): Promise<Sidecar> => {
    return fetchJSON<Sidecar>(`${BASE}/item?path=${encodeURIComponent(path)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'x-client-id': getClientId(),
        'x-updated-by': 'web',
      },
      body: JSON.stringify(body),
    }).promise
  },

  /**
   * Fetch backend health and persistence status.
   */
  getHealth: (): Promise<HealthResponse> => {
    return fetchJSON<HealthResponse>(`${BASE}/health`).promise
  },

  /**
   * Send presence heartbeat for the current gallery.
   */
  postPresence: (galleryId: string, clientId?: string): Promise<PresenceEvent> => {
    return fetchJSON<PresenceEvent>(`${BASE}/presence`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        gallery_id: galleryId,
        client_id: clientId ?? getClientId(),
      }),
    }).promise
  },

  /**
   * Get a thumbnail, using cache if available.
   */
  getThumb: (path: string): Promise<Blob> => {
    return thumbCache.getOrFetch(path, () =>
      fetchBlob(`${BASE}/thumb?path=${encodeURIComponent(path)}`)
    )
  },

  /**
   * Prefetch a thumbnail in the background.
   */
  prefetchThumb: (path: string): void => {
    thumbCache.prefetch(path, () =>
      fetchBlob(`${BASE}/thumb?path=${encodeURIComponent(path)}`)
    )
  },

  /**
   * Get a full-size file, using cache if available.
   */
  getFile: (path: string): Promise<Blob> => {
    return fileCache.getOrFetch(path, () =>
      fetchBlob(`${BASE}/file?path=${encodeURIComponent(path)}`)
    )
  },

  /**
   * Prefetch a full-size file in the background.
   * Respects the 40MB size cap to avoid caching huge files.
   */
  prefetchFile: async (path: string): Promise<void> => {
    // Skip if already cached or in-flight
    if (fileCache.has(path) || fileCache.isInflight(path)) return
    
    try {
      const blob = await fetchBlob(`${BASE}/file?path=${encodeURIComponent(path)}`).promise
      if (blob.size <= MAX_PREFETCH_SIZE) {
        fileCache.set(path, blob)
      }
    } catch {
      // Silently ignore prefetch errors
    }
  },

  /**
   * Cancel a prefetch if it's in progress.
   */
  cancelPrefetch: (path: string): void => {
    fileCache.cancelPrefetch(path)
  },

  /**
   * Upload a file to a destination folder.
   */
  uploadFile: async (dest: string, file: File): Promise<FileOpResponse> => {
    const fd = new FormData()
    fd.append('dest', dest)
    fd.append('file', file)
    return fetchJSON<FileOpResponse>(`${BASE}/file`, {
      method: 'POST',
      body: fd,
      timeoutMs: 60_000, // Longer timeout for uploads
    }).promise
  },

  /**
   * Move a file from one location to another.
   */
  moveFile: async (src: string, dest: string): Promise<FileOpResponse> => {
    const fd = new FormData()
    fd.append('src', src)
    fd.append('dest', dest)
    return fetchJSON<FileOpResponse>(`${BASE}/move`, {
      method: 'POST',
      body: fd,
    }).promise
  },

  /**
   * Permanently delete files.
   */
  deleteFiles: async (paths: string[]): Promise<{ ok: boolean }> => {
    return fetchJSON<{ ok: boolean }>(`${BASE}/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths }),
    }).promise
  },

  /**
   * Signal intent to export a file.
   */
  exportIntent: async (path: string): Promise<{ ok: boolean }> => {
    const fd = new FormData()
    fd.append('path', path)
    return fetchJSON<{ ok: boolean }>(`${BASE}/export-intent`, {
      method: 'POST',
      body: fd,
    }).promise
  },

  /**
   * Fetch saved Smart Folders (views).
   */
  getViews: (): Promise<ViewsPayload> => {
    return fetchJSON<ViewsPayload>(`${BASE}/views`).promise
  },

  /**
   * Persist saved Smart Folders (views).
   */
  saveViews: (payload: ViewsPayload): Promise<ViewsPayload> => {
    return fetchJSON<ViewsPayload>(`${BASE}/views`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).promise
  },
}
