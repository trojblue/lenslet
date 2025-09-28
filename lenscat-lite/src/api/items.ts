import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Sidecar } from '../lib/types'

export function useSidecar(path: string) {
  return useQuery({ queryKey: ['item', path], queryFn: () => api.getSidecar(path) })
}

export function useUpdateSidecar(path: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (next: Sidecar) => api.putSidecar(path, next),
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 4000),
    onSuccess: (data) => { qc.setQueryData(['item', path], data) }
  })
}

// Helper for bulk updates: fetch each sidecar, merge fields, and PUT back
export async function bulkUpdateSidecars(paths: string[], fields: Partial<Sidecar>) {
  const now = new Date().toISOString()
  // Limit concurrency to avoid flooding the backend
  const CONCURRENCY = 6
  let idx = 0
  const results: Promise<void>[] = []
  const worker = async () => {
    while (idx < paths.length) {
      const p = paths[idx++]
      try {
        await queueSidecarUpdate(p, fields, now)
      } catch (e) {
        // Surface in console for visibility; do not swallow silently
        try { console.error('bulkUpdate failed for', p, e) } catch {}
      }
    }
  }
  for (let i = 0; i < Math.min(CONCURRENCY, paths.length); i++) results.push(worker())
  await Promise.all(results)
}

// Optimistic, per-path update queue so rapid changes coalesce and persist reliably
const pendingPatches = new Map<string, Partial<Sidecar>>()
const inflightByPath = new Map<string, Promise<void>>()

export async function queueSidecarUpdate(path: string, patch: Partial<Sidecar>, timestamp?: string) {
  const now = timestamp ?? new Date().toISOString()
  // merge with pending for this path
  const existing = pendingPatches.get(path) || {}
  pendingPatches.set(path, { ...existing, ...patch })
  // if already flushing, let that cycle pick up the merged patch
  if (inflightByPath.has(path)) return inflightByPath.get(path)!

  const flush = (async () => {
    try {
      for (;;) {
        const toSend = pendingPatches.get(path)
        if (!toSend) break
        pendingPatches.delete(path)
        // fetch latest server copy to avoid clobbering unrelated fields
        let base: Sidecar
        try { base = await api.getSidecar(path) as Sidecar }
        catch { base = { v:1, tags:[], notes:'', updated_at: now, updated_by:'web' } as any }
        const next: Sidecar = { ...(base as any), ...(toSend as any), updated_at: now, updated_by: 'web' }
        // retry with backoff
        let attempts = 0
        for (;;) {
          try { await api.putSidecar(path, next); break }
          catch (e) { if (++attempts >= 3) throw e; await new Promise(r=> setTimeout(r, 200 * Math.pow(2, attempts))) }
        }
        // loop to see if more patches accumulated while we were PUTing
      }
    } finally {
      inflightByPath.delete(path)
    }
  })()
  inflightByPath.set(path, flush)
  return flush
}
