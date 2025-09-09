import { useQuery } from '@tanstack/react-query'
import { api } from './client'

export function useFolder(path: string) {
  return useQuery({ queryKey: ['folder', path], queryFn: () => api.getFolder(path), staleTime: 5_000 })
}
