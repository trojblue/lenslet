import { useQuery } from '@tanstack/react-query'
import { fetchJSON } from '../lib/fetcher'
import type { Item } from '../lib/types'
import { BASE } from './base'
export function useSearch(q: string) {
  return useQuery({ enabled: !!q, queryKey: ['search', q], queryFn: () => fetchJSON<{ items: Item[] }>(`${BASE}/search?q=${encodeURIComponent(q)}`).promise })
}
