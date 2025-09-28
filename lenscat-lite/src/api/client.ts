import { fetchJSON, fetchBlob } from '../lib/fetcher'
import { fileCache, thumbCache } from '../lib/blobCache'
import type { FolderIndex, Sidecar } from '../lib/types'

// Prefer same-origin in production/tunnel; use VITE_API_BASE only for local dev.
// If VITE_API_BASE points to localhost but the page is served from a non-localhost
// origin (e.g., via Cloudflare tunnel), ignore it and use same-origin.
const envBase = (import.meta as any).env?.VITE_API_BASE as string | undefined
const isLocalHost = typeof window !== 'undefined' && /^(localhost|127\.0\.0\.1|\[::1\])$/i.test(window.location.hostname)
const envPointsToLocal = !!envBase && /localhost|127\.0\.0\.1|\[::1\]/i.test(envBase)
const BASE = !isLocalHost && envPointsToLocal ? '' : (envBase ?? '')

export const api = {
  getFolder: (path: string, page?: number) => fetchJSON<FolderIndex>(`${BASE}/folders?path=${encodeURIComponent(path)}${page!=null?`&page=${page}`:''}`).promise,
  getSidecar: (path: string) => fetchJSON<Sidecar>(`${BASE}/item?path=${encodeURIComponent(path)}`).promise,
  putSidecar: (path: string, body: Sidecar) => fetchJSON<Sidecar>(`${BASE}/item?path=${encodeURIComponent(path)}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }).promise,
  getThumb: (path: string) => thumbCache.getOrFetch(path, () => fetchBlob(`${BASE}/thumb?path=${encodeURIComponent(path)}`).promise),
  prefetchThumb: (path: string) => thumbCache.prefetch(path, () => fetchBlob(`${BASE}/thumb?path=${encodeURIComponent(path)}`).promise),
  getFile: (path: string) => fileCache.getOrFetch(path, () => fetchBlob(`${BASE}/file?path=${encodeURIComponent(path)}`).promise),
  // Prefetch with a 40MB size cap to avoid caching abnormally large originals
  prefetchFile: async (path: string) => {
    const blob = await fetchBlob(`${BASE}/file?path=${encodeURIComponent(path)}`).promise
    if ((blob.size || 0) <= 40 * 1024 * 1024) fileCache.set(path, blob)
  },
  uploadFile: async (dest: string, file: File) => {
    const fd = new FormData()
    fd.append('dest', dest)
    fd.append('file', file)
    const { promise } = fetchJSON<{ ok: boolean; path: string }>(`${BASE}/file`, { method: 'POST', body: fd as any })
    return promise
  },
  moveFile: async (src: string, dest: string) => {
    const fd = new FormData()
    fd.append('src', src)
    fd.append('dest', dest)
    const { promise } = fetchJSON<{ ok: boolean; path: string }>(`${BASE}/move`, { method: 'POST', body: fd as any })
    return promise
  },
  deleteFiles: async (paths: string[]) => {
    const { promise } = fetchJSON<{ ok: boolean }>(`${BASE}/delete`, { method: 'POST', headers: { 'content-type':'application/json' }, body: JSON.stringify({ paths }) })
    return promise
  },
  exportIntent: async (path: string) => {
    const fd = new FormData()
    fd.append('path', path)
    const { promise } = fetchJSON<{ ok: boolean }>(`${BASE}/export-intent`, { method: 'POST', body: fd as any })
    return promise
  }
}
