import { useQuery } from '@tanstack/react-query'
import { fetchJSON } from '../lib/fetcher'
import type { Item } from '../lib/types'
import { BASE } from './base'
export function useSearch(q: string, path: string) {
  const qp = new URLSearchParams()
  if (q) qp.set('q', q)
  if (path) qp.set('path', path)
  return useQuery({ enabled: !!q, queryKey: ['search', q, path], queryFn: () => fetchJSON<{ items: Item[] }>(`${BASE}/search?${qp.toString()}`).promise })
}
