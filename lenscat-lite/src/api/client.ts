import { fetchJSON, fetchBlob } from '../lib/fetcher'
import type { FolderIndex, Sidecar } from '../lib/types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export const api = {
  getFolder: (path: string, page?: number) => fetchJSON<FolderIndex>(`${BASE}/folders?path=${encodeURIComponent(path)}${page!=null?`&page=${page}`:''}`).promise,
  getSidecar: (path: string) => fetchJSON<Sidecar>(`${BASE}/item?path=${encodeURIComponent(path)}`).promise,
  putSidecar: (path: string, body: Sidecar) => fetchJSON<Sidecar>(`${BASE}/item?path=${encodeURIComponent(path)}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }).promise,
  getThumb: (path: string) => fetchBlob(`${BASE}/thumb?path=${encodeURIComponent(path)}`).promise,
  getFile: (path: string) => fetchBlob(`${BASE}/file?path=${encodeURIComponent(path)}`).promise
}
