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
  PresenceEvent,
  ItemUpdatedEvent,
  MetricsUpdatedEvent,
} from '../lib/types'
import { BASE } from './base'

/** Maximum file size to cache in prefetch (40MB) */
const MAX_PREFETCH_SIZE = 40 * 1024 * 1024

const CLIENT_ID_KEY = 'lenslet.client_id'
let cachedClientId: string | null = null
let idempotencyCounter = 0

export function getClientId(): string {
  if (cachedClientId) return cachedClientId
  try {
    const existing = window.localStorage.getItem(CLIENT_ID_KEY)
    if (existing) {
      cachedClientId = existing
      return existing
    }
    const next = typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `client_${Math.random().toString(36).slice(2, 10)}_${Date.now()}`
    window.localStorage.setItem(CLIENT_ID_KEY, next)
    cachedClientId = next
    return next
  } catch {
    const fallback = `client_${Math.random().toString(36).slice(2, 10)}_${Date.now()}`
    cachedClientId = fallback
    return fallback
  }
}

export function makeIdempotencyKey(prefix = 'lenslet'): string {
  idempotencyCounter += 1
  return `${prefix}:${getClientId()}:${Date.now()}:${idempotencyCounter}`
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

function notifyStatus(next: ConnectionStatus) {
  connectionStatus = next
  for (const listener of statusListeners) {
    listener(next)
  }
}

export function connectEvents(): void {
  if (eventSource || typeof window === 'undefined' || typeof EventSource === 'undefined') return
  notifyStatus('connecting')
  const es = new EventSource(`${BASE}/events`)
  eventSource = es

  const handle = (type: SyncEvent['type']) => (evt: MessageEvent) => {
    const data = parseEventData(evt.data)
    if (!data) return
    const rawId = evt.lastEventId ? Number(evt.lastEventId) : null
    const id = rawId != null && Number.isFinite(rawId) ? rawId : null
    for (const listener of eventListeners) {
      listener({ type, id, data } as SyncEvent)
    }
  }

  es.addEventListener('item-updated', handle('item-updated'))
  es.addEventListener('metrics-updated', handle('metrics-updated'))
  es.addEventListener('presence', handle('presence'))

  es.onopen = () => notifyStatus('live')
  es.onerror = () => {
    if (!eventSource) return
    if (eventSource.readyState === EventSource.CLOSED) {
      notifyStatus('offline')
    } else {
      notifyStatus('reconnecting')
    }
  }
}

export function disconnectEvents(): void {
  if (!eventSource) return
  eventSource.close()
  eventSource = null
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
