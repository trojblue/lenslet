import { useMemo } from 'react'
import { useSidecar } from '../api/items'
export function useInspector(path: string | null) {
  const q = useSidecar(path ?? '')
  return useMemo(() => ({ path, sidecar: q.data, loading: q.isLoading, error: q.error as Error | null }), [path, q.data, q.isLoading, q.error])
}
