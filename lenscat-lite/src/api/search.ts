import { useQuery } from '@tanstack/react-query'
import { fetchJSON } from '../lib/fetcher'
import type { Item } from '../lib/types'
const envBase = (import.meta as any).env?.VITE_API_BASE as string | undefined
const isLocalHost = typeof window !== 'undefined' && /^(localhost|127\.0\.0\.1|\[::1\])$/i.test(window.location.hostname)
const envPointsToLocal = !!envBase && /localhost|127\.0\.0\.1|\[::1\]/i.test(envBase)
const BASE = !isLocalHost && envPointsToLocal ? '' : (envBase ?? '')
export function useSearch(q: string) {
  return useQuery({ enabled: !!q, queryKey: ['search', q], queryFn: () => fetchJSON<{ items: Item[] }>(`${BASE}/search?q=${encodeURIComponent(q)}`).promise })
}
