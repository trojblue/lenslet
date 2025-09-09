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
