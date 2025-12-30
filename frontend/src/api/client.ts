import { fetchJSON, fetchBlob } from '../lib/fetcher'
import { fileCache, thumbCache } from '../lib/blobCache'
import type { FolderIndex, Sidecar, FileOpResponse, RefreshResponse, SearchResult, ImageMetadataResponse, ViewsPayload } from '../lib/types'
import { BASE } from './base'

/** Maximum file size to cache in prefetch (40MB) */
const MAX_PREFETCH_SIZE = 40 * 1024 * 1024

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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
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
