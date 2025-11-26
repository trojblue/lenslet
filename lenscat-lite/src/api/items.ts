import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { Sidecar } from '../lib/types'

/** Query key for sidecar data */
export const sidecarQueryKey = (path: string) => ['item', path] as const

/** Default sidecar for new items */
const DEFAULT_SIDECAR: Sidecar = {
  v: 1,
  tags: [],
  notes: '',
  updated_at: '',
  updated_by: 'web',
}

/**
 * Hook to fetch sidecar metadata for an item.
 */
export function useSidecar(path: string) {
  return useQuery({
    queryKey: sidecarQueryKey(path),
    queryFn: () => api.getSidecar(path),
    enabled: !!path,
    staleTime: 30_000, // Sidecar data doesn't change often
    gcTime: 5 * 60_000,
    retry: 2,
  })
}

/**
 * Hook to update sidecar metadata.
 * Optimistically updates the cache on success.
 */
export function useUpdateSidecar(path: string) {
  const qc = useQueryClient()
  
  return useMutation({
    mutationFn: (next: Sidecar) => api.putSidecar(path, next),
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * Math.pow(2, attempt), 4000),
    onSuccess: (data) => {
      qc.setQueryData(sidecarQueryKey(path), data)
    },
  })
}

/** Concurrency limit for bulk operations */
const BULK_CONCURRENCY = 6

/**
 * Update multiple sidecars with the same partial data.
 * Uses a worker pool to limit concurrent requests.
 */
export async function bulkUpdateSidecars(
  paths: string[],
  fields: Partial<Omit<Sidecar, 'v' | 'updated_at' | 'updated_by'>>
): Promise<void> {
  if (!paths.length) return
  
  const now = new Date().toISOString()
  let idx = 0
  const errors: Array<{ path: string; error: unknown }> = []
  
  const worker = async (): Promise<void> => {
    while (idx < paths.length) {
      const currentIdx = idx++
      const p = paths[currentIdx]
      try {
        await queueSidecarUpdate(p, fields, now)
      } catch (error) {
        errors.push({ path: p, error })
        // Log but don't stop other updates
        console.error(`[bulkUpdateSidecars] Failed for ${p}:`, error)
      }
    }
  }
  
  // Start workers
  const workers = Array.from(
    { length: Math.min(BULK_CONCURRENCY, paths.length) },
    () => worker()
  )
  await Promise.all(workers)
  
  // If all failed, throw
  if (errors.length === paths.length) {
    throw new Error(`All ${paths.length} sidecar updates failed`)
  }
}

/**
 * Pending patches keyed by path, waiting to be flushed.
 */
const pendingPatches = new Map<string, Partial<Sidecar>>()

/**
 * In-flight flush operations keyed by path.
 */
const inflightByPath = new Map<string, Promise<void>>()

/**
 * Queue a sidecar update for a path. Coalesces rapid updates.
 * Returns a promise that resolves when the update is persisted.
 */
export async function queueSidecarUpdate(
  path: string,
  patch: Partial<Omit<Sidecar, 'v' | 'updated_at' | 'updated_by'>>,
  timestamp?: string
): Promise<void> {
  const now = timestamp ?? new Date().toISOString()
  
  // Merge with any pending patch for this path
  const existing = pendingPatches.get(path) || {}
  pendingPatches.set(path, { ...existing, ...patch })
  
  // If already flushing, the existing flush will pick up this patch
  const existingFlush = inflightByPath.get(path)
  if (existingFlush) return existingFlush

  const flush = (async (): Promise<void> => {
    try {
      // Keep flushing while there are pending patches
      while (pendingPatches.has(path)) {
        const toSend = pendingPatches.get(path)
        pendingPatches.delete(path)
        
        if (!toSend) break
        
        // Fetch latest server copy to avoid clobbering unrelated fields
        let base: Sidecar
        try {
          base = await api.getSidecar(path)
        } catch {
          base = { ...DEFAULT_SIDECAR, updated_at: now }
        }
        
        const next: Sidecar = {
          ...base,
          ...toSend,
          v: 1,
          updated_at: now,
          updated_by: 'web',
        }
        
        // Retry with exponential backoff
        let attempts = 0
        const maxAttempts = 3
        while (attempts < maxAttempts) {
          try {
            await api.putSidecar(path, next)
            break
          } catch (e) {
            attempts++
            if (attempts >= maxAttempts) throw e
            await new Promise((r) => setTimeout(r, 200 * Math.pow(2, attempts)))
          }
        }
      }
    } finally {
      inflightByPath.delete(path)
    }
  })()
  
  inflightByPath.set(path, flush)
  return flush
}

/**
 * Check if there are pending updates for a path.
 */
export function hasPendingUpdate(path: string): boolean {
  return pendingPatches.has(path) || inflightByPath.has(path)
}
