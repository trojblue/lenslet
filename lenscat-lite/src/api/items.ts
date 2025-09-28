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
        const current = await api.getSidecar(p)
        const next: Sidecar = { ...(current as any), ...fields, updated_at: now, updated_by: 'web' } as Sidecar
        // retry a few times for transient failures
        let attempts = 0
        for (;;) {
          try { await api.putSidecar(p, next); break }
          catch (e) { if (++attempts >= 3) throw e; await new Promise(r=> setTimeout(r, 200 * Math.pow(2, attempts))) }
        }
      } catch (e) {
        // Surface in console for visibility; do not swallow silently
        try { console.error('bulkUpdate failed for', p, e) } catch {}
      }
    }
  }
  for (let i = 0; i < Math.min(CONCURRENCY, paths.length); i++) results.push(worker())
  await Promise.all(results)
}
