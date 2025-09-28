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
    onSuccess: (data) => { qc.setQueryData(['item', path], data) }
  })
}

// Helper for bulk updates: fetch each sidecar, merge fields, and PUT back
export async function bulkUpdateSidecars(paths: string[], fields: Partial<Sidecar>) {
  const now = new Date().toISOString()
  for (const p of paths) {
    try {
      const current = await api.getSidecar(p)
      const next: Sidecar = {
        ...(current as any),
        ...fields,
        updated_at: now,
        updated_by: 'web',
      } as Sidecar
      await api.putSidecar(p, next)
    } catch {}
  }
}
