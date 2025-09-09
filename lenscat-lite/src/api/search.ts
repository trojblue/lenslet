import { useQuery } from '@tanstack/react-query'
import { fetchJSON } from '../lib/fetcher'
import type { Item } from '../lib/types'
const BASE = import.meta.env.VITE_API_BASE ?? ''
export function useSearch(q: string) {
  return useQuery({ enabled: !!q, queryKey: ['search', q], queryFn: () => fetchJSON<{ items: Item[] }>(`${BASE}/search?q=${encodeURIComponent(q)}`).promise })
}
